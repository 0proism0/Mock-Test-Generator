#!/usr/bin/env python3
"""Validate (and upgrade) MockTest Maker paper JSON against format v1.1.

    python scripts/validate_paper.py examples/demo_rand_01.json
    python scripts/validate_paper.py users/test/tests/*.json --legacy-ok
    python scripts/validate_paper.py users/test/tests/amc8_rand_01.json --upgrade
    python scripts/validate_paper.py examples/demo_rand_01.json --hash
    python scripts/validate_paper.py examples/demo_rand_01.json --coverage

Standard library only, same policy as app/server.py.
Exit code: 0 = clean (warnings allowed), 1 = errors, 2 = unreadable input.

The schema lives in schema/paper-1.1.schema.json (schema/paper-1.0.schema.json
is frozen for reference); this script re-implements the rules JSON Schema cannot
express (cross references, asset existence, answer vs choices consistency,
topic ids vs the taxonomy file) so it works without a jsonschema dependency.

All console output is ASCII on purpose: the project is run from GBK cmd.exe
windows where non-ASCII diagnostics turn into mojibake.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

FORMAT_VERSION = "1.1"
FORMAT_RE = re.compile(r"^1\.\d+$")
# Files written by older tools keep validating: 1.1 is a superset of 1.0.
SUPPORTED_FORMATS = ("1.0", "1.1")

TOP_KEYS = {
    "format_version", "paper_version", "id", "title", "competition", "category",
    "instructions", "time_limit_min", "total_points", "calculator_allowed",
    "locale", "created_at", "updated_at", "generator", "version_history",
    "sections", "taxonomy", "questions", "content_hash", "notes",
}
QUESTION_KEYS = {
    "n", "qid", "section", "type", "source", "question", "question_zh", "choices",
    "answer", "solution", "solution_zh", "points", "grading", "figure", "subject",
    "difficulty", "classification",
}
FIGURE_KEYS = {
    "kind", "state", "placement", "src", "inline", "mime", "sha256", "width",
    "height", "viewBox", "alt", "caption", "credit", "source_code",
}
QUESTION_TYPES = {"multiple_choice", "integer_answer", "numeric", "proof"}
FIGURE_KINDS = {"svg", "image"}
FIGURE_STATES = {"ready", "placeholder"}
PLACEMENTS = {"prompt", "solution", "both"}

# --- v1.1: per-question classification ------------------------------------
CLASSIFICATION_KEYS = {
    "state", "taxonomy", "primary", "tags", "source", "confidence", "reviewed",
    "at", "note",
}
TAG_KEYS = {"id", "weight", "note"}
CLASSIFICATION_STATES = {"pending", "done"}
CLASSIFICATION_SOURCES = {"human", "rule", "model", "import"}
TOPIC_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
TAXONOMY_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")

# Annotation, not content: re-tagging must not churn cached hashes or force a
# paper_version bump. Excluded from content_hash along with x-* extensions.
HASH_EXCLUDED_KEYS = {"classification", "difficulty"}

# difficulty is an estimate, not authored content: recalibrating it (prior, model
# re-rating, Elo updates from real answers) must not invalidate content_hash or force
# a paper_version bump. The v1.1 difficulty object therefore stays out of the hash.
LEGACY_DIFFICULTY = {"easy", "medium", "hard"}
# Difficulty scale "amc20": 1-20 where 20 = the average AMC 12 problem 25; AIME and
# olympiad problems legitimately go above 20. Band is derived, never authored by hand.
DIFFICULTY_SCORE_MAX = 60
DIFFICULTY_LEVEL_MAX = 60
DIFFICULTY_EASY_MAX = 9        # <= AMC 8 last problem
DIFFICULTY_MEDIUM_MAX = 17     # <= AMC 10 last problem; AMC 12 #25 is 20
DIFFICULTY_SCALES = {"amc20", "legacy5"}


def band_of_level(level: int) -> str:
    if level <= DIFFICULTY_EASY_MAX:
        return "easy"
    if level <= DIFFICULTY_MEDIUM_MAX:
        return "medium"
    return "hard"


DIFFICULTY_KEYS = {"level", "scale", "band", "score", "method", "confidence",
                   "components", "evidence", "reviewed", "at"}
DIFFICULTY_METHODS = {"prior", "llm_rubric", "elo", "irt", "human", "hybrid"}
DIFFICULTY_COMPONENT_KEYS = {"method", "score", "weight", "confidence", "reason"}

REPO_ROOT = Path(__file__).resolve().parent.parent

# Same heuristic the bank builders use for has_diagram. Used when upgrading a
# legacy paper so geometry problems get a reserved figure slot.
DIAGRAM_HINT = re.compile(r"\bdiagram\b|\bfigure\b|\bshown\b|如图|图中", re.IGNORECASE)


class Problems:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.items: list[tuple[str, str, str]] = []
        self.taxonomy_unverified = False

    def error(self, code: str, msg: str) -> None:
        self.items.append(("error", code, msg))

    def warn(self, code: str, msg: str) -> None:
        self.items.append(("warn", code, msg))

    @property
    def errors(self) -> int:
        return sum(1 for lvl, _, _ in self.items if lvl == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for lvl, _, _ in self.items if lvl == "warn")


def _hash_payload(questions: list) -> list:
    """Strip annotation-only keys (classification, x-*) before hashing."""
    out = []
    for q in questions:
        if isinstance(q, dict):
            q = {
                k: v for k, v in q.items()
                if k not in HASH_EXCLUDED_KEYS and not k.startswith("x-")
            }
        out.append(q)
    return out


def content_hash(questions: list) -> str:
    """sha256 over the canonical JSON of the questions array.

    Canonical = UTF-8, keys sorted, no spaces, ensure_ascii=False. Assets are
    covered through their inline/src/sha256 fields, so swapping a file changes
    the hash as long as the asset's sha256 is maintained.

    Since v1.1 classification and x-* are excluded: re-tagging a question is an
    annotation change, not a content change. Papers without those keys hash the
    same as under v1.0.
    """
    blob = json.dumps(_hash_payload(questions), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _unknown_keys(obj: dict, allowed: set[str], p: Problems, where: str) -> None:
    for key in obj:
        if key not in allowed and not key.startswith("x-"):
            p.error("unknown-key", f"{where}: unknown field {key!r} (use an x- prefix for extensions)")


def _check_figure(fig, p: Problems, paper_dir: Path, where: str) -> None:
    if fig is None:
        return
    if not isinstance(fig, dict):
        p.error("figure-type", f"{where}: figure must be an object or null")
        return
    _unknown_keys(fig, FIGURE_KEYS, p, f"{where}.figure")

    kind, state = fig.get("kind"), fig.get("state")
    if kind not in FIGURE_KINDS:
        p.error("figure-kind", f"{where}: figure.kind must be one of {sorted(FIGURE_KINDS)}, got {kind!r}")
    if state not in FIGURE_STATES:
        p.error("figure-state", f"{where}: figure.state must be one of {sorted(FIGURE_STATES)}, got {state!r}")
    if fig.get("placement") not in PLACEMENTS:
        p.error("figure-placement", f"{where}: figure.placement must be one of {sorted(PLACEMENTS)}")
    alt = fig.get("alt")
    if not isinstance(alt, str) or not alt.strip():
        p.error("figure-alt", f"{where}: figure.alt is required (a11y text, and what to draw while placeholder)")

    for dim in ("width", "height"):
        if dim in fig and not (_is_num(fig[dim]) and fig[dim] > 0):
            p.error("figure-size", f"{where}: figure.{dim} must be a positive number")

    has_src, has_inline = "src" in fig, "inline" in fig
    if state == "ready":
        if has_src == has_inline:
            p.error("figure-source", f"{where}: state=ready needs exactly one of figure.src / figure.inline")
        if "width" not in fig or "height" not in fig:
            p.error("figure-size", f"{where}: state=ready needs width/height (display size)")
    elif state == "placeholder":
        if has_src or has_inline:
            p.error("figure-source", f"{where}: state=placeholder must not carry src/inline (nothing drawn yet)")
        if "width" not in fig or "height" not in fig:
            p.error("figure-size", f"{where}: state=placeholder needs width/height (reserved box)")

    if has_src:
        src = fig["src"]
        if not isinstance(src, str) or not src.strip():
            p.error("figure-src", f"{where}: figure.src must be a non-empty string")
        else:
            target = (paper_dir / src).resolve()
            if not target.is_file():
                p.error("figure-missing", f"{where}: asset {src!r} not found (relative to {paper_dir})")
            else:
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                if fig.get("sha256") and fig["sha256"] != digest:
                    p.error("figure-hash", f"{where}: sha256 mismatch for {src!r} (file changed?)")
                elif not fig.get("sha256"):
                    p.warn("figure-hash", f"{where}: {src!r} has no sha256, expected {digest}")
        if fig.get("sha256") and not re.fullmatch(r"[0-9a-f]{64}", str(fig["sha256"])):
            p.error("figure-hash", f"{where}: figure.sha256 must be 64 lowercase hex chars")

    if has_inline:
        inline = fig["inline"]
        if not isinstance(inline, str) or not inline.strip():
            p.error("figure-inline", f"{where}: figure.inline must be a non-empty string")
        else:
            if kind == "svg":
                try:
                    ElementTree.fromstring(inline)
                except ElementTree.ParseError as exc:
                    p.error("figure-svg", f"{where}: inline SVG is not well-formed XML: {exc}")
                if "currentColor" not in inline:
                    p.warn("figure-theme", f"{where}: inline SVG uses no currentColor, it may be invisible in dark mode")
            if len(inline) > 200_000:
                p.warn("figure-inline", f"{where}: inline payload is {len(inline)//1024} KB, prefer src")

    mime = fig.get("mime")
    if mime:
        if kind == "svg" and mime != "image/svg+xml":
            p.warn("figure-mime", f"{where}: kind=svg but mime={mime!r}")
        if kind == "image" and not str(mime).startswith("image/"):
            p.warn("figure-mime", f"{where}: kind=image but mime={mime!r}")


class Taxonomy:
    """A loaded topic vocabulary (taxonomy/<id>.json)."""

    def __init__(self, tax_id: str, version: str, nodes: dict[str, str | None]) -> None:
        self.id = tax_id
        self.version = version
        self.nodes = nodes                    # node id -> parent id (None for roots)
        self.children: dict[str, list[str]] = {}
        for nid, parent in nodes.items():
            self.children.setdefault(parent or "", []).append(nid)

    def has(self, node_id: str) -> bool:
        return node_id in self.nodes

    def is_leaf(self, node_id: str) -> bool:
        return not self.children.get(node_id)


_TAXONOMY_CACHE: dict[str, Taxonomy | None] = {}


def _parse_taxonomy(data, path: Path, p: Problems) -> Taxonomy | None:
    if not isinstance(data, dict):
        p.error("taxonomy-type", f"{path}: taxonomy root must be an object")
        return None
    nodes: dict[str, str | None] = {}

    def walk(items, parent: str | None) -> None:
        if not isinstance(items, list):
            p.error("taxonomy-nodes", f"{path}: nodes must be an array")
            return
        for node in items:
            if not isinstance(node, dict):
                p.error("taxonomy-node", f"{path}: each node must be an object")
                continue
            nid = node.get("id")
            if not isinstance(nid, str) or not TOPIC_ID_RE.fullmatch(nid):
                p.error("taxonomy-node-id", f"{path}: bad node id {nid!r}")
                continue
            if nid in nodes:
                p.error("taxonomy-node-dup", f"{path}: duplicate node id {nid!r}")
                continue
            if parent and not nid.startswith(parent + "."):
                p.error("taxonomy-node-parent", f"{path}: node {nid!r} must sit under {parent!r} (id prefix)")
            nodes[nid] = parent
            walk(node.get("children") or [], nid)

    walk(data.get("roots") or [], None)
    if not nodes:
        p.error("taxonomy-empty", f"{path}: taxonomy declares no nodes")
        return None
    tax_id = data.get("id")
    if isinstance(tax_id, str) and not TAXONOMY_ID_RE.fullmatch(tax_id):
        p.error("taxonomy-id", f"{path}: taxonomy id {tax_id!r} must match {TAXONOMY_ID_RE.pattern}")
    return Taxonomy(tax_id if isinstance(tax_id, str) else path.stem, str(data.get("version") or ""), nodes)


def load_taxonomy(ref, paper_dir: Path, p: Problems) -> Taxonomy | None:
    """Load the taxonomy a paper points at. None means ids cannot be verified."""
    if not isinstance(ref, dict):
        return None
    tax_id = ref.get("id")
    if not isinstance(tax_id, str) or not tax_id:
        return None
    candidates: list[Path] = []
    uri = ref.get("uri")
    if isinstance(uri, str) and uri.strip():
        candidates.append(paper_dir / uri)
    candidates.append(paper_dir / "taxonomy" / f"{tax_id}.json")
    candidates.append(REPO_ROOT / "taxonomy" / f"{tax_id}.json")
    for cand in candidates:
        try:
            key = str(cand.resolve())
        except OSError:
            continue
        if key in _TAXONOMY_CACHE:
            cached = _TAXONOMY_CACHE[key]
            if cached is not None:
                return cached
            continue
        if not cand.is_file():
            _TAXONOMY_CACHE[key] = None
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            p.warn("taxonomy-load", f"cannot read taxonomy {cand}: {exc}")
            _TAXONOMY_CACHE[key] = None
            return None
        tax = _parse_taxonomy(data, cand, p)
        _TAXONOMY_CACHE[key] = tax
        return tax
    p.warn(
        "taxonomy-missing",
        f"taxonomy {tax_id!r} not found (looked next to the paper and in {REPO_ROOT / 'taxonomy'}); "
        f"topic ids were not verified",
    )
    return None


def _check_classification(cls, p: Problems, where: str, default_tax_id: str | None,
                          taxonomy: Taxonomy | None) -> None:
    """Validate one question's classification block (v1.1)."""
    if cls is None:
        return
    if not isinstance(cls, dict):
        p.error("classification-type", f"{where}: classification must be an object or null")
        return
    _unknown_keys(cls, CLASSIFICATION_KEYS, p, f"{where}.classification")

    state = cls.get("state")
    if state not in CLASSIFICATION_STATES:
        p.error("classification-state", f"{where}: classification.state must be one of {sorted(CLASSIFICATION_STATES)}, got {state!r}")

    if "taxonomy" in cls and not isinstance(cls["taxonomy"], str):
        p.error("classification-taxonomy", f"{where}: classification.taxonomy must be a string")
    tax_id = cls.get("taxonomy") or default_tax_id

    tags = cls.get("tags")
    primary = cls.get("primary")
    tag_ids: list[str] = []

    if state == "done":
        if not isinstance(tags, list) or not tags:
            p.error("classification-tags", f"{where}: state=done needs a non-empty tags array")
            tags = []
        for i, tag in enumerate(tags):
            if not isinstance(tag, dict):
                p.error("classification-tag", f"{where}: tags[{i}] must be an object")
                continue
            _unknown_keys(tag, TAG_KEYS, p, f"{where}.classification.tags[{i}]")
            tid = tag.get("id")
            if not isinstance(tid, str) or not TOPIC_ID_RE.fullmatch(tid):
                p.error("classification-tag-id", f"{where}: tags[{i}].id={tid!r} is not a dotted topic id")
                continue
            if tid in tag_ids:
                p.error("classification-tag-dup", f"{where}: topic {tid!r} is listed twice")
            tag_ids.append(tid)
            if "weight" in tag and not (_is_num(tag["weight"]) and 0 < tag["weight"] <= 1):
                p.error("classification-weight", f"{where}: tags[{i}].weight must be in (0, 1], got {tag['weight']!r}")
        if not isinstance(primary, str) or not TOPIC_ID_RE.fullmatch(primary):
            p.error("classification-primary", f"{where}: state=done needs primary as a dotted topic id, got {primary!r}")
        elif tag_ids and primary not in tag_ids:
            p.error("classification-primary", f"{where}: primary={primary!r} is not among tags {sorted(tag_ids)}")
        elif len(tag_ids) > 1 and not any(
            isinstance(t, dict) and t.get("weight", 1) == 1 for t in tags
        ):
            p.warn("classification-weight", f"{where}: several topics but none carries weight 1, primary is ambiguous")
        if cls.get("source") in ("model", "rule") and "confidence" not in cls:
            p.warn("classification-confidence", f"{where}: machine-labelled without confidence, sampling review cannot triage")
    elif state == "pending":
        if tags or primary:
            p.error("classification-pending", f"{where}: state=pending must not carry tags/primary (nothing decided yet)")

    if "source" in cls and cls["source"] not in CLASSIFICATION_SOURCES:
        p.error("classification-source", f"{where}: source must be one of {sorted(CLASSIFICATION_SOURCES)}, got {cls['source']!r}")
    if "confidence" in cls and not (_is_num(cls["confidence"]) and 0 <= cls["confidence"] <= 1):
        p.error("classification-confidence", f"{where}: confidence must be a number in [0, 1]")
    if "reviewed" in cls and not isinstance(cls["reviewed"], bool):
        p.error("classification-reviewed", f"{where}: reviewed must be a boolean")

    probe = list(tag_ids)
    if isinstance(primary, str) and primary not in probe:
        probe.append(primary)
    if taxonomy is not None:
        for tid in probe:
            if not taxonomy.has(tid):
                p.error("classification-topic", f"{where}: topic {tid!r} is not in taxonomy {taxonomy.id!r}")
        if isinstance(primary, str) and taxonomy.has(primary) and "." not in primary:
            p.warn("classification-branch",
                   f"{where}: primary={primary!r} is a level-1 domain, file the question under a "
                   f"topic or tag inside it")
        if tax_id and tax_id != taxonomy.id:
            p.warn("classification-taxonomy", f"{where}: taxonomy={tax_id!r} but loaded {taxonomy.id!r}")
    elif probe and not p.taxonomy_unverified:
        p.taxonomy_unverified = True
        p.warn("classification-unverified", f"{where}: topic ids were not verified against any taxonomy file")


def _check_difficulty(value, p: Problems, where: str) -> None:
    """Validate a v1.1 difficulty object (legacy easy/medium/hard strings still pass)."""
    if value is None:
        return
    if isinstance(value, str):
        if value not in LEGACY_DIFFICULTY:
            p.error("difficulty-legacy", f"{where}.difficulty: {value!r} must be one of {sorted(LEGACY_DIFFICULTY)}")
        return
    if not isinstance(value, dict):
        p.error("difficulty-type", f"{where}.difficulty: must be \"easy|medium|hard\" or an object")
        return

    _unknown_keys(value, DIFFICULTY_KEYS, p, f"{where}.difficulty")

    level = value.get("level")
    if not _is_int(level) or not 1 <= level <= DIFFICULTY_LEVEL_MAX:
        p.error("difficulty-level",
                f"{where}.difficulty: level must be an integer 1-{DIFFICULTY_LEVEL_MAX}, got {level!r}")
        level = None

    scale = value.get("scale")
    if scale is not None and scale not in DIFFICULTY_SCALES:
        p.error("difficulty-scale", f"{where}.difficulty: scale={scale!r} must be one of {sorted(DIFFICULTY_SCALES)}")

    band = value.get("band")
    if band is not None:
        if band not in LEGACY_DIFFICULTY:
            p.error("difficulty-band", f"{where}.difficulty: band={band!r} must be one of {sorted(LEGACY_DIFFICULTY)}")
        elif level is not None and scale != "legacy5" and band != band_of_level(level):
            p.warn("difficulty-band",
                   f"{where}.difficulty: band={band} disagrees with level={level} "
                   f"(expected {band_of_level(level)})")

    score = value.get("score")
    if score is not None:
        if not _is_num(score) or not 1 <= score <= DIFFICULTY_SCORE_MAX:
            p.error("difficulty-score",
                    f"{where}.difficulty: score must be a number 1-{DIFFICULTY_SCORE_MAX}, got {score!r}")
            score = None
        elif level is not None and scale != "legacy5" and score_level(score) != level:
            p.warn("difficulty-score",
                   f"{where}.difficulty: score={score} implies level {score_level(score)}, but level={level}")

    method = value.get("method")
    if method is not None and method not in DIFFICULTY_METHODS:
        p.error("difficulty-method", f"{where}.difficulty: method={method!r} must be one of {sorted(DIFFICULTY_METHODS)}")

    conf = value.get("confidence")
    if conf is not None and (not _is_num(conf) or not 0 <= conf <= 1):
        p.error("difficulty-confidence", f"{where}.difficulty: confidence must be 0-1, got {conf!r}")

    comps = value.get("components")
    if comps is not None:
        if not isinstance(comps, list):
            p.error("difficulty-components", f"{where}.difficulty: components must be an array")
        elif len(comps) > 6:
            p.error("difficulty-components", f"{where}.difficulty: at most 6 components, got {len(comps)}")
        else:
            total_w = 0.0
            weighted = 0.0
            for i, c in enumerate(comps):
                cw = f"{where}.difficulty.components[{i}]"
                if not isinstance(c, dict):
                    p.error("difficulty-component", f"{cw}: must be an object")
                    continue
                _unknown_keys(c, DIFFICULTY_COMPONENT_KEYS, p, cw)
                if c.get("method") not in DIFFICULTY_METHODS - {"hybrid"}:
                    p.error("difficulty-component", f"{cw}: method must be one of {sorted(DIFFICULTY_METHODS - {'hybrid'})}")
                cs = c.get("score")
                # component scores live on the same 1-60 range as the fused score
                if not _is_num(cs) or not 1 <= cs <= DIFFICULTY_SCORE_MAX:
                    p.error("difficulty-component",
                            f"{cw}: score must be a number 1-{DIFFICULTY_SCORE_MAX}, got {cs!r}")
                    continue
                cwt = c.get("weight", 1.0)
                if not _is_num(cwt) or not 0 <= cwt <= 1:
                    p.error("difficulty-component", f"{cw}: weight must be 0-1, got {cwt!r}")
                    continue
                total_w += float(cwt)
                weighted += float(cs) * float(cwt)
            if total_w > 0 and score is not None:
                fused = weighted / total_w
                if abs(fused - float(score)) > 0.15:
                    p.warn("difficulty-weights",
                           f"{where}.difficulty: components fuse to {fused:.2f} but score={score} (check weights)")

    evidence = value.get("evidence")
    if evidence is not None:
        if not isinstance(evidence, dict):
            p.error("difficulty-evidence", f"{where}.difficulty: evidence must be an object")
        else:
            _unknown_keys(evidence, {"attempts"}, p, f"{where}.difficulty.evidence")
            attempts = evidence.get("attempts")
            if attempts is not None and (not _is_int(attempts) or attempts < 0):
                p.error("difficulty-evidence", f"{where}.difficulty: evidence.attempts must be an integer >= 0")

    reviewed = value.get("reviewed")
    if reviewed is not None and not isinstance(reviewed, bool):
        p.error("difficulty-reviewed", f"{where}.difficulty: reviewed must be a boolean")

    at = value.get("at")
    if at is not None and (not isinstance(at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", at)):
        p.error("difficulty-at", f"{where}.difficulty: at must be an ISO date YYYY-MM-DD")


def score_level(score: float) -> int:
    """Same scale as classifier/difficulty/prior.py:to_level (1-20+, open above 20)."""
    return int(min(DIFFICULTY_SCORE_MAX, max(1.0, round(float(score)))))


def _check_question(q, idx: int, p: Problems, paper_dir: Path, section_ids: set[str],
                    default_tax_id: str | None = None, taxonomy: Taxonomy | None = None) -> None:
    where = f"questions[{idx}]"
    if not isinstance(q, dict):
        p.error("question-type", f"{where}: must be an object")
        return
    _unknown_keys(q, QUESTION_KEYS, p, where)

    n = q.get("n")
    if not _is_int(n) or n < 1:
        p.error("question-n", f"{where}: n must be an integer >= 1")
    else:
        where = f"questions[{idx}] (n={n})"
        if n != idx + 1:
            p.warn("question-order", f"{where}: question numbers are not contiguous, expected n={idx + 1}")

    qtype = q.get("type")
    if qtype not in QUESTION_TYPES:
        p.error("question-type", f"{where}: type must be one of {sorted(QUESTION_TYPES)}, got {qtype!r}")

    if not isinstance(q.get("question"), str) or not q.get("question", "").strip():
        p.error("question-text", f"{where}: question is required and must be non-empty")
    if not _is_num(q.get("points")) or q.get("points", -1) < 0:
        p.error("question-points", f"{where}: points must be a number >= 0")

    if "qid" in q:
        qid = q["qid"]
        if not isinstance(qid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", qid):
            p.error("question-qid", f"{where}: qid must be 1-32 chars of [A-Za-z0-9_-]")

    sec = q.get("section")
    if sec is not None and section_ids and sec not in section_ids:
        p.error("question-section", f"{where}: section={sec!r} is not declared in top-level sections")

    choices, answer = q.get("choices"), q.get("answer")
    if qtype == "multiple_choice":
        if not isinstance(choices, dict) or len(choices) < 2:
            p.error("choice-missing", f"{where}: multiple_choice needs at least 2 choices")
        else:
            for letter in choices:
                if not re.fullmatch(r"[A-H]", letter):
                    p.error("choice-letter", f"{where}: choice keys must be A-H, got {letter!r}")
            if not isinstance(answer, str) or answer not in choices:
                p.error("choice-answer", f"{where}: answer={answer!r} is not among choices {sorted(choices)}")
    elif qtype == "integer_answer":
        if not isinstance(answer, str) or not re.fullmatch(r"-?[0-9]{1,15}", answer or ""):
            p.error("answer-format", f"{where}: integer_answer needs an integer string, e.g. \"028\" or \"-35\"")
    elif qtype == "numeric":
        try:
            float(str(answer))
        except (TypeError, ValueError):
            p.error("answer-format", f"{where}: numeric answer must parse as a number, got {answer!r} (put the unit in grading.unit)")
    elif qtype == "proof" and answer not in (None, ""):
        p.warn("answer-proof", f"{where}: proof questions usually have no answer, but answer={answer!r}")

    _check_figure(q.get("figure"), p, paper_dir, where)
    _check_classification(q.get("classification"), p, where, default_tax_id, taxonomy)
    _check_difficulty(q.get("difficulty"), p, where)


def validate(doc, path: Path, legacy_ok: bool = False) -> Problems:
    p = Problems(path)
    if not isinstance(doc, dict):
        p.error("root-type", "root must be an object")
        return p

    if "format_version" not in doc:
        if legacy_ok:
            p.warn("legacy", "no format_version: this is the legacy v0 shape (run --upgrade to convert)")
            return p
        p.error("format-version", "missing format_version (pass --legacy-ok for old papers, or --upgrade)")
        return p

    fv = doc.get("format_version")
    if not isinstance(fv, str) or not FORMAT_RE.fullmatch(fv):
        p.error("format-version", f"format_version={fv!r} does not match {FORMAT_RE.pattern}")
    elif fv not in SUPPORTED_FORMATS:
        p.warn("format-version", f"format_version={fv}, this validator targets {FORMAT_VERSION}")

    _unknown_keys(doc, TOP_KEYS, p, "root")

    pv = doc.get("paper_version")
    if not _is_int(pv) or pv < 1:
        p.error("paper-version", f"paper_version must be an integer >= 1, got {pv!r}")

    for key in ("id", "title"):
        if not isinstance(doc.get(key), str) or not doc.get(key, "").strip():
            p.error("required", f"missing required field {key}")

    pid = doc.get("id")
    if isinstance(pid, str):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", pid):
            p.error("id-format", f"id={pid!r} may only contain [A-Za-z0-9._-] and must not start with a symbol")
        else:
            # Upgrade output is written as <id>.v1.json, so ignore that suffix.
            stem = re.sub(r"\.v1$", "", path.stem)
            if stem != pid:
                p.warn("id-filename", f"id={pid!r} does not match file name {stem!r}")

    if "locale" in doc and doc["locale"] not in ("en", "zh"):
        p.error("locale", f"locale must be en or zh, got {doc['locale']!r}")

    section_ids: set[str] = set()
    sections = doc.get("sections")
    if sections is not None:
        if not isinstance(sections, list):
            p.error("sections-type", "sections must be an array")
        else:
            for i, sec in enumerate(sections):
                if not isinstance(sec, dict):
                    p.error("section-type", f"sections[{i}] must be an object")
                    continue
                sid = sec.get("id")
                if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,16}", sid):
                    p.error("section-id", f"sections[{i}]: invalid id")
                elif sid in section_ids:
                    p.error("section-dup", f"sections[{i}]: duplicate id {sid!r}")
                else:
                    section_ids.add(sid)

    tax_ref = doc.get("taxonomy")
    default_tax_id: str | None = None
    taxonomy: Taxonomy | None = None
    if tax_ref is not None:
        if not isinstance(tax_ref, dict):
            p.error("taxonomy-type", "root: taxonomy must be an object")
        else:
            if not isinstance(tax_ref.get("id"), str):
                p.error("taxonomy-id", "root: taxonomy.id is required")
            else:
                default_tax_id = tax_ref["id"]
            taxonomy = load_taxonomy(tax_ref, path.parent, p)

    questions = doc.get("questions")
    if not isinstance(questions, list) or not questions:
        p.error("questions", "questions must be a non-empty array")
        return p

    seen_qid: set[str] = set()
    seen_n: set[int] = set()
    for i, q in enumerate(questions):
        _check_question(q, i, p, path.parent, section_ids, default_tax_id, taxonomy)
        if isinstance(q, dict):
            if _is_int(q.get("n")):
                if q["n"] in seen_n:
                    p.error("question-dup", f"duplicate question number {q['n']}")
                seen_n.add(q["n"])
            qid = q.get("qid")
            if isinstance(qid, str):
                if qid in seen_qid:
                    p.error("qid-dup", f"duplicate qid {qid!r}")
                seen_qid.add(qid)
    if seen_qid and len(seen_qid) != len(questions):
        p.warn("qid-missing", "some questions have no qid: answers and version diffs lose their stable anchor")

    total = doc.get("total_points")
    if _is_num(total):
        summed = sum(q.get("points", 0) for q in questions if isinstance(q, dict) and _is_num(q.get("points", 0)))
        if abs(total - summed) > 1e-9:
            p.warn("total-points", f"total_points={total} != sum of question points {summed}")

    hist = doc.get("version_history")
    if isinstance(hist, list) and hist and _is_int(pv):
        versions = [h.get("version") for h in hist if isinstance(h, dict) and _is_int(h.get("version"))]
        if versions and max(versions) != pv:
            p.warn("version-history", f"version_history max version {max(versions)} != paper_version={pv}")

    if "content_hash" in doc:
        expected = content_hash(questions)
        if doc["content_hash"] != expected:
            p.warn("content-hash", f"content_hash is stale, expected {expected}")

    return p


def upgrade(doc: dict, path: Path, guess_figures: bool = True,
            mark_pending: bool = False) -> tuple[dict, list[str]]:
    """Legacy (no version fields) -> v1.1. Returns (new document, notes)."""
    notes: list[str] = []
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    questions = []
    for i, q in enumerate(doc.get("questions", [])):
        if not isinstance(q, dict):
            continue
        n = q.get("n") if _is_int(q.get("n")) else i + 1
        new = {"n": n, "qid": q.get("qid") or f"q{n:02d}"}
        for key in QUESTION_KEYS - {"n", "qid", "figure"}:
            if key in q:
                new[key] = q[key]
        new.setdefault("type", "multiple_choice" if q.get("choices") else "integer_answer")
        new.setdefault("points", 1)
        if guess_figures and DIAGRAM_HINT.search(str(q.get("question", ""))):
            new["figure"] = {
                "kind": "svg",
                "state": "placeholder",
                "placement": "prompt",
                "width": 320,
                "height": 240,
                "alt": "TODO: original problem has a figure, redraw it here",
            }
            notes.append(f"q{n}: prompt mentions diagram/figure -> reserved a placeholder slot")
        else:
            new["figure"] = None
        if mark_pending:
            new["classification"] = {"state": "pending"}
        questions.append(new)

    out = {
        "format_version": FORMAT_VERSION,
        "paper_version": 1,
        "id": doc.get("id") or path.stem,
        "title": doc.get("title") or path.stem,
        "questions": questions,
        "version_history": [
            {"version": 1, "at": now, "by": "upgrade", "note": "converted from legacy v0 (no version fields)"}
        ],
        "updated_at": now,
    }
    for key in ("competition", "category", "instructions", "time_limit_min",
                "total_points", "calculator_allowed", "locale", "notes", "created_at"):
        if key in doc:
            out[key] = doc[key]
    out.setdefault("created_at", now)
    out["content_hash"] = content_hash(questions)
    return out, notes


def _root_of(taxonomy: "Taxonomy", node_id: str) -> str:
    """Walk up the parent chain to the level-1 domain."""
    cur = node_id
    seen = set()
    while cur not in seen:
        seen.add(cur)
        parent = taxonomy.nodes.get(cur)
        if not parent:
            return cur
        cur = parent
    return cur


def _taxonomy_shape(taxonomy: "Taxonomy") -> str:
    by_level: dict[int, int] = {}
    for nid in taxonomy.nodes:
        level = nid.count(".") + 1
        by_level[level] = by_level.get(level, 0) + 1
    parts = " ".join(f"L{lv}={n}" for lv, n in sorted(by_level.items()))
    return f"{taxonomy.id} v{taxonomy.version} ({parts})"


def report_coverage(doc, taxonomy: "Taxonomy | None" = None) -> None:
    """Print how much of a paper is classified (v1.1)."""
    qs = [q for q in doc.get("questions") or [] if isinstance(q, dict)]
    done, pending, reviewed = [], 0, 0
    primaries: dict[str, int] = {}
    for q in qs:
        cls = q.get("classification")
        if not isinstance(cls, dict):
            continue
        if cls.get("state") == "done":
            done.append(cls)
            if cls.get("reviewed"):
                reviewed += 1
            tid = cls.get("primary")
            if isinstance(tid, str):
                primaries[tid] = primaries.get(tid, 0) + 1
        elif cls.get("state") == "pending":
            pending += 1
    total = len(qs)
    untouched = total - len(done) - pending
    print(f"  coverage: {len(done)}/{total} classified, {pending} pending, "
          f"{untouched} not considered, {reviewed} reviewed")
    if taxonomy is not None:
        print(f"  taxonomy: {_taxonomy_shape(taxonomy)}")
    shown = sorted(primaries.items(), key=lambda kv: (-kv[1], kv[0]))
    if taxonomy is not None:
        domains: dict[str, int] = {}
        for tid, count in primaries.items():
            if taxonomy.has(tid):
                top = _root_of(taxonomy, tid)
                domains[top] = domains.get(top, 0) + count
        if domains:
            print("  by domain:")
            for top, count in sorted(domains.items(), key=lambda kv: (-kv[1], kv[0])):
                print(f"    {count:5d}  {top}")
    if shown:
        print("  top primary topics:")
        for tid, count in shown[:8]:
            print(f"    {count:5d}  {tid}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate / upgrade MockTest paper JSON (format v1.0)")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--legacy-ok", action="store_true", help="accept papers without format_version (warn only)")
    ap.add_argument("--upgrade", action="store_true", help="convert a legacy paper to v1.0, written as <name>.v1.json")
    ap.add_argument("--no-guess-figures", action="store_true", help="do not reserve figure slots from prompt keywords")
    ap.add_argument("--hash", action="store_true", help="print the recomputed content_hash")
    ap.add_argument("--coverage", action="store_true", help="report classification coverage")
    ap.add_argument("--mark-pending", action="store_true",
                    help="with --upgrade: seed classification={state:pending} on every question")
    ap.add_argument("--quiet", action="store_true", help="errors only")
    args = ap.parse_args(argv)

    rc = 0
    for path in args.files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{path}: unreadable: {exc}")
            rc = max(rc, 2)
            continue

        if args.hash:
            print(content_hash(doc.get("questions", [])))
            continue

        if args.upgrade:
            if "format_version" in doc:
                print(f"{path}: already v{doc.get('format_version')}, skipped")
                continue
            new, notes = upgrade(doc, path, guess_figures=not args.no_guess_figures,
                                 mark_pending=args.mark_pending)
            out = path.with_suffix(".v1.json")
            out.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"{path}: upgraded -> {out.name}")
            for note in notes:
                print(f"  note: {note}")
            continue

        p = validate(doc, path, legacy_ok=args.legacy_ok)
        if p.errors or (p.warnings and not args.quiet):
            print(f"{path}")
            for level, code, msg in p.items:
                if args.quiet and level == "warn":
                    continue
                print(f"  {'ERROR' if level == 'error' else 'WARN '} [{code}] {msg}")
        print(f"  -> {'OK' if not p.errors else 'FAILED'} ({p.errors} error, {p.warnings} warn)")
        if args.coverage:
            tax = load_taxonomy(doc.get("taxonomy"), path.parent, Problems(path))
            report_coverage(doc, tax)
        if p.errors:
            rc = max(rc, 1)
    return rc


if __name__ == "__main__":
    sys.exit(main())

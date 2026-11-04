#!/usr/bin/env python3
"""Validate (and upgrade) MockTest Maker paper JSON against format v1.0.

    python scripts/validate_paper.py examples/demo_rand_01.json
    python scripts/validate_paper.py users/test/tests/*.json --legacy-ok
    python scripts/validate_paper.py users/test/tests/amc8_rand_01.json --upgrade
    python scripts/validate_paper.py examples/demo_rand_01.json --hash

Standard library only, same policy as app/server.py.
Exit code: 0 = clean (warnings allowed), 1 = errors, 2 = unreadable input.

The schema lives in schema/paper-1.0.schema.json; this script re-implements the
rules JSON Schema cannot express (cross references, asset existence, answer vs
choices consistency) so it works without a jsonschema dependency.

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

FORMAT_VERSION = "1.0"
FORMAT_RE = re.compile(r"^1\.\d+$")

TOP_KEYS = {
    "format_version", "paper_version", "id", "title", "competition", "category",
    "instructions", "time_limit_min", "total_points", "calculator_allowed",
    "locale", "created_at", "updated_at", "generator", "version_history",
    "sections", "questions", "content_hash", "notes",
}
QUESTION_KEYS = {
    "n", "qid", "section", "type", "source", "question", "question_zh", "choices",
    "answer", "solution", "solution_zh", "points", "grading", "figure", "subject",
    "difficulty",
}
FIGURE_KEYS = {
    "kind", "state", "placement", "src", "inline", "mime", "sha256", "width",
    "height", "viewBox", "alt", "caption", "credit", "source_code",
}
QUESTION_TYPES = {"multiple_choice", "integer_answer", "numeric", "proof"}
FIGURE_KINDS = {"svg", "image"}
FIGURE_STATES = {"ready", "placeholder"}
PLACEMENTS = {"prompt", "solution", "both"}

# Same heuristic the bank builders use for has_diagram. Used when upgrading a
# legacy paper so geometry problems get a reserved figure slot.
DIAGRAM_HINT = re.compile(r"\bdiagram\b|\bfigure\b|\bshown\b|如图|图中", re.IGNORECASE)


class Problems:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.items: list[tuple[str, str, str]] = []

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


def content_hash(questions: list) -> str:
    """sha256 over the canonical JSON of the questions array.

    Canonical = UTF-8, keys sorted, no spaces, ensure_ascii=False. Assets are
    covered through their inline/src/sha256 fields, so swapping a file changes
    the hash as long as the asset's sha256 is maintained.
    """
    blob = json.dumps(questions, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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


def _check_question(q, idx: int, p: Problems, paper_dir: Path, section_ids: set[str]) -> None:
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
    elif fv != FORMAT_VERSION:
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

    questions = doc.get("questions")
    if not isinstance(questions, list) or not questions:
        p.error("questions", "questions must be a non-empty array")
        return p

    seen_qid: set[str] = set()
    seen_n: set[int] = set()
    for i, q in enumerate(questions):
        _check_question(q, i, p, path.parent, section_ids)
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


def upgrade(doc: dict, path: Path, guess_figures: bool = True) -> tuple[dict, list[str]]:
    """Legacy (no version fields) -> v1.0. Returns (new document, notes)."""
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate / upgrade MockTest paper JSON (format v1.0)")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--legacy-ok", action="store_true", help="accept papers without format_version (warn only)")
    ap.add_argument("--upgrade", action="store_true", help="convert a legacy paper to v1.0, written as <name>.v1.json")
    ap.add_argument("--no-guess-figures", action="store_true", help="do not reserve figure slots from prompt keywords")
    ap.add_argument("--hash", action="store_true", help="print the recomputed content_hash")
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
            new, notes = upgrade(doc, path, guess_figures=not args.no_guess_figures)
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
        if p.errors:
            rc = max(rc, 1)
    return rc


if __name__ == "__main__":
    sys.exit(main())

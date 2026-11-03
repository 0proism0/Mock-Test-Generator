#!/usr/bin/env python3
"""Migrate bank/*.json to the v1.0 bank format (aligned with paper format v1.0).

Reads  bank/<name>.json   ({competition, set, variants[]})
Writes bank/<name>.v1.json by default. Originals are never touched.

What changes per variant
------------------------
* qid        stable content id: "q" + sha1(source \\0 question)[:12]
             stable across runs, unaffected by position/renumbering
* type       normalized to the schema enum
             (multiple_choice | integer_answer | numeric | proof);
             legacy "integer" -> "integer_answer"; missing -> inferred
* figure     null when the item has no figure, otherwise a placeholder slot
             (from the legacy has_diagram flag) carrying width/height/alt
* has_diagram dropped: superseded by figure
* "" answers normalized to null (proof problems)

Output is ASCII-only on the console: the Windows console here is GBK and
would mangle Chinese diagnostics.

Usage
-----
  python scripts/migrate_banks.py --dry-run      # report only, write nothing
  python scripts/migrate_banks.py                # write bank/*.v1.json
  python scripts/migrate_banks.py --check        # re-verify existing *.v1.json
  python scripts/migrate_banks.py --stats        # per-bank numbers
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK_DIR = ROOT / "bank"
OUT_SUFFIX = ".v1.json"
FORMAT_VERSION = "1.0"
BANK_VERSION = 1

TYPES = ("multiple_choice", "integer_answer", "numeric", "proof")
LETTERS = set("ABCDEFGH")
INT_RE = re.compile(r"^-?[0-9]{1,15}$")
NUM_RE = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
# "7.0 ms^{-1}", "15 hours", "0.20 m" -> number + unit
NUM_UNIT_RE = re.compile(r"^\s*(-?[0-9]+(?:\.[0-9]+)?)\s*(.+?)\s*$")

PLACEHOLDER_W = 320
PLACEHOLDER_H = 240
PLACEHOLDER_ALT = "TODO: original problem has a figure; redraw it here."


def qid_for(source: str, question: str) -> str:
    """Stable content id, independent of position and file name."""
    h = hashlib.sha1(f"{source}\0{question}".encode("utf-8")).hexdigest()
    return "q" + h[:12]


def unique_qid(base: str, seen: dict[str, int]) -> str:
    """Disambiguate genuine duplicate rows in a bank (-2, -3, ...).

    A few banks carry the same problem twice (scraper artifact). The first
    occurrence keeps the plain content id; later ones get a deterministic
    occurrence suffix so answer records never collide.
    """
    n = seen.get(base, 0) + 1
    seen[base] = n
    return base if n == 1 else f"{base}-{n}"


def norm_answer(ans):
    if ans is None:
        return None
    if isinstance(ans, str) and ans.strip() == "":
        return None
    return ans


def infer_type(v: dict, notes: list[str]) -> str:
    """Map a legacy `type` onto the v1.0 enum, inferring when absent."""
    raw = v.get("type")
    choices = v.get("choices")
    answer = norm_answer(v.get("answer"))
    n_choices = len(choices) if isinstance(choices, dict) else 0

    if raw == "integer":
        notes.append("type: integer -> integer_answer")
        return "integer_answer"
    if raw in TYPES:
        if raw == "multiple_choice" and n_choices < 2:
            notes.append(f"type: multiple_choice with {n_choices} choices -> downgraded")
            return infer_type({**v, "type": None}, notes)
        return raw

    # missing / unknown: infer from the data
    if n_choices >= 2 and isinstance(answer, str) and answer in LETTERS:
        notes.append("type: missing -> multiple_choice (inferred)")
        return "multiple_choice"
    if isinstance(answer, str) and INT_RE.match(answer):
        notes.append("type: missing -> integer_answer (inferred)")
        return "integer_answer"
    if isinstance(answer, str) and NUM_RE.match(answer):
        notes.append("type: missing -> numeric (inferred)")
        return "numeric"
    if isinstance(answer, str) and NUM_UNIT_RE.match(answer):
        notes.append("type: missing -> numeric with unit (inferred)")
        return "numeric"
    notes.append("type: missing -> proof (no answer, no choices)")
    return "proof"


def figure_for(v: dict) -> dict | None:
    """Placeholder slot for problems whose statement refers to a figure."""
    if v.get("has_diagram") is not True:
        return None
    return {
        "kind": "svg",
        "state": "placeholder",
        "placement": "prompt",
        "width": PLACEHOLDER_W,
        "height": PLACEHOLDER_H,
        "alt": PLACEHOLDER_ALT,
    }


def migrate_variant(v: dict, notes: list[str], seen: dict[str, int]) -> dict:
    qtype = infer_type(v, notes)
    answer = norm_answer(v.get("answer"))
    grading = None
    legacy_answer = None

    # Physics answers carry their unit inline ("7.0 ms^{-1}"). The v1.0 schema
    # keeps the number in answer and the unit in grading.unit.
    if qtype == "numeric" and isinstance(answer, str) and not NUM_RE.match(answer):
        m = NUM_UNIT_RE.match(answer)
        if m:
            legacy_answer = answer
            answer = m.group(1)
            grading = {"mode": "numeric_tolerance", "unit": m.group(2)}
            notes.append(f"answer: split unit {m.group(2)!r} into grading.unit")

    out = {
        "position": v["position"],
        "qid": unique_qid(qid_for(v.get("source", ""), v.get("question", "")), seen),
        "source": v.get("source"),
        "type": qtype,
        "question": v.get("question"),
    }
    if v.get("question_zh") is not None:
        out["question_zh"] = v["question_zh"]

    choices = v.get("choices")
    out["choices"] = choices if (isinstance(choices, dict) and choices) else None
    out["answer"] = answer
    if grading is not None:
        out["grading"] = grading
    out["solution"] = v.get("solution")
    if v.get("solution_zh") is not None:
        out["solution_zh"] = v["solution_zh"]
    if v.get("points") is not None:
        out["points"] = v["points"]
    if v.get("subject") is not None:
        out["subject"] = v["subject"]
    out["figure"] = figure_for(v)
    if legacy_answer is not None:
        out["x-legacy_answer"] = legacy_answer
    return out


def validate_variant(v: dict, where: str, errors: list[str]) -> None:
    if v["type"] not in TYPES:
        errors.append(f"{where}: bad type {v['type']!r}")
    if not v.get("question"):
        errors.append(f"{where}: empty question")
    if v["type"] == "multiple_choice":
        ch = v.get("choices")
        if not isinstance(ch, dict) or len(ch) < 2:
            errors.append(f"{where}: multiple_choice without choices")
        elif v.get("answer") not in ch:
            errors.append(f"{where}: answer {v.get('answer')!r} not among choices")
    if v["type"] == "integer_answer":
        a = v.get("answer")
        if not (isinstance(a, str) and INT_RE.match(a)):
            errors.append(f"{where}: integer_answer with bad answer {a!r}")
    if v["type"] == "numeric":
        a = v.get("answer")
        if not (isinstance(a, str) and NUM_RE.match(a)):
            errors.append(f"{where}: numeric with bad answer {a!r}")
        g = v.get("grading")
        if g is not None and g.get("mode") not in (None, "numeric_tolerance", "exact"):
            errors.append(f"{where}: numeric with unexpected grading.mode {g.get('mode')!r}")
    if not re.match(r"^[A-Za-z0-9_-]{1,32}$", v["qid"]):
        errors.append(f"{where}: bad qid {v['qid']!r}")
    fig = v.get("figure")
    if fig is not None:
        if fig.get("state") == "placeholder" and ("src" in fig or "inline" in fig):
            errors.append(f"{where}: placeholder must not carry src/inline")
        if not fig.get("alt"):
            errors.append(f"{where}: figure without alt")
        if not fig.get("width") or not fig.get("height"):
            errors.append(f"{where}: figure without width/height")


def migrate_file(path: Path, out_path: Path, write: bool, errors: list[str], notes: list[str]):
    raw = json.loads(path.read_text(encoding="utf-8"))
    variants_in = raw.get("variants") or []
    variants_out = []
    seen: dict[str, int] = {}
    for i, v in enumerate(variants_in, 1):
        where = f"{path.name}[{i}] pos={v.get('position')}"
        notes_local: list[str] = []
        mv = migrate_variant(v, notes_local, seen)
        validate_variant(mv, where, errors)
        for n in notes_local:
            notes.append(f"{where}: {n}")
        variants_out.append(mv)

    doc = {
        "format_version": FORMAT_VERSION,
        "bank_version": BANK_VERSION,
        "competition": raw.get("competition"),
        "set": raw.get("set"),
        "source_file": path.name,
        "count": len(variants_out),
        "figure_slots": sum(1 for v in variants_out if v.get("figure")),
        "variants": variants_out,
    }
    if write:
        out_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate bank/*.json to bank v1.0")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--check", action="store_true", help="verify existing *.v1.json")
    ap.add_argument("--stats", action="store_true", help="print per-bank numbers")
    ap.add_argument("--notes", action="store_true", help="print every inferred type change")
    args = ap.parse_args()

    if args.check:
        files = sorted(BANK_DIR.glob("*" + OUT_SUFFIX))
        if not files:
            print("no *.v1.json files found")
            return 1
    else:
        files = sorted(p for p in BANK_DIR.glob("*.json") if not p.name.endswith(OUT_SUFFIX))

    errors: list[str] = []
    notes: list[str] = []
    total = 0
    figs = 0
    rows = []

    for path in files:
        out_path = path.with_name(path.name[: -len(".json")] + OUT_SUFFIX)
        if args.check:
            doc = json.loads(path.read_text(encoding="utf-8"))
            for i, v in enumerate(doc.get("variants") or [], 1):
                validate_variant(v, f"{path.name}[{i}]", errors)
            n = len(doc.get("variants") or [])
            f = doc.get("figure_slots", 0)
        else:
            doc = migrate_file(path, out_path, not args.dry_run, errors, notes)
            n = doc["count"]
            f = doc["figure_slots"]
        total += n
        figs += f
        rows.append((path.name, n, f))

    if args.stats:
        print(f"{'bank':24s} {'items':>6s} {'figures':>8s}")
        for name, n, f in rows:
            print(f"{name:24s} {n:6d} {f:8d}")

    mode = "CHECK" if args.check else ("DRY-RUN" if args.dry_run else "WRITE")
    print(f"\n[{mode}] files={len(files)} variants={total} figure_slots={figs}")
    if notes:
        print(f"type adjustments: {len(notes)}")
        if args.notes:
            for n in notes:
                print("  " + n)
    if errors:
        print(f"\nFAILED: {len(errors)} error(s)")
        for e in errors[:40]:
            print("  " + e)
        if len(errors) > 40:
            print(f"  ... and {len(errors) - 40} more")
        return 1
    print("OK (0 errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

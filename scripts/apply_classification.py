#!/usr/bin/env python3
"""Write classifier output back into bank/v2/*.json.

Reads classifier/out/<bank>_v2.jsonl (one JSON row per question, the last row
for a qid wins) and stamps `classification` + `difficulty` onto the matching
bank variant. The bank files stay the single source of truth: this script only
copies the two annotation fields, it never touches question text, choices,
answers, solutions, figures or points.

Output is ASCII only (the console is GBK).

Usage:
  python scripts/apply_classification.py --stats      # what would change
  python scripts/apply_classification.py --dry-run    # same, nothing written
  python scripts/apply_classification.py              # write the banks
  python scripts/apply_classification.py --check      # verify banks are current
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK_DIR = ROOT / "bank" / "v2"
OUT_DIR = ROOT / "classifier" / "out"
SCALE = "amc20"
ANNOTATION_KEYS = ("classification", "difficulty")
DATE = time.strftime("%Y-%m-%d")


def load_rows(out_dir: Path) -> dict:
    """qid -> classifier row, last row wins (runs are append-only)."""
    rows: dict = {}
    for path in sorted(out_dir.glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            qid = row.get("qid")
            if qid:
                rows[qid] = row
    return rows


def is_usable(row: dict) -> bool:
    """Only rows produced by the current scale and actually classified."""
    if not row:
        return False
    if (row.get("classification") or {}).get("state") != "done":
        return False
    return (row.get("difficulty") or {}).get("scale") == SCALE


def stamp(doc: dict, rows: dict, tax_ref: dict, with_issues: bool) -> tuple[int, int]:
    """Copy annotations onto variants. Returns (applied, unknown_qids)."""
    applied = 0
    missing: set = set()
    for v in doc.get("variants") or []:
        qid = v.get("qid")
        row = rows.get(qid) if qid else None
        if not is_usable(row):
            missing.add(qid)
            continue
        for key in ANNOTATION_KEYS:
            if row.get(key):
                v[key] = copy.deepcopy(row[key])
        if with_issues and row.get("issue"):
            v["x-issue"] = copy.deepcopy(row["issue"])
        applied += 1
    if applied:
        doc["taxonomy"] = dict(tax_ref)
        doc["classified_at"] = DATE
    return applied, len(missing)


def tax_ref_of(rows: dict) -> dict:
    for row in rows.values():
        cls = row.get("classification") or {}
        if cls.get("state") == "done" and cls.get("taxonomy"):
            return {"id": cls["taxonomy"], "version": cls.get("taxonomy_version") or "1.0"}
    return {"id": "amc-v1", "version": "1.0"}


def _validator():
    path = ROOT / "scripts" / "validate_paper.py"
    spec = importlib.util.spec_from_file_location("validate_paper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def verify(doc: dict, path: Path, tax_ref: dict) -> tuple[int, int]:
    """Run the paper-format rules over the annotations now in the bank."""
    vp = _validator()
    p = vp.Problems(path)
    tax = vp.load_taxonomy(tax_ref, path.parent, p)
    errors = p.errors
    warnings = p.warnings
    for v in doc.get("variants") or []:
        where = f"qid={v.get('qid')} pos={v.get('position')}"
        if v.get("classification"):
            vp._check_classification(v["classification"], p, where,
                                     tax_ref.get("id"), tax)
        if v.get("difficulty"):
            vp._check_difficulty(v["difficulty"], p, where)
    return p.errors - errors, p.warnings - warnings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Stamp classification/difficulty into bank/v2/*.json")
    ap.add_argument("--bank-dir", type=Path, default=BANK_DIR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    ap.add_argument("--check", action="store_true", help="exit 1 if a bank is behind its jsonl")
    ap.add_argument("--stats", action="store_true", help="per-bank counts only")
    ap.add_argument("--with-issues", action="store_true",
                    help="also copy the model's defect report into x-issue")
    ap.add_argument("--verify", action="store_true", default=True,
                    help="run paper-format checks on the annotations (default: on)")
    args = ap.parse_args(argv)

    rows = load_rows(args.out_dir)
    usable = {k: v for k, v in rows.items() if is_usable(v)}
    tax_ref = tax_ref_of(rows)
    print(f"[rows] {len(rows)} qids, {len(usable)} usable (scale={SCALE})")
    if not usable:
        print("[abort] no usable classifier rows")
        return 2

    files = sorted(args.bank_dir.glob("*.json"))
    if not files:
        print(f"[abort] no bank files under {args.bank_dir}")
        return 2

    stale = 0
    err_total = 0
    warn_total = 0
    for path in files:
        raw = path.read_text(encoding="utf-8")
        doc = json.loads(raw)
        before = json.dumps(doc, ensure_ascii=False, sort_keys=True)
        applied, missing = stamp(doc, usable, tax_ref, args.with_issues)
        after = json.dumps(doc, ensure_ascii=False, sort_keys=True)
        changed = before != after

        if args.check:
            if changed:
                stale += 1
                print(f"[stale] {path.name}: bank differs from classifier output "
                      f"(applied would be {applied}, unclassified {missing})")
            else:
                print(f"[ok]    {path.name}: up to date ({applied} annotated)")
            continue

        line = f"[bank]  {path.name}: annotate={applied} unclassified={missing} changed={changed}"
        if args.dry_run or args.stats or not changed:
            print(line)
        if args.dry_run or not changed:
            continue

        if args.verify:
            errs, warns = verify(doc, path, doc.get("taxonomy") or tax_ref)
            err_total += errs
            warn_total += warns
            line += f" verify_errors={errs} verify_warnings={warns}"
            print(line)
        else:
            print(line)

        # keep the original on-disk shape: indent=1, no trailing newline, LF
        # the bank files use LF, and write_text() would translate to CRLF on Windows
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="")

    if args.check:
        print("[check] OK (all banks up to date)" if not stale else f"[check] {stale} bank(s) stale")
        return 0 if not stale else 1
    if args.dry_run or args.stats:
        print("[dry-run] nothing written" if args.dry_run else "[stats] nothing written")
        return 0
    if err_total:
        print(f"[verify] {err_total} error(s), {warn_total} warning(s)")
        return 1
    print(f"[verify] OK (0 errors, {warn_total} warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

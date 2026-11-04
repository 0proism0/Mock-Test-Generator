#!/usr/bin/env python3
"""Import AutoAOPS paper-format exports as bank version 2.

The AutoAOPS project exports one JSON per contest paper (schema/paper-1.0)
plus a ``figures/`` folder of SVGs.  This script folds those papers into the
bank shape app/server.py already understands, so the generator can offer a
second, figure-carrying bank version next to the classic one.

    bank/v2/amc10.json        one file per competition slug
    bank/v2/figures/*.svg     every figure referenced by those banks

Version 1 banks (bank/<slug>_*.json) are never touched: the two versions live
side by side and the UI picks one at generation time.

Usage:
    python scripts/import_papers.py --source "C:/Users/xiang/Projects/AutoAOPS/papers"
    python scripts/import_papers.py --dry-run          # report only, write nothing
    python scripts/import_papers.py --check            # validate an existing import

Console output is ASCII only: the Windows console here is GBK and would mangle
non-ASCII diagnostics.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"C:\Users\xiang\Projects\AutoAOPS\papers")
OUT_DIR = ROOT / "bank" / "v2"
FIGURES_DIR = OUT_DIR / "figures"

BANK_VERSION = 2
FORMAT_VERSION = "1.0"

# competition string in the export -> slug used by app/server.py (COMP_META)
SLUG_BY_COMPETITION = {
    "AMC 8": "amc8",
    "AMC 10": "amc10",
    "AMC 12": "amc12",
    "AHSME": "amc10",
}

PROOF = "proof"


def die(msg: str) -> None:
    print(f"[FAIL] {msg}")
    sys.exit(1)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalise_figure(fig: dict, paper_id: str) -> dict:
    """Keep only what the renderer needs; make src relative to the bank file."""
    src = fig.get("src") or ""
    if not src.startswith("figures/"):
        src = "figures/" + Path(src).name
    out = {
        "kind": fig.get("kind") or "svg",
        "state": fig.get("state") or "ready",
        "placement": fig.get("placement") or "prompt",
        "src": src,
        "mime": fig.get("mime") or "image/svg+xml",
        "alt": fig.get("alt") or f"{paper_id} figure",
    }
    for key in ("width", "height", "viewBox", "sha256"):
        if fig.get(key) not in (None, ""):
            out[key] = fig[key]
    if fig.get("state") == "placeholder":
        out.pop("src", None)
    return out


def variant_from_question(q: dict, paper_id: str) -> dict:
    v = {
        "position": q.get("n"),
        "qid": q.get("qid") or f"{paper_id}-q{q.get('n'):02d}",
        "source": q.get("source") or paper_id,
        "type": q.get("type") or "multiple_choice",
        "question": q.get("question") or "",
        "choices": q.get("choices"),
        "answer": q.get("answer"),
        "solution": q.get("solution"),
        "points": q.get("points"),
    }
    if q.get("figure"):
        v["figure"] = normalise_figure(q["figure"], paper_id)
    return v


def collect(source: Path):
    """Read every paper and group its questions by competition slug."""
    index_path = source / "index.json"
    if not index_path.exists():
        die(f"no index.json under {source}")
    papers = load_json(index_path).get("papers") or []
    if not papers:
        die("index.json lists no papers")

    by_slug: dict[str, list[dict]] = defaultdict(list)
    figure_files: set[str] = set()
    stats = Counter()
    skipped_comp: Counter = Counter()
    problems: list[str] = []

    for entry in papers:
        pid = entry.get("id")
        path = source / f"{pid}.json"
        if not path.exists():
            problems.append(f"{pid}: missing paper file")
            continue
        paper = load_json(path)
        slug = SLUG_BY_COMPETITION.get(paper.get("competition") or "")
        if not slug:
            skipped_comp[paper.get("competition") or "?"] += 1
            continue
        questions = paper.get("questions") or []
        if not questions:
            problems.append(f"{pid}: no questions")
            continue
        positions = set()
        for q in questions:
            v = variant_from_question(q, pid)
            if not isinstance(v["position"], int) or v["position"] < 1:
                problems.append(f"{pid}: bad position {v['position']!r}")
                continue
            positions.add(v["position"])
            # A question with no answer can never be graded, so it is useless to
            # the generator: drop it here instead of letting it reach a test.
            if not v["answer"]:
                stats["no_answer"] += 1
                continue
            if v["choices"] is not None and not isinstance(v["choices"], dict):
                problems.append(f"{pid} q{v['position']}: choices is not a dict")
            if v["choices"] and v["answer"] not in v["choices"]:
                problems.append(f"{pid} q{v['position']}: answer {v['answer']!r} not in choices")
            if v.get("figure") and v["figure"].get("src"):
                figure_files.add(Path(v["figure"]["src"]).name)
                stats["figures"] += 1
            if not v["solution"]:
                stats["no_solution"] += 1
            if v["type"] == PROOF:
                stats["proof"] += 1
            by_slug[slug].append(v)
        missing = sorted(set(range(1, len(questions) + 1)) - positions)
        if missing:
            problems.append(f"{pid}: missing positions {missing}")
        stats["papers"] += 1
        stats["questions"] += len(questions)

    if skipped_comp:
        print("[warn] skipped competitions with no slug mapping: "
              + ", ".join(f"{k}={v}" for k, v in skipped_comp.items()))
    return by_slug, figure_files, stats, problems


def coverage_report(slug: str, variants: list[dict]) -> list[str]:
    """Which positions survive the generator's eligibility filter."""
    eligible = [v for v in variants
                if v.get("solution") and v.get("type") != PROOF]
    per_pos = Counter(v["position"] for v in eligible)
    gaps = [p for p in range(1, 26) if per_pos.get(p, 0) == 0]
    lines = [
        f"  {slug}: variants={len(variants)} eligible={len(eligible)} "
        f"figures={sum(1 for v in variants if v.get('figure'))} "
        f"positions={len(per_pos)} min_per_pos={min(per_pos.values()) if per_pos else 0}"
    ]
    if gaps:
        lines.append(f"    WARNING uncovered positions: {gaps}")
    return lines


def write_bank(slug: str, variants: list[dict], dry_run: bool) -> Path:
    variants.sort(key=lambda v: (v["position"], v["source"]))
    payload = {
        "format_version": FORMAT_VERSION,
        "bank_version": BANK_VERSION,
        "slug": slug,
        "set": "v2",
        "source": "AutoAOPS papers export (paper-format 1.0)",
        "count": len(variants),
        "figure_count": sum(1 for v in variants if v.get("figure")),
        "variants": variants,
    }
    target = OUT_DIR / f"{slug}.json"
    if not dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    return target


def copy_figures(source: Path, names: set[str], dry_run: bool) -> tuple[int, int]:
    copied = missing = 0
    if not dry_run:
        FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for name in sorted(names):
        src = source / "figures" / name
        if not src.exists():
            print(f"[warn] figure not found: {name}")
            missing += 1
            continue
        if not dry_run:
            shutil.copyfile(src, FIGURES_DIR / name)
        copied += 1
    return copied, missing


def check() -> int:
    """Validate an existing bank/v2 import."""
    files = sorted(OUT_DIR.glob("*.json"))
    if not files:
        die(f"nothing to check under {OUT_DIR}")
    errors = 0
    for f in files:
        d = load_json(f)
        variants = d.get("variants") or []
        print(f"[check] {f.name}: count={len(variants)} "
              f"figure_count={sum(1 for v in variants if v.get('figure'))}")
        for v in variants:
            fig = v.get("figure")
            if fig and fig.get("src"):
                p = OUT_DIR / fig["src"]
                if not p.exists():
                    print(f"  [error] {f.name} {v.get('qid')}: missing figure {fig['src']}")
                    errors += 1
            if v.get("choices") and v.get("answer") not in v["choices"]:
                print(f"  [error] {f.name} {v.get('qid')}: answer not in choices")
                errors += 1
    print(f"[check] {'OK' if errors == 0 else 'FAILED'} ({errors} errors)")
    return 0 if errors == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(DEFAULT_SOURCE),
                    help="AutoAOPS papers directory (contains index.json)")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--check", action="store_true", help="validate an existing import")
    args = ap.parse_args()

    if args.check:
        return check()

    source = Path(args.source)
    if not source.is_dir():
        die(f"source directory not found: {source}")

    print(f"[read] {source}")
    by_slug, figure_files, stats, problems = collect(source)
    print(f"[stats] papers={stats['papers']} questions={stats['questions']} "
          f"figures={stats['figures']} no_solution={stats['no_solution']} "
          f"no_answer_dropped={stats['no_answer']} proof={stats['proof']}")

    for slug in sorted(by_slug):
        for line in coverage_report(slug, by_slug[slug]):
            print(line)

    copied, missing = copy_figures(source, figure_files, args.dry_run)
    print(f"[figures] copied={copied} missing={missing} -> {FIGURES_DIR}")

    for slug in sorted(by_slug):
        target = write_bank(slug, by_slug[slug], args.dry_run)
        print(f"[write] {target} ({len(by_slug[slug])} variants)")

    if problems:
        print(f"[warn] {len(problems)} data problems:")
        for p in problems[:20]:
            print(f"  - {p}")
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more")

    print("[done] " + ("dry run, nothing written" if args.dry_run else "import complete"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

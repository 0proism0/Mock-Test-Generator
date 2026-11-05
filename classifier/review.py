"""Human review helper: print what the classifier did, one question per block.

    python -m classifier.review                 # every jsonl in classifier/out
    python -m classifier.review amc10           # just amc10
    python -m classifier.review amc10 --level 4 # only the ones rated 4

The point is to eyeball ``why`` before trusting a full-bank run: if the model
starts justifying level with "the question is long", the rubric prompt lost and
prompts/classify.md needs fixing before you spend hours on 9266 questions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"


def rows(name: str):
    for line in (OUT / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bank", nargs="?", help="output stem, e.g. amc10 (default: all)")
    ap.add_argument("--level", type=int, help="only show this difficulty level")
    ap.add_argument("--state", help="only show this classification state (done/pending)")
    ap.add_argument("--limit", type=int, default=40, help="max rows per bank")
    args = ap.parse_args()

    stems = [args.bank] if args.bank else sorted(p.stem for p in OUT.glob("*.jsonl"))
    if not stems:
        print(f"no jsonl under {OUT}")
        return 2

    for stem in stems:
        shown = 0
        entries = sorted(rows(stem), key=lambda r: (r.get("position") or 0))
        print(f"===== {stem}: {len(entries)} rows")
        for r in entries:
            diff = r.get("difficulty") or {}
            cls = r.get("classification") or {}
            if args.level and diff.get("level") != args.level:
                continue
            if args.state and cls.get("state") != args.state:
                continue
            if shown >= args.limit:
                print(f"  ... ({args.limit} shown, use --limit)")
                break
            shown += 1
            tags = [t["id"] for t in cls.get("tags") or []]
            print(f'-- pos{r.get("position")} L{diff.get("level")} score={diff.get("score")} state={cls.get("state")}')
            print("   Q:", (r.get("question") or "")[:130].replace("\n", " "))
            print("   primary:", cls.get("primary"))
            print("   tags:", tags)
            print("   why:", (r.get("llm", {}).get("why") or "")[:160])
        if not shown:
            print("  (nothing matched the filters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

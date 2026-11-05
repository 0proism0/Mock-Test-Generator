"""Classify every bank, in one pass, resumable.

Order matters: bank v1 first, then bank v2. The v2 AMC 10/12 banks contain the
same problems as the v1 ones (measured: 47.8% / 31.8% of v2 rows are already in
v1 by whitespace-normalised text), so running v1 first lets `--reuse` skip those
model calls instead of paying for them twice.

Everything is appended to `classifier/out/<slug>.jsonl`, so killing this process
and re-running it just continues where it stopped.

    python -m classifier.run_all              # full run
    python -m classifier.run_all --only aime  # one slug
    python -m classifier.run_all --concurrency 8
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path

from . import classify

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "bank"
LOG = ROOT / "classifier" / "out" / "run_all.log"


def bank_slugs() -> list[str]:
    """Every competition slug that has at least one bank v1 file, biggest first."""
    sizes: dict[str, int] = {}
    for f in BANK.glob("*.json"):
        if f.name.endswith(".v1.json"):
            continue
        slug = f.name.split("_")[0]
        try:
            import json

            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a broken bank must not kill the run
            continue
        sizes[slug] = sizes.get(slug, 0) + len(doc.get("variants") or [])
    return [s for s, _ in sorted(sizes.items(), key=lambda kv: -kv[1])]


def v2_slugs() -> list[str]:
    d = BANK / "v2"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run_one(argv: list[str], label: str) -> tuple[bool, float]:
    t0 = time.time()
    log(f"--- {label} ---")
    try:
        classify.main(argv)
        ok = True
    except KeyboardInterrupt:
        raise
    except Exception:  # noqa: BLE001
        log(f"FAILED {label}\n{traceback.format_exc()}")
        ok = False
    dt = time.time() - t0
    log(f"=== {label}: {'ok' if ok else 'failed'} in {dt / 60:.1f} min")
    return ok, dt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="classify every bank")
    ap.add_argument("--only", help="comma separated slugs")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--skip-v2", action="store_true")
    ap.add_argument("--only-v2", action="store_true",
                    help="bank v2 only (bank v1 is being retired for AMC 10/12)")
    ap.add_argument("--force", action="store_true", help="reclassify rows already in the output")
    args = ap.parse_args(argv)

    slugs = [] if args.only_v2 else bank_slugs()
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        slugs = [s for s in slugs if s in want]
    v2 = [] if args.skip_v2 else v2_slugs()
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        v2 = [s for s in v2 if s in want]
    plan = [(["--bank", s], f"v1 {s}") for s in slugs]
    plan += [(["--bank", s, "--v2"], f"v2 {s}") for s in v2]
    if args.force:
        plan = [(extra + ["--force"], label) for extra, label in plan]

    log(f"plan: {len(plan)} batches, concurrency {args.concurrency}")
    pid_file = LOG.parent / "runner.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    t0 = time.time()
    fails = []
    for i, (extra, label) in enumerate(plan, 1):
        ok, _ = run_one(extra + ["--concurrency", str(args.concurrency)], f"[{i}/{len(plan)}] {label}")
        if not ok:
            fails.append(label)
    total = (time.time() - t0) / 60
    log(f"all done in {total:.1f} min; failed batches: {fails or 'none'}")
    pid_file.unlink(missing_ok=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

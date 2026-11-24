#!/usr/bin/env python3
"""Simulate a student practicing, so the mastery / rating code has data.

Writes rows into users/<user>/results.jsonl with exactly the same shape that
POST /api/result writes (including the per-question items[]), then prints what
the mastery model makes of them. Useful for checking that /api/mastery recovers
the ability you simulated, and for giving later features (weak-spot driven
papers, recommendations) something to chew on.

The simulated student is a Rasch model:

    P(correct) = sigmoid(theta + domain_offset - (level - 20) / 6)

`theta` is solved per paper by bisection so the *expected* accuracy hits
--accuracy; domain offsets (--spread) make some areas stronger than others so
the "weakest" panel has something real to show. Answers are then drawn with
that probability, so the realised accuracy lands near the target.

Examples
--------
python scripts/simulate_practice.py --user test --tests 10 --accuracy 0.55
python scripts/simulate_practice.py --user test --tests 20 --accuracy 0.7 --months 8 --seed 3
python scripts/simulate_practice.py --user test --show-only
python scripts/simulate_practice.py --user test --reset          # drop sim_ rows only
python scripts/simulate_practice.py --user test --tests 5 --dry-run

Output is ASCII only (the Windows console is GBK).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import mastery  # noqa: E402  (app/mastery.py)
import server  # noqa: E402  (app/server.py)

SIM_PREFIX = "sim_"


# ---------------------------------------------------------------- bank access

def _level_of(variant):
    """difficulty.level of a variant, or None when it was never classified."""
    diff = variant.get("difficulty")
    if isinstance(diff, dict):
        try:
            level = int(diff.get("level"))
        except (TypeError, ValueError):
            return None
    elif isinstance(diff, int):
        level = diff
    else:
        return None
    return level if 1 <= level <= 60 else None


def _topic_of(variant):
    cls = variant.get("classification")
    if isinstance(cls, dict) and cls.get("state", "done") == "done":
        primary = cls.get("primary")
        if isinstance(primary, str) and primary:
            return primary
    return None


def _domain_of(topic):
    return topic.split(".", 1)[0] if topic else None


def load_pool(banks):
    """(slug, position) -> list of usable variants (v2 bank, classified only)."""
    pool = {}
    for slug in banks:
        try:
            variants = server.load_bank(slug, None, version=2)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] cannot load bank v2 {slug}: {exc}")
            continue
        kept = 0
        for variant in variants:
            level = _level_of(variant)
            if level is None:
                continue
            position = variant.get("position")
            if not isinstance(position, int):
                continue
            pool.setdefault((slug, position), []).append(variant)
            kept += 1
        print(f"[pool] {slug}: {kept} classified variants")
    return pool


def build_paper(pool, banks, per_test, rng):
    """One paper: question N drawn from the pool of position N, like the real generator.

    Returns [(slug, variant), ...] so each item can carry its own bank tag.
    """
    picked = []
    for position in range(1, per_test + 1):
        candidates = []
        for slug in banks:
            for variant in pool.get((slug, position), []):
                candidates.append((slug, variant))
        if not candidates:
            continue
        picked.append(rng.choice(candidates))
    return picked


# ------------------------------------------------------------------- the model

def _sigmoid(x):
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def _b(level):
    return (level - mastery.ANCHOR) / mastery.LEVELS_PER_LOGIT


def _expected_accuracy(theta, rows):
    """Mean P(correct) over [(level, domain_offset)] pairs."""
    total = 0.0
    for level, offset in rows:
        total += _sigmoid(theta + offset - _b(level))
    return total / len(rows) if rows else 0.0


def solve_theta(rows, target):
    """Bisect theta so the expected accuracy equals target (monotone in theta)."""
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _expected_accuracy(mid, rows) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def draw_outcomes(probs, rng, noisy=False):
    """Turn per-question probabilities into right/wrong.

    Default is *stratified*: pick exactly round(sum(p)) questions to be correct,
    weighted by p, so a 25-question paper at --accuracy 0.6 always scores 15/25.
    That keeps the number you asked for stable even on tiny runs. `--noisy` falls
    back to independent Bernoulli draws (more realistic, much noisier at n=25).
    """
    if noisy:
        return [rng.random() < p for p in probs]
    n = len(probs)
    k = int(round(sum(probs)))
    if k <= 0:
        return [False] * n
    if k >= n:
        return [True] * n
    # Efraimidis-Spirakis: u^(1/p), keep the top k -> weighted sample w/o replacement.
    keys = []
    for p in probs:
        u = max(rng.random(), 1e-12)
        keys.append(u ** (1.0 / max(p, 1e-6)))
    chosen = set(sorted(range(n), key=lambda i: keys[i], reverse=True)[:k])
    return [i in chosen for i in range(n)]


# ---------------------------------------------------------------- result rows

def _result_row(user, picked, outcomes, submitted_at, duration_s, index):
    items = []
    for i, ((slug, variant), correct) in enumerate(zip(picked, outcomes), start=1):
        item = {"n": i, "correct": bool(correct)}
        qid = variant.get("qid")
        if isinstance(qid, str) and qid:
            item["qid"] = qid[:80]
        topic = _topic_of(variant)
        if topic:
            item["topic"] = topic[:120]
        qtype = variant.get("type")
        if isinstance(qtype, str) and qtype:
            item["type"] = qtype[:32]
        item["bank"] = slug
        level = _level_of(variant)
        if level is not None:
            item["level"] = level
        items.append(item)
    return {
        "test_id": f"{SIM_PREFIX}{int(time.time())}_{index:03d}",
        "title": f"Simulated practice #{index}",
        "competition": picked[0][0] if picked else "amc10",
        "score": sum(1 for outcome in outcomes if outcome),
        "total": len(picked),
        "answered": len(picked),
        "duration_s": duration_s,
        "items": items,
        "submitted_at": submitted_at,
        "user": user,
    }


def _timestamp(now, months, rng):
    """Spread attempts backwards in time so the monthly decay gets exercised."""
    if months <= 0:
        return now.strftime("%Y-%m-%d %H:%M:%S")
    days = months * 30
    offset = timedelta(days=rng.uniform(0, days), minutes=rng.randint(0, 1439))
    return (now - offset).strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------- reporting

def print_mastery(user):
    rows = server.read_results(user)
    if not rows:
        print(f"[mastery] no results for {user}")
        return
    try:
        summary = mastery.summarize(rows, server.load_taxonomy())
    except Exception as exc:  # noqa: BLE001
        print(f"[mastery] failed: {exc}")
        return
    totals = summary["totals"]
    rating = summary["rating"]
    print("")
    print(f"[mastery] rows={totals['attempts']} answered={totals['answered']} "
          f"correct={totals['correct']} accuracy={totals['accuracy']}")
    if rating:
        print(f"[mastery] rating level={rating['level']} band={rating['band']} "
              f"theta={rating['theta']} ci={rating['ci']} n={rating['n']}")
    else:
        print("[mastery] rating: null (not enough difficulty-rated answers)")
    for domain in summary["domains"]:
        print(f"[mastery]   {domain['id']:<24} mastery={domain['mastery']:>3} "
              f"accuracy={domain['accuracy']} n={domain['n']}")
    if summary["weakest"]:
        weakest = summary["weakest"][0]
        print(f"[mastery] weakest: {weakest.get('topic')} {weakest.get('bucket')} "
              f"mastery={weakest.get('mastery')} n={weakest.get('n')}")


# ------------------------------------------------------------------------ main

def main(argv=None):
    parser = argparse.ArgumentParser(description="Simulate practice for a user (testing aid).")
    parser.add_argument("--user", default="test", help="username to write results for")
    parser.add_argument("--tests", type=int, default=10, help="how many papers to simulate")
    parser.add_argument("--accuracy", type=float, default=0.6, help="target overall accuracy (0-1)")
    parser.add_argument("--per-test", type=int, default=25, help="questions per paper")
    parser.add_argument("--months", type=int, default=0,
                        help="spread attempts over the last N months (0 = all now)")
    parser.add_argument("--spread", type=float, default=0.8,
                        help="per-domain ability std in logits (0 = uniform ability)")
    parser.add_argument("--banks", default="amc10,amc12", help="comma separated bank slugs (v2)")
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducibility")
    parser.add_argument("--noisy", action="store_true",
                        help="draw answers independently instead of matching the target exactly")
    parser.add_argument("--reset", action="store_true", help="delete existing sim_ rows first")
    parser.add_argument("--purge", action="store_true", help="delete the whole results file first")
    parser.add_argument("--dry-run", action="store_true", help="do not write anything")
    parser.add_argument("--show", action="store_true", help="print the mastery summary after writing")
    parser.add_argument("--show-only", action="store_true", help="print the mastery summary and exit")
    args = parser.parse_args(argv)

    if args.show_only:
        print_mastery(args.user)
        return 0

    if not 0.0 < args.accuracy < 1.0:
        print("[error] --accuracy must be strictly between 0 and 1")
        return 2

    rng = random.Random(args.seed)
    now = datetime.now()
    banks = [slug.strip() for slug in args.banks.split(",") if slug.strip()]

    rfile = server._results_file(args.user)  # noqa: SLF001 (same package, test aid)
    rfile.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if rfile.exists():
        for line in rfile.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(line)

    if args.purge:
        existing = []
        print(f"[reset] purge: dropped all {len(server.read_results(args.user))} row(s)")
    elif args.reset:
        kept = [line for line in existing
                if not str(json.loads(line).get("test_id", "")).startswith(SIM_PREFIX)]
        print(f"[reset] dropped {len(existing) - len(kept)} sim_ row(s)")
        existing = kept

    pool = load_pool(banks)
    if not pool:
        print("[error] no classified questions found (run the classifier first?)")
        return 2

    domain_offsets = {}
    new_rows = []
    target_sum = 0.0
    hit_sum = 0
    item_count = 0
    thetas = []

    for index in range(1, args.tests + 1):
        picked = build_paper(pool, banks, args.per_test, rng)
        if not picked:
            continue
        levels = [_level_of(variant) for _, variant in picked]
        domains = [_domain_of(_topic_of(variant)) for _, variant in picked]
        for domain in domains:
            if domain and domain not in domain_offsets:
                domain_offsets[domain] = rng.gauss(0.0, args.spread)

        rows = [(level, domain_offsets.get(domain, 0.0))
                for level, domain in zip(levels, domains)]
        theta = solve_theta(rows, args.accuracy)
        thetas.append(theta)

        probs = []
        for level, offset in rows:
            p = _sigmoid(theta + offset - _b(level))
            p = min(0.98, max(0.02, p))
            target_sum += p
            probs.append(p)
        outcomes = draw_outcomes(probs, rng, noisy=args.noisy)
        hit_sum += sum(1 for outcome in outcomes if outcome)
        item_count += len(picked)

        submitted_at = _timestamp(now, args.months, rng)
        duration_s = rng.randint(1200, 2700)
        new_rows.append(_result_row(args.user, picked, outcomes,
                                    submitted_at, duration_s, index))

    if not new_rows:
        print("[error] nothing to simulate")
        return 2

    total_q = sum(row["total"] for row in new_rows)
    total_hit = sum(row["score"] for row in new_rows)
    mean_theta = sum(thetas) / len(thetas)
    print(f"[plan] {len(new_rows)} paper(s), {total_q} question(s), "
          f"target accuracy {args.accuracy:.3f}")
    print(f"[plan] realised accuracy {total_hit / total_q:.3f} "
          f"({total_hit}/{total_q}), expected {target_sum / max(1, item_count):.3f}")
    print(f"[plan] simulated ability theta={mean_theta:.3f} "
          f"-> level {20 + 6 * mean_theta:.1f}")

    if args.dry_run:
        print("[dry-run] nothing written")
        return 0

    lines = existing + [json.dumps(row, ensure_ascii=False) for row in new_rows]
    rfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[write] {rfile} now has {len(lines)} row(s)")

    if args.show:
        print_mastery(args.user)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic difficulty prior from bank metadata — no model, no answer data.

Why this exists: a paper is assembled by drawing "question at original position N"
from many years, so `position` already carries the author's own difficulty
ordering. That makes a cheap, reproducible prior available for every one of the
9266 bank questions before a single human or model label exists.

Scale: 1-20, where **20 = the average AMC 12 problem 25**. AIME and olympiad
problems run above 20, up to about 42 for an IMO #6. The same ladder is used by
the model rubric in `prompts/classify.md`, so prior and llm_rubric are directly
comparable numbers and can be averaged.

Two signals, nothing else:
  * `BASE_TOP` base — how hard the contest is at its position 1
  * `BASE_TOP` top  — how hard it is at its last question; position interpolates

The prior is deliberately coarse. Its job is to be (a) a cold-start value,
(b) a tie-breaker when the model is unsure, and (c) the anchor that keeps the
model's ratings from drifting between runs.
"""

from __future__ import annotations

import re

# (position 1 difficulty, last-position difficulty) on the 1-20+ scale.
BASE_TOP: dict[str, tuple[float, float]] = {
    "mathkangaroo": (1.0, 6.0),
    "amc8": (1.0, 8.0),
    "mathcounts": (2.0, 10.0),
    "amc10": (5.0, 15.0),
    "amc12": (7.0, 20.0),
    "fma": (9.0, 20.0),
    "comc": (8.0, 22.0),
    "bmmt": (9.0, 24.0),
    "ukmt": (10.0, 24.0),
    "bmt": (11.0, 28.0),
    "smt": (10.0, 30.0),
    "aime": (20.0, 30.0),
    "cmo": (22.0, 34.0),
    "apmo": (22.0, 34.0),
    "pumac": (12.0, 33.0),
    "cmimc": (12.0, 32.0),
    "hmmt": (13.0, 32.0),
    "usamts": (18.0, 32.0),
    "usamo": (26.0, 40.0),
    "putnam": (25.0, 42.0),
    "imo": (28.0, 42.0),
    "bpho": (18.0, 30.0),
    "usapho": (25.0, 38.0),
    "physicsbowl": (3.0, 12.0),
}
DEFAULT_BASE, DEFAULT_TOP = 6.0, 22.0

MAX_SCORE = 60.0

# Coarse buckets over the open ended scale.
EASY_MAX = 9      # AMC 8 last problem and below
MEDIUM_MAX = 17   # AMC 10 last problem and below; AMC 12 #25 is 20
SCALE = "amc20"


def _slug_of(competition: str | None, source: str | None = None) -> str:
    raw = (competition or "").strip().lower().replace("-", "_")
    if raw in BASE_TOP:
        return raw
    # "AMC 10 2003 Problem 4" -> amc10
    m = re.match(r"^([a-z]+)\s*(\d+)", raw)
    if m and (m.group(1) + m.group(2)) in BASE_TOP:
        return m.group(1) + m.group(2)
    if source:
        s = re.match(r"^([A-Za-z]+)\s*(\d+)?", source.strip())
        if s:
            cand = (s.group(1) + (s.group(2) or "")).lower()
            if cand in BASE_TOP:
                return cand
    return raw


def prior(competition: str | None, position: int | None, positions: int = 25,
          source: str | None = None) -> dict:
    """Return {'score': 1-60 float, 'level': int, 'reason': str, 'slug': str}."""
    slug = _slug_of(competition, source)
    base, top = BASE_TOP.get(slug, (DEFAULT_BASE, DEFAULT_TOP))

    n = max(2, int(positions or 25))
    pos = int(position or 1)
    t = min(1.0, max(0.0, (pos - 1) / (n - 1)))
    score = round(min(MAX_SCORE, max(1.0, base + (top - base) * t)), 2)
    return {
        "score": score,
        "level": to_level(score),
        "slug": slug,
        "position": pos,
        "positions": n,
        "reason": f"{slug} {base:.1f}->{top:.1f} at t={t:.2f} = {score:.2f}",
    }


def to_level(score: float) -> int:
    """Continuous score -> integer level on the open 1-20+ scale."""
    return int(min(MAX_SCORE, max(1.0, round(float(score)))))


def band_of(level: int) -> str:
    if level <= EASY_MAX:
        return "easy"
    if level <= MEDIUM_MAX:
        return "medium"
    return "hard"


if __name__ == "__main__":
    for slug in ("amc8", "amc10", "amc12", "aime", "pumac", "usamo"):
        row = [f"p{p}:{prior(slug, p)['score']:.1f}" for p in (1, 5, 10, 15, 20, 25)]
        print(f"{slug:8s} " + "  ".join(row))

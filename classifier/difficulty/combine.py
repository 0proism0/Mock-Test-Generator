"""Fuse difficulty evidence into the v1.1 `difficulty` object.

Evidence sources (all optional, any subset):
  prior       competition+position prior          (always available, deterministic)
  llm_rubric  model rating 1-20+                  (available today, noisy)
  elo         rating from real answer history     (needs per-question answer logs)
  irt         Rasch/2PL b parameter               (needs a few hundred answers)
  human       edited by a person                  (overrides everything)

Weights shift as real evidence accumulates, so the same JSON shape keeps working
from cold start to a calibrated library. No field has to be rewritten later.
"""

from __future__ import annotations

import time

from . import prior as prior_mod

# method -> (weight, confidence) by evidence stage
WEIGHT_TABLE: dict[str, dict[str, float]] = {
    "cold":   {"prior": 0.35, "llm_rubric": 0.65},
    "early":  {"prior": 0.20, "llm_rubric": 0.50, "elo": 0.30},
    "mid":    {"prior": 0.10, "llm_rubric": 0.35, "elo": 0.35, "irt": 0.20},
    "mature": {"prior": 0.05, "llm_rubric": 0.20, "elo": 0.35, "irt": 0.40},
}


def stage_for(attempts: int) -> str:
    if attempts <= 0:
        return "cold"
    if attempts < 10:
        return "early"
    if attempts < 30:
        return "mid"
    return "mature"


def combine(
    *,
    competition: str | None = None,
    position: int | None = None,
    positions: int = 25,
    source: str | None = None,
    llm_level: int | None = None,
    llm_confidence: float | None = None,
    attempts: int = 0,
    elo_score: float | None = None,
    irt_score: float | None = None,
    human_score: float | None = None,
    today: str | None = None,
) -> dict:
    """Return a v1.1 `difficulty` object."""
    comps: list[dict] = []

    if human_score is not None:
        comps.append({"method": "human", "score": round(float(human_score), 2),
                      "weight": 1.0, "confidence": 1.0})
    else:
        p = prior_mod.prior(competition, position, positions, source)
        stage = stage_for(attempts)
        weights = dict(WEIGHT_TABLE[stage])
        if llm_level is None:
            weights.pop("llm_rubric", None)
        if elo_score is None:
            weights.pop("elo", None)
        if irt_score is None:
            weights.pop("irt", None)
        if not weights:
            weights = {"prior": 1.0}

        if "prior" in weights:
            comps.append({"method": "prior", "score": p["score"],
                          "weight": weights["prior"], "confidence": 0.35,
                          "reason": p["reason"]})
        if "llm_rubric" in weights:
            comps.append({"method": "llm_rubric",
                          "score": round(float(llm_level), 2),
                          "weight": weights["llm_rubric"],
                          "confidence": round(float(llm_confidence if llm_confidence is not None else 0.5), 2)})
        if "elo" in weights:
            comps.append({"method": "elo", "score": round(float(elo_score), 2),
                          "weight": weights["elo"],
                          "confidence": round(min(0.9, 0.2 + attempts / 60.0), 2)})
        if "irt" in weights:
            comps.append({"method": "irt", "score": round(float(irt_score), 2),
                          "weight": weights["irt"],
                          "confidence": round(min(0.95, 0.3 + attempts / 120.0), 2)})

    total_w = sum(c["weight"] for c in comps) or 1.0
    score = round(min(prior_mod.MAX_SCORE,
                      max(1.0, sum(c["score"] * c["weight"] for c in comps) / total_w)), 2)
    confidence = round(sum(c.get("confidence", 0.5) * c["weight"] for c in comps) / total_w, 2)
    level = prior_mod.to_level(score)
    method = comps[0]["method"] if len(comps) == 1 else "hybrid"

    return {
        "level": level,
        "scale": prior_mod.SCALE,
        "band": prior_mod.band_of(level),
        "score": score,
        "method": method,
        "confidence": confidence,
        "components": comps,
        "evidence": {"attempts": attempts},
        "reviewed": human_score is not None,
        "at": today or time.strftime("%Y-%m-%d"),
    }

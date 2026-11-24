"""Mastery model: per-area / per-topic / per-difficulty-band progress plus one rating.

Derived data only. Raw per-question outcomes live in ``users/<user>/results.jsonl``
as the ``items`` array of each attempt; this module turns them into the numbers
the UI draws. Standard library only, like the rest of the backend.

Scale: ``difficulty.level`` is the amc20 scale (1..60, 20 == average AMC 12 #25).

Model in one paragraph
----------------------
Every answered question is one weighted Bernoulli trial: y=1 solved, y=0 not.
The weight decays on a monthly boundary -- on the 1st of each month every old
answer is multiplied by DECAY (0.85), so what you did last year counts ~0.14.
Accuracy is a Beta(2,2)-shrunk ratio, so "1 of 1" reads as 75% instead of 100%.
The overall rating is a Rasch/logistic fit: P(solve | level) = sigmoid(theta - b)
with b = (level - 20) / 6, so theta is "how many logits above the AMC 12 #25
anchor you are"; it is reported back on the 1-60 level scale.
"""

from __future__ import annotations

import math
from datetime import datetime

# --- tunables -------------------------------------------------------------

# Monthly decay: applied on the 1st of every month (see months_between).
DECAY = 0.85
# Beta prior on every accuracy cell: pretend we already saw 2 right / 2 wrong.
PRIOR_WINS = 2.0
PRIOR_LOSSES = 2.0
# Difficulty buckets used for the "fine" cells (amc20 levels, inclusive).
BUCKETS = ((1, 5), (6, 10), (11, 15), (16, 20), (21, 60))
# amc20 anchor: level 20 == average AMC 12 problem 25.
ANCHOR = 20.0
LEVELS_PER_LOGIT = 6.0
# Gaussian prior on theta, in logits. Keeps 2-answer histories from rating L40.
THETA_PRIOR_SD = 1.0
DOMAIN_PRIOR_SD = 1.5
MIN_RATING_ITEMS = 3
MAX_ITEMS_PER_ATTEMPT = 300


# --- small helpers --------------------------------------------------------


def _parse_ts(value):
    """'2026-11-05 21:44:33' (server) or ISO-ish strings -> datetime or None."""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def months_between(then, now):
    """Whole month boundaries crossed, i.e. how many 1st-of-month decays apply."""
    months = (now.year - then.year) * 12 + (now.month - then.month)
    return max(0, months)


def decay_weight(then, now):
    return DECAY ** months_between(then, now)


def bucket_of(level):
    """amc20 level -> bucket label such as '6-10'; None when unknown."""
    try:
        lv = int(level)
    except (TypeError, ValueError):
        return None
    for lo, hi in BUCKETS:
        if lo <= lv <= hi:
            return "%d-%d" % (lo, hi)
    return "%d-%d" % (BUCKETS[0] if lv < BUCKETS[0][0] else BUCKETS[-1])


def _sigmoid(x):
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def shrink(wins, total):
    """Beta(2,2)-shrunk accuracy: 0.5 prior, 4 pseudo-observations."""
    if total <= 0:
        return None
    return (wins + PRIOR_WINS) / (total + PRIOR_WINS + PRIOR_LOSSES)


def pct(wins, total):
    value = shrink(wins, total)
    return None if value is None else int(round(value * 100))


def band_of(level):
    if level is None:
        return None
    if level <= 9:
        return "easy"
    if level <= 17:
        return "medium"
    return "hard"


def level_of(theta):
    level = ANCHOR + LEVELS_PER_LOGIT * theta
    return max(1.0, min(60.0, level))


def fit_theta(observations, prior_sd=THETA_PRIOR_SD, iterations=40):
    """Weighted logistic MLE with a Gaussian prior. Returns (theta, standard error)."""
    if not observations:
        return 0.0, 9.99
    precision = 1.0 / (prior_sd * prior_sd)
    theta = 0.0
    info = precision
    for _ in range(iterations):
        grad = -theta * precision
        info = precision
        for b, y, w in observations:
            p = _sigmoid(theta - b)
            grad += w * (y - p)
            info += w * p * (1.0 - p)
        if info <= 1e-9:
            return theta, 9.99
        step = grad / info
        theta = max(-6.0, min(6.0, theta + step))
        if abs(step) < 1e-7:
            break
    return theta, math.sqrt(1.0 / info)


def b_of_level(level):
    return (float(level) - ANCHOR) / LEVELS_PER_LOGIT


# --- item extraction ------------------------------------------------------


def build_items(result_rows, now=None):
    """Flatten stored attempts into weighted per-question observations.

    Rows written before per-question recording existed have no ``items`` and are
    skipped here; they still count towards the attempt totals.
    """
    now = now or datetime.now()
    out = []
    for row in result_rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("test_id") or "").startswith("pk_"):
            continue  # PK games are a different mode, not practice evidence
        at = _parse_ts(row.get("submitted_at"))
        if at is None:
            continue
        weight = decay_weight(at, now)
        raw_items = row.get("items")
        if not isinstance(raw_items, list):
            continue
        for item in raw_items[:MAX_ITEMS_PER_ATTEMPT]:
            if not isinstance(item, dict):
                continue
            topic = item.get("topic") or item.get("primary") or ""
            topic = topic.strip() if isinstance(topic, str) else ""
            domain = topic.split(".")[0] if topic else ""
            try:
                level = int(item.get("level"))
            except (TypeError, ValueError):
                level = None
            if level is not None and not 1 <= level <= 60:
                level = None
            out.append({
                "topic": topic,
                "domain": domain,
                "level": level,
                "bucket": bucket_of(level) if level is not None else None,
                "correct": bool(item.get("correct")),
                "weight": weight,
                "at": at,
            })
    return out


# --- aggregation ----------------------------------------------------------


class _Tally:
    __slots__ = ("wins", "n")

    def __init__(self):
        self.wins = 0.0
        self.n = 0.0

    def add(self, correct, weight):
        self.wins += weight * (1.0 if correct else 0.0)
        self.n += weight


def _node_label(nodes, node_id, field):
    node = nodes.get(node_id) or {}
    value = node.get(field)
    return value if isinstance(value, str) and value else None


def _domain_sort_key(order, node_id):
    return (order.get(node_id, 10 ** 6), node_id)


def summarize(result_rows, taxonomy=None, now=None):
    """Turn stored attempts into the payload ``GET /api/mastery`` returns."""
    now = now or datetime.now()
    nodes = {}
    if isinstance(taxonomy, dict):
        nodes = taxonomy.get("nodes") or {}
    order = {node_id: i for i, node_id in enumerate(nodes)}

    items = build_items(result_rows, now)
    cells = {}
    topics = {}
    domains = {}
    buckets = {}
    obs_all = []
    obs_by_domain = {}
    last_at = None
    attempts = 0
    for row in result_rows or []:
        if isinstance(row, dict) and not str(row.get("test_id") or "").startswith("pk_"):
            attempts += 1

    for item in items:
        dom = item["domain"] or "unknown"
        top = item["topic"] or "unknown"
        cells.setdefault((dom, top, item["bucket"]), _Tally()).add(item["correct"], item["weight"])
        topics.setdefault((dom, top), _Tally()).add(item["correct"], item["weight"])
        domains.setdefault(dom, _Tally()).add(item["correct"], item["weight"])
        if item["bucket"] is not None:
            buckets.setdefault(item["bucket"], _Tally()).add(item["correct"], item["weight"])
            b = b_of_level(item["level"])
            obs = (b, 1.0 if item["correct"] else 0.0, item["weight"])
            obs_all.append(obs)
            obs_by_domain.setdefault(dom, []).append(obs)
        if last_at is None or item["at"] > last_at:
            last_at = item["at"]

    # --- overall rating ---------------------------------------------------
    rating = None
    if len(obs_all) >= MIN_RATING_ITEMS:
        theta, se = fit_theta(obs_all)
        level = level_of(theta)
        half = LEVELS_PER_LOGIT * 1.96 * se
        rating = {
            "level": round(level, 2),
            "band": band_of(level),
            "theta": round(theta, 3),
            "se": round(se, 3),
            "ci": [round(max(1.0, level - half), 2), round(min(60.0, level + half), 2)],
            "n": len(obs_all),
        }

    # --- domains / topics / cells ----------------------------------------
    topic_rows = {}
    for (dom, top), tally in topics.items():
        cell_rows = []
        for (c_dom, c_top, bucket), cell in cells.items():
            if c_dom != dom or c_top != top or bucket is None:
                continue
            cell_rows.append({
                "bucket": bucket,
                "mastery": pct(cell.wins, cell.n),
                "n": int(round(cell.n)),
                "wins": int(round(cell.wins)),
            })
        cell_rows.sort(key=lambda c: [b for b, _ in _bucket_order()].index(c["bucket"])
                       if c["bucket"] in [b for b, _ in _bucket_order()] else 99)
        # Topic mastery is the evidence-weighted mean of its difficulty cells,
        # exactly as asked: the fine cells roll up, they are not recomputed.
        num = sum((c["mastery"] or 0) * c["n"] for c in cell_rows)
        den = sum(c["n"] for c in cell_rows)
        mastery = int(round(num / den)) if den else pct(tally.wins, tally.n)
        topic_rows.setdefault(dom, []).append({
            "id": top,
            "en": _node_label(nodes, top, "en"),
            "zh": _node_label(nodes, top, "zh"),
            "mastery": mastery,
            "accuracy": round(shrink(tally.wins, tally.n), 3) if tally.n else None,
            "n": int(round(tally.n)),
            "cells": cell_rows,
        })

    domain_rows = []
    for dom, tally in domains.items():
        kids = sorted(topic_rows.get(dom, []), key=lambda t: _domain_sort_key(order, t["id"]))
        num = sum((t["mastery"] or 0) * t["n"] for t in kids)
        den = sum(t["n"] for t in kids)
        mastery = int(round(num / den)) if den else pct(tally.wins, tally.n)
        dom_level = None
        dom_band = None
        dom_obs = obs_by_domain.get(dom) or []
        if len(dom_obs) >= MIN_RATING_ITEMS:
            d_theta, _ = fit_theta(dom_obs, prior_sd=DOMAIN_PRIOR_SD)
            dom_level = round(level_of(d_theta), 2)
            dom_band = band_of(dom_level)
        domain_rows.append({
            "id": dom,
            "en": _node_label(nodes, dom, "en") or (None if dom == "unknown" else dom),
            "zh": _node_label(nodes, dom, "zh"),
            "mastery": mastery,
            "accuracy": round(shrink(tally.wins, tally.n), 3) if tally.n else None,
            "n": int(round(tally.n)),
            "level": dom_level,
            "band": dom_band,
            "topics": kids,
        })
    # The radar always needs every first-level area, even when an area has no
    # attempts yet -- otherwise a new account gets a triangle instead of a
    # polygon and the numbers table silently loses rows.
    seen_domains = {d["id"] for d in domain_rows}
    for dom in (node_id for node_id in nodes if "." not in node_id):
        if dom in seen_domains:
            continue
        domain_rows.append({
            "id": dom,
            "en": _node_label(nodes, dom, "en"),
            "zh": _node_label(nodes, dom, "zh"),
            "mastery": None,
            "accuracy": None,
            "n": 0,
            "level": None,
            "band": None,
            "topics": [],
        })
    domain_rows.sort(key=lambda d: _domain_sort_key(order, d["id"]))

    # --- difficulty profile + weakest spots -------------------------------
    bucket_rows = []
    for label, _ in _bucket_order():
        tally = buckets.get(label)
        if tally is None:
            continue
        bucket_rows.append({
            "bucket": label,
            "mastery": pct(tally.wins, tally.n),
            "n": int(round(tally.n)),
            "wins": int(round(tally.wins)),
        })

    weakest = []
    for (dom, top, bucket), cell in cells.items():
        if cell.n < 2 or bucket is None:
            continue
        weakest.append({
            "domain": dom,
            "topic": top,
            "en": _node_label(nodes, top, "en"),
            "zh": _node_label(nodes, top, "zh"),
            "bucket": bucket,
            "mastery": pct(cell.wins, cell.n),
            "n": int(round(cell.n)),
        })
    weakest.sort(key=lambda w: (w["mastery"], -w["n"]))
    weakest = weakest[:5]

    total_wins = sum(t.wins for t in domains.values())
    total_n = sum(t.n for t in domains.values())
    return {
        "model": {
            "name": "amc20-decay",
            "scale": "amc20",
            "anchor": ANCHOR,
            "levels_per_logit": LEVELS_PER_LOGIT,
            "decay": DECAY,
            "decay_rule": "weight *= %.2f on the 1st of every month" % DECAY,
            "prior": [PRIOR_WINS, PRIOR_LOSSES],
            "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "totals": {
            "attempts": attempts,
            "answered": len(items),
            "correct": int(round(sum(1 for i in items if i["correct"]))),
            "accuracy": round(shrink(total_wins, total_n), 3) if total_n else None,
            "decayed_n": round(total_n, 1),
            "first_at": min((i["at"] for i in items), default=None).strftime("%Y-%m-%d")
            if items else None,
            "last_at": last_at.strftime("%Y-%m-%d") if last_at else None,
        },
        "rating": rating,
        "domains": domain_rows,
        "buckets": bucket_rows,
        "weakest": weakest,
    }


def _bucket_order():
    return [("%d-%d" % (lo, hi), (lo, hi)) for lo, hi in BUCKETS]

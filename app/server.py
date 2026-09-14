"""MockTest Maker — localhost web app.

Run:  .venv/bin/python app/server.py  (then open http://localhost:8000)
Stdlib only. Serves tests from tests/*.json, generates new tests from bank/<slug>_*.json.
"""
import hashlib
import json
import os
import random
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys_path = str(Path(__file__).resolve().parent)
if sys_path not in os.sys.path:
    os.sys.path.insert(0, sys_path)
from latex_wrap import wrap_bare_math

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
BANK = ROOT / "bank"
STATIC = ROOT / "app" / "static"
RESULTS = ROOT / "results.jsonl"
USERS_DIR = ROOT / "users"
USERS_FILE = ROOT / "users.json"
SESSIONS_FILE = ROOT / "sessions.json"
SESSION_DAYS = 7
PORT = 8000

COMP_META = {  # slug -> (display name, n_q, tlim, category, rounds, family)
    "amc8": ("AMC 8", 25, 40, "Math", None, "AMC"),
    "amc10": ("AMC 10", 25, 75, "Math", None, "AMC"),
    "amc12": ("AMC 12", 25, 75, "Math", None, "AMC"),
    "aime": ("AIME", 15, 180, "Math", None, "AIME"),
    "imo": ("IMO", 6, 270, "Math", None, "IMO"),
    "usamo": ("USAMO", 6, 270, "Math", None, "USAMO"),
    "putnam": ("Putnam", 12, 360, "Math", None, "Putnam"),
    "apmo": ("APMO", 5, 240, "Math", None, "APMO"),
    "hmmt": ("HMMT", 10, 50, "Math", {"General": (10, 50), "Theme": (10, 50)}, "HMMT"),
    "mathcounts": ("MATHCOUNTS", 30, 40, "Math", {"Sprint": (30, 40), "Target": (8, 24), "Team": (10, 20)}, "MATHCOUNTS"),
    "smt": ("SMT", 25, 110, "Math", {"General": (25, 110), "Algebra": (10, 50), "Calculus": (10, 50), "Discrete": (10, 50), "Geometry": (10, 50), "Team": (15, 50)}, "SMT"),
    "pumac": ("PUMaC", 8, 60, "Math", {"Algebra": (8, 60), "Geometry": (8, 60), "Combinatorics": (8, 60), "Number Theory": (8, 60), "Individual Finals": (4, 60), "Team": (15, 90), "Power": (11, 90)}, "PUMaC"),
    "bmt": ("BMT", 25, 90, "Math", {"General": (25, 90), "Algebra": (11, 60), "Calculus": (11, 60), "Discrete": (11, 60), "Geometry": (11, 60), "Guts": (27, 75), "Power": (3, 60)}, "BMT"),
    "bmmt": ("BMMT", 25, 60, "Math", None, "BMMT"),
    "cmimc": ("CMIMC", 10, 60, "Math", {"Algebra": (10, 50), "Combinatorics": (10, 50), "Geometry": (10, 50), "Computer Science": (10, 50), "Team": (10, 30)}, "CMIMC"),
    "comc": ("COMC", 8, 150, "Math", None, "COMC"),
    "cmo": ("CMO", 5, 180, "Math", None, "CMO"),
    "usamts": ("USAMTS", 5, 240, "Math", None, "USAMTS"),
    "ukmt": ("UKMT", 25, 60, "Math", None, "UKMT"),
    "mathkangaroo": ("Math Kangaroo", 10, 45, "Math", None, "Math Kangaroo"),
    "fma": ("F=ma", 25, 75, "Physics", None, "F=ma"),
    "physicsbowl": ("Physics Bowl", 40, 45, "Physics", None, "Physics Bowl"),
    "usapho": ("USAPhO", 6, 180, "Physics", None, "USAPhO"),
    "bpho_r1": ("BPhO Round 1", 10, 60, "Physics", None, "BPhO"),
    "bpho_r2": ("BPhO Round 2", 4, 180, "Physics", None, "BPhO"),
    "ipho": ("IPhO", 3, 300, "Physics", {"Theory": (3, 300)}, "IPhO"),
    "sat_physics": ("SAT Physics", 75, 60, "Physics", None, "SAT Physics"),
    "ap_physics1": ("AP Physics 1", 50, 90, "Physics", None, "AP Physics"),
    "ap_physics2": ("AP Physics 2", 50, 90, "Physics", None, "AP Physics"),
    "ap_physics_c_mech": ("AP Physics C: Mechanics", 35, 45, "Physics", None, "AP Physics C"),
    "ap_physics_c_em": ("AP Physics C: E&M", 35, 45, "Physics", None, "AP Physics C"),
    "gre_physics": ("GRE Physics", 100, 170, "Physics", None, "GRE Physics"),
}

ROUND_PATTERNS = {  # slug -> regex extracting round name from a variant's source string
    "mathcounts": r"(Sprint|Target|Team)",
    "hmmt": r"(General|Theme)",
    "smt": r"SMT (\w+) Problem",
    "pumac": r"PUMaC ([\w ]+?) Problem",
    "bmt": r"(?:BMT|BmMT) (\w+) Problem",
    "cmimc": r"CMIMC ([\w ]+?) Problem",
}

# Default points per question for competitions where every problem has the same weight.
# Competitions not listed here fall back to 1 point per question.
DEFAULT_POINTS = {
    "amc8": 1,
    "amc10": 6,
    "amc12": 6,
    "aime": 1,
    "fma": 1,
    "physicsbowl": 1,
    "hmmt": 1,
    "smt": 1,
    "bmmt": 1,
}

CATEGORY_ORDER = ["Math", "Physics", "Chemistry", "Biology", "Informatics",
                  "Astronomy & Earth", "Economics", "Linguistics", "Other"]


# ---------- Auth helpers ----------

def _load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return salt, key


def _verify_password(password, salt, key):
    _, check = _hash_password(password, salt)
    return secrets.compare_digest(key, check)


def _read_users():
    return {u["username"]: u for u in _load_json(USERS_FILE, [])}


def _write_users(users):
    _save_json(USERS_FILE, list(users.values()))


def _read_sessions():
    now = time.time()
    sessions = _load_json(SESSIONS_FILE, [])
    # drop expired
    return {s["id"]: s for s in sessions if s.get("expires_at", 0) > now}


def _write_sessions(sessions):
    _save_json(SESSIONS_FILE, list(sessions.values()))


def _make_session(username):
    sessions = _read_sessions()
    sid = secrets.token_urlsafe(32)
    sessions[sid] = {
        "id": sid,
        "username": username,
        "expires_at": time.time() + SESSION_DAYS * 86400,
    }
    _write_sessions(sessions)
    return sid


def _delete_session(sid):
    sessions = _read_sessions()
    sessions.pop(sid, None)
    _write_sessions(sessions)


def _parse_cookies(cookie_header):
    if not cookie_header:
        return {}
    out = {}
    for part in cookie_header.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k] = v
    return out


def current_user(cookie_header):
    cookies = _parse_cookies(cookie_header)
    sid = cookies.get("session_id")
    if not sid:
        return None
    sessions = _read_sessions()
    s = sessions.get(sid)
    if not s:
        return None
    touch_user(s["username"])
    return s["username"]


# --- online presence (in-memory; single process) ---
ONLINE_WINDOW = 90  # seconds without a request => offline
_active = {}        # username -> last request timestamp
_active_lock = threading.Lock()


def touch_user(username):
    if username:
        with _active_lock:
            _active[username] = time.time()


def is_online(username):
    with _active_lock:
        ts = _active.get(username)
    return bool(ts and time.time() - ts < ONLINE_WINDOW)


# --- friends & chat storage ---
FRIENDS_FILE = ROOT / "friends.json"
MESSAGES_FILE = ROOT / "messages.jsonl"
_store_lock = threading.Lock()

# --- PK (1v1 battle / race) storage ---
PK_DIR = ROOT / "pk"
PK_LEVELS = {"easy": (0.0, 0.4), "medium": (0.4, 0.75), "hard": (0.75, 1.001)}
PK_INVITE_TTL_S = 300  # pending challenges expire after 5 minutes
CLASSES_FILE = ROOT / "classes.json"
CLASS_REPORTS_FILE = ROOT / "class_reports.jsonl"


def _read_classes():
    return _load_json(CLASSES_FILE, {})


def _write_classes(d):
    _save_json(CLASSES_FILE, d)


def _pk_game_path(gid):
    return PK_DIR / f"{gid}.json"


def _read_pk(gid):
    f = _pk_game_path(gid)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except Exception:
        return None


def _write_pk(game):
    PK_DIR.mkdir(exist_ok=True)
    with _store_lock:
        _pk_game_path(game["id"]).write_text(json.dumps(game, ensure_ascii=False))


def _pk_result_for(user, test_id):
    for r in reversed(read_results(user)):
        if r.get("test_id") == test_id:
            return r
    return None


def pk_game_view(game, user):
    """Game dict from `user`'s perspective, with live scores."""
    other = game["opponent"] if user == game["challenger"] else game["challenger"]
    view = {
        "id": game["id"], "opponent": other, "me": user,
        "role": "challenger" if user == game["challenger"] else "opponent",
        "slug": game["slug"], "difficulty": game["difficulty"],
        "status": game["status"], "created_at": game.get("created_at"),
        "test_id": game.get("test_id"),
    }
    mine = theirs = None
    if game.get("test_id"):
        mine = _pk_result_for(user, game["test_id"])
        theirs = _pk_result_for(other, game["test_id"])
    view["my"] = _pk_score_view(mine)
    view["their"] = _pk_score_view(theirs)
    if game["status"] == "active":
        if mine and theirs:
            view["status"] = "done"
        elif mine or theirs:
            view["status"] = "submitted"  # one side finished
    if view["status"] in ("done",):
        ms, ts = view["my"], view["their"]
        if ms["done"] and ts["done"]:
            mp = ms["score"] / ms["total"] if ms["total"] else 0
            tp = ts["score"] / ts["total"] if ts["total"] else 0
            view["winner"] = "me" if mp > tp else ("them" if tp > mp else "draw")
        else:
            view["winner"] = "me" if ms["done"] else "them"
    return view


def _pk_score_view(rec):
    if not rec:
        return {"done": False, "score": None, "total": rec and rec.get("total"), "answered": 0}
    return {"done": True, "score": rec.get("score"), "total": rec.get("total"),
            "answered": rec.get("answered", 0)}


def _pk_maybe_expire(game):
    """Lazily expire pending games older than the invite TTL. Returns game."""
    if game.get("status") != "pending":
        return game
    try:
        created = time.mktime(time.strptime(game.get("created_at", ""), "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return game
    if time.time() - created > PK_INVITE_TTL_S:
        game["status"] = "expired"
        _write_pk(game)
    return game


def _pk_user_in(game, user):
    if game.get("mode") == "race":
        return user in game.get("players", [])
    return user in (game.get("challenger"), game.get("opponent"))


def _pk_pending_for(game, user):
    """True if `user` still needs to respond to this pending game."""
    if game.get("mode") == "race":
        return (user in game.get("players", []) and user != game.get("host")
                and user not in game.get("accepted", []))
    return game.get("opponent") == user


def pk_race_view(game, user):
    """Race game view with live standings (score desc, then duration asc)."""
    view = {"id": game["id"], "mode": "race", "host": game["host"], "me": user,
            "is_host": user == game["host"],
            "slug": game["slug"], "difficulty": game["difficulty"],
            "status": game["status"], "created_at": game.get("created_at"),
            "test_id": game.get("test_id"),
            "players": game.get("players", []), "accepted": game.get("accepted", []),
            "invited": [p for p in game.get("players", []) if p not in game.get("accepted", [])]}
    standings = []
    for p in game.get("accepted", []):
        rec = _pk_result_for(p, game["test_id"]) if game.get("test_id") else None
        standings.append({"user": p, "done": bool(rec),
                          "score": rec and rec.get("score"), "total": rec and rec.get("total"),
                          "duration_s": rec and rec.get("duration_s"),
                          "answered": (rec and rec.get("answered", 0)) or 0})
    standings.sort(key=lambda s: (not s["done"], -(s["score"] or 0), s["duration_s"] or 9e9))
    view["standings"] = standings
    if view["status"] == "active" and standings and all(s["done"] for s in standings):
        view["status"] = "done"
    view["winner"] = standings[0]["user"] if (view["status"] == "done" and standings and standings[0]["done"]) else None
    return view


def build_pk_test(game):
    """Generate the shared PK test and drop it into both players' test dirs.

    Difficulty = position window (same ratios as the UI difficulty labels):
    easy r<=0.4, medium r<=0.75, hard beyond. Returns True on success.
    """
    slug = game["slug"]
    if slug not in COMP_META:
        return False
    name, n_q, tlim, category, rounds, family = COMP_META[slug]
    if rounds:  # round-based competitions not supported in PK for now
        return False
    lo, hi = PK_LEVELS.get(game["difficulty"], PK_LEVELS["medium"])
    by_pos = {}
    for v in load_bank(slug):
        by_pos.setdefault(v["position"], []).append(v)
    positions = [p for p in range(1, n_q + 1) if lo < p / n_q <= hi]
    if not positions or any(p not in by_pos for p in positions):
        return False
    questions = []
    total_points = 0
    for i, pos in enumerate(positions, 1):
        v = random.choice(by_pos[pos])
        pts = v.get("points") or points_for(slug, None, pos)
        total_points += pts
        questions.append({
            "n": i, "source": v["source"], "question": v["question"],
            "choices": v.get("choices"), "answer": v["answer"], "solution": v.get("solution"),
            "type": v.get("type", "integer_answer" if slug == "aime" else "multiple_choice"),
            "points": pts,
        })
    level_name = game["difficulty"].capitalize()
    test_id = f"pk_{game['id']}"
    is_race = game.get("mode") == "race"
    if is_race:
        recipients = list(game.get("accepted", []))
    else:
        recipients = [game["challenger"], game["opponent"]]
    for username in recipients:
        if is_race:
            title = f"🏁 Race — {name} · {level_name}"
            instr = (f"{len(questions)} questions · PK race with {len(recipients)} players. "
                     f"Difficulty: {level_name}.")
        else:
            other = game["opponent"] if username == game["challenger"] else game["challenger"]
            title = f"⚔️ PK vs {other} — {name} · {level_name}"
            instr = f"{len(questions)} questions · PK battle vs {other}. Difficulty: {level_name}."
        test = {
            "id": test_id,
            "competition": f"PK — {name}",
            "category": category,
            "title": title,
            "instructions": instr,
            "time_limit_min": max(5, round(tlim * len(questions) / n_q)),
            "total_points": total_points,
            "questions": questions,
        }
        tdir = _tests_dir(username)
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / f"{test_id}.json").write_text(json.dumps(test, ensure_ascii=False))
    game["test_id"] = test_id
    game["status"] = "active"
    game["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return True


def _read_friends():
    return _load_json(FRIENDS_FILE, {})


def _write_friends(d):
    _save_json(FRIENDS_FILE, d)


def _friend_entry(d, user):
    return d.setdefault(user, {"friends": [], "incoming": [], "outgoing": []})


def read_messages(a, b, since=0, limit=200):
    """Messages exchanged between users a and b, ts > since, last `limit`."""
    if not MESSAGES_FILE.exists():
        return []
    out = []
    with _store_lock:
        for line in MESSAGES_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                m = json.loads(line)
            except Exception:
                continue
            pair = {m.get("frm"), m.get("to")}
            if pair == {a, b} and m.get("ts", 0) > since:
                out.append(m)
    return out[-limit:]


def append_message(frm, to, text):
    m = {"ts": time.time(), "frm": frm, "to": to, "text": text}
    with _store_lock:
        with MESSAGES_FILE.open("a") as f:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    return m


def user_paths(username):
    """Per-user storage directories."""
    base = USERS_DIR / username
    return base / "tests", base / "results.jsonl"


def round_allows_proofs(variants):
    """Allow proof problems in a round only when they are a tiny minority.

    Rule: include proofs if the round has at most 2 proof questions and at
    least 10 non-proof questions (i.e. '1-2 proof questions and tens of others').
    """
    n_total = len(variants)
    n_proof = sum(1 for v in variants if v.get("type") == "proof")
    return n_proof <= 2 and n_total - n_proof >= 10


def is_eligible(v, allow_proof=False):
    """A variant may be used only if it has a solution.

    Proof problems are excluded unless the round explicitly allows them.
    """
    if not v.get("solution"):
        return False
    if v.get("type") == "proof" and not allow_proof:
        return False
    return True


def points_for(slug, round_name, position):
    """Return the point value for a question in its actual contest format."""
    # Round-specific overrides
    if slug == "mathcounts":
        return 2 if round_name == "Target" else 1
    if round_name:
        # Most subject/team rounds award 1 point per problem.
        return 1
    pts = DEFAULT_POINTS.get(slug)
    if pts is not None:
        return pts
    # Special per-position rules for competitions not in DEFAULT_POINTS
    if slug == "mathkangaroo":
        # Approximation for the 10-question bank: 1-3 -> 3 pts, 4-7 -> 4 pts, 8-10 -> 5 pts
        return 3 if position <= 3 else 4 if position <= 7 else 5
    if slug == "ukmt":
        # SMC-style scoring: first 15 questions 4 pts, last 10 questions 5 pts
        return 4 if position <= 15 else 5
    return 1


def _tests_dir(user=None):
    if not user:
        return TESTS
    udir, _ = user_paths(user)
    udir.mkdir(parents=True, exist_ok=True)
    return udir


def _results_file(user=None):
    if not user:
        return RESULTS
    _, rfile = user_paths(user)
    rfile.parent.mkdir(parents=True, exist_ok=True)
    return rfile


def list_tests(user=None):
    out = []
    tests_dir = _tests_dir(user)
    for f in sorted(tests_dir.glob("*.json")):
        if f.name.endswith(".meta.json"):
            continue
        try:
            d = json.loads(f.read_text())
            if str(d.get("id", "")).startswith("pk_"):
                continue  # PK battles live in the PK tab, not My Tests
            out.append({
                "id": d["id"], "title": d["title"], "competition": d["competition"],
                "n_questions": len(d["questions"]), "time_limit_min": d.get("time_limit_min"),
            })
        except Exception:
            continue
    return out


def used_sources(user=None):
    """Sources already consumed by previously generated tests (no-overlap rule)."""
    used = set()
    tests_dir = _tests_dir(user)
    for f in tests_dir.glob("*_rand_*.json"):
        try:
            d = json.loads(f.read_text())
            for q in d.get("questions", []):
                if q.get("source"):
                    used.add(q["source"])
        except Exception:
            continue
    return used


def round_of(slug, source):
    pat = ROUND_PATTERNS.get(slug)
    if not pat:
        return None
    m = re.search(pat, source or "")
    if not m:
        return None
    r = m.group(1)
    return {"Nt": "Number Theory", "Combo": "Combinatorics"}.get(r, r)


def wrap_variant(v):
    """Normalise bare LaTeX in a variant's texts so KaTeX renders them."""
    for k in ("question", "solution", "explanation"):
        if isinstance(v.get(k), str):
            v[k] = wrap_bare_math(v[k])
    ch = v.get("choices")
    if isinstance(ch, list):
        v["choices"] = [wrap_bare_math(c) if isinstance(c, str) else c for c in ch]
    elif isinstance(ch, dict):
        v["choices"] = {k: wrap_bare_math(c) if isinstance(c, str) else c
                        for k, c in ch.items()}
    return v


_bank_cache = {}  # slug -> wrapped, eligible variants (banks are static at runtime)


def load_bank(slug, round_name=None):
    """All eligible variants for a slug (optionally restricted to a round).

    Excludes variants without a solution. Proof problems are excluded unless
    that round has only a tiny minority of proofs (<=2) plus many other questions.
    Results are cached: latex wrapping every variant on every request is far
    too slow (list_banks hits this for all competitions at once).
    """
    if slug not in _bank_cache:
        out = []
        for f in sorted(BANK.glob(f"{slug}_*.json")):
            try:
                d = json.loads(f.read_text())
                variants = d.get("variants", [])
                allow_proof = round_allows_proofs(variants)
                out.extend(wrap_variant(v) for v in variants if is_eligible(v, allow_proof=allow_proof))
            except Exception:
                continue
        _bank_cache[slug] = out
    variants = _bank_cache[slug]
    if round_name:
        variants = [v for v in variants if round_of(slug, v.get("source")) == round_name]
    return variants


def list_banks(user=None):
    """Generator cards: one per competition (or per round for round-based ones).

    Only counts eligible variants (with solution; proofs allowed only when that
    round has just a few proofs and many other questions).
    """
    used = used_sources(user)
    out = []
    for slug, meta in COMP_META.items():
        name, n_q, tlim, category, rounds, family = meta
        if rounds:
            for rname, (rn_q, rn_tlim) in rounds.items():
                rv = load_bank(slug, round_name=rname)
                if not rv:
                    continue
                pos_src = {}
                for v in rv:
                    pos_src.setdefault(v["position"], set()).add(v.get("source"))
                ready = len(pos_src) >= rn_q
                min_unused = min((len(s - used) for s in pos_src.values()), default=0)
                out.append({
                    "slug": slug, "round": rname, "name": f"{name} — {rname}",
                    "category": category, "family": family, "n_questions": rn_q, "time_limit_min": rn_tlim,
                    "ready": ready, "total_variants": len(rv),
                    "positions_covered": len(pos_src), "tests_remaining": min_unused,
                    "real": slug.startswith("bpho"),
                })
        else:
            rv = load_bank(slug)
            pos_src = {}
            for v in rv:
                pos_src.setdefault(v["position"], set()).add(v.get("source"))
            ready = len(pos_src) >= n_q
            counts = [len(s) for p, s in pos_src.items() if p <= n_q]
            min_src = min(counts, default=0)
            counts_unused = [len(s - used) for p, s in pos_src.items() if p <= n_q]
            out.append({
                "slug": slug, "round": None, "name": name, "category": category, "family": family,
                "n_questions": n_q, "time_limit_min": tlim, "ready": ready,
                "total_variants": len(rv), "positions_covered": len(pos_src),
                "tests_remaining": min(counts_unused, default=0), "tests_total": min_src,
                "real": slug.startswith("bpho"),
            })
    # Only expose competitions/rounds that can actually be generated right now.
    return [b for b in out if b["ready"]]


def generate_test(slug, round_name=None, user=None):
    """Assemble a new mock: one eligible variant per position, never reusing a source
    that appeared in any previously generated test.

    Returns None if any required position has no eligible variant (proof problems
    and problems without a solution are excluded).
    """
    name, n_q, tlim, category, rounds, family = COMP_META[slug]
    if rounds:
        if not round_name or round_name not in rounds:
            return None
        n_q, tlim = rounds[round_name]
        display = f"{name} — {round_name}"
    else:
        display = name
    used = used_sources(user)
    by_pos, by_pos_unused = {}, {}
    for v in load_bank(slug):
        if rounds and round_of(slug, v.get("source")) != round_name:
            continue
        by_pos.setdefault(v["position"], {})[v["source"]] = v
        if v["source"] not in used:
            by_pos_unused.setdefault(v["position"], {})[v["source"]] = v
    # All positions 1..n_q must have at least one eligible variant.
    if set(range(1, n_q + 1)) - set(by_pos.keys()):
        return None
    questions = []
    reused = 0
    total_points = 0
    for pos in range(1, n_q + 1):
        # Prefer unused sources; do not fall back to already-used sources.
        pool = by_pos_unused.get(pos)
        if not pool:
            reused += 1
            pool = by_pos[pos]
        v = random.choice(list(pool.values()))
        pts = v.get("points") or points_for(slug, round_name, pos)
        total_points += pts
        questions.append({
            "n": pos, "source": v["source"], "question": v["question"],
            "choices": v.get("choices"), "answer": v["answer"], "solution": v.get("solution"),
            "type": v.get("type", "integer_answer" if slug == "aime" else "multiple_choice"),
            "points": pts,
        })
    integer = slug in ("aime", "mathcounts")
    calc = " · Calculator allowed" if slug.startswith("bpho") else " · No calculator"
    tests_dir = _tests_dir(user)
    n_existing = len(list(tests_dir.glob(f"{slug}_rand_*.json")))
    point_line = f"{total_points} points total."
    instr_extra = ("Answers are integers from 000 to 999. " + point_line if integer
                   else point_line)
    gen_time = time.strftime("%Y-%m-%d %H:%M")
    test = {
        "id": f"{slug}_rand_{n_existing + 1:02d}",
        "competition": display,
        "category": category,
        "title": f"{display} — Random Mock #{n_existing + 1} · {gen_time}",
        "instructions": f"{n_q} questions · {tlim} minutes{calc}. " + instr_extra,
        "time_limit_min": tlim,
        "total_points": total_points,
        "questions": questions,
    }
    (tests_dir / f"{test['id']}.json").write_text(json.dumps(test, ensure_ascii=False, indent=1))
    test["reused_positions"] = reused
    return test


def read_results(user=None):
    rfile = _results_file(user)
    if not rfile.exists():
        return []
    out = []
    for line in rfile.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def compute_stats(user=None):
    results = [r for r in read_results(user)
               if not str(r.get("test_id", "")).startswith("pk_")]
    per_comp = {}
    for r in results:
        c = per_comp.setdefault(r["competition"], {"attempts": 0, "scores": []})
        c["attempts"] += 1
        if r.get("total"):
            c["scores"].append(r["score"] / r["total"] * 100)
    comps = []
    for name, c in sorted(per_comp.items()):
        comps.append({
            "competition": name,
            "attempts": c["attempts"],
            "avg_pct": round(sum(c["scores"]) / len(c["scores"]), 1) if c["scores"] else None,
            "best_pct": round(max(c["scores"]), 1) if c["scores"] else None,
        })
    graded = [r for r in results if r.get("total")]
    return {
        "total_attempts": len(results),
        "total_questions_answered": sum(r.get("answered", 0) for r in results),
        "avg_pct": round(sum(r["score"] / r["total"] * 100 for r in graded) / len(graded), 1) if graded else None,
        "per_competition": comps,
    }


class Handler(BaseHTTPRequestHandler):
    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def _cookie(self, name, value=None, max_age=None, clear=False):
        if clear:
            return f"{name}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
        return f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict"

    def _send(self, body, ctype="application/json", code=200, cookies=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if cookies:
            for c in cookies:
                self.send_header("Set-Cookie", c)
        self.end_headers()
        self.wfile.write(data)

    def _user(self):
        return current_user(self.headers.get("Cookie"))

    def _test_file(self, test_id, user):
        tests_dir = _tests_dir(user)
        f = tests_dir / f"{test_id}.json"
        if f.exists():
            return f
        # fallback to global tests for backward compatibility
        f = TESTS / f"{test_id}.json"
        return f if f.exists() else None

    def do_GET(self):
        path = self.path.split("?")[0]
        user = self._user()
        if path == "/":
            self._send((STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/me":
            info = {"user": user}
            if user:
                u = _read_users().get(user) or {}
                info["role"] = u.get("role", "student")
                if u.get("school"):
                    info["school"] = u["school"]
            self._send(json.dumps(info))
        elif path == "/api/tests":
            self._send(json.dumps(list_tests(user)))
        elif path == "/api/banks":
            self._send(json.dumps(list_banks(user)))
        elif m := re.match(r"^/api/generate/([a-z0-9_]+)(?:/(.+))?$", path):
            from urllib.parse import unquote
            test = generate_test(m.group(1), unquote(m.group(2)) if m.group(2) else None, user)
            if test:
                self._send(json.dumps({"ok": True, "id": test["id"]}))
            else:
                self._send('{"error": "bank incomplete for this competition"}', code=400)
        elif path == "/api/announcements":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                f = ROOT / "announcements.json"
                try:
                    items = json.loads(f.read_text()) if f.exists() else []
                except Exception:
                    items = []
                self._send(json.dumps({"announcements": items}))
        elif path == "/api/friends":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                d = _read_friends()
                mine = _friend_entry(d, user)
                friends = [{"username": f, "online": is_online(f)} for f in mine["friends"]]
                self._send(json.dumps({
                    "friends": friends,
                    "incoming": mine["incoming"],
                    "outgoing": mine["outgoing"],
                }))
        elif m := re.match(r"^/api/chat/([a-z0-9_]+)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                other = m.group(1)
                mine = _friend_entry(_read_friends(), user)
                if other not in mine["friends"]:
                    self._send('{"error": "not friends"}', code=403)
                else:
                    from urllib.parse import parse_qs, urlparse
                    qs = parse_qs(urlparse(self.path).query)
                    try:
                        since = float(qs.get("since", [0])[0])
                    except ValueError:
                        since = 0
                    msgs = read_messages(user, other, since)
                    self._send(json.dumps({"messages": msgs, "online": is_online(other)}))
        elif path == "/api/pk":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                games = []
                if PK_DIR.exists():
                    for f in sorted(PK_DIR.glob("*.json")):
                        try:
                            g = json.loads(f.read_text())
                        except Exception:
                            continue
                        if _pk_user_in(g, user):
                            games.append(_pk_maybe_expire(g))
                games.sort(key=lambda g: g.get("created_at", ""), reverse=True)
                views = [(pk_race_view if g.get("mode") == "race" else pk_game_view)(g, user) for g in games[:50]]
                self._send(json.dumps({
                    "games": views,
                    "levels": sorted(PK_LEVELS),
                }))
        elif path == "/api/pk/invites":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                invites = []
                if PK_DIR.exists():
                    for f in PK_DIR.glob("*.json"):
                        try:
                            g = json.loads(f.read_text())
                        except Exception:
                            continue
                        g = _pk_maybe_expire(g)
                        if g.get("status") == "pending" and _pk_pending_for(g, user):
                            if g.get("mode") == "race":
                                others = [p for p in g.get("players", [])
                                          if p not in (user, g.get("host"))]
                                invites.append({"game_id": g["id"], "mode": "race",
                                                "from": g.get("host"), "others": others,
                                                "slug": g.get("slug"), "difficulty": g.get("difficulty")})
                            else:
                                invites.append({"game_id": g["id"], "mode": "duel",
                                                "from": g.get("challenger"),
                                                "slug": g.get("slug"), "difficulty": g.get("difficulty")})
                invites.sort(key=lambda i: i["game_id"])
                self._send(json.dumps({"count": len(invites), "invites": invites}))
        elif path == "/api/friends/badge":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                mine = _friend_entry(_read_friends(), user)
                self._send(json.dumps({"count": len(mine.get("incoming", []))}))
        elif m := re.match(r"^/api/pk/([a-z0-9_]+)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                g = _read_pk(m.group(1))
                if not g or not _pk_user_in(g, user):
                    self._send('{"error": "not found"}', code=404)
                else:
                    g = _pk_maybe_expire(g)
                    view = pk_race_view(g, user) if g.get("mode") == "race" else pk_game_view(g, user)
                    self._send(json.dumps(view))
        elif path == "/api/results":
            # PK attempts show up in the PK tab history, not in My Tests
            results = [r for r in read_results(user)
                       if not str(r.get("test_id", "")).startswith("pk_")]
            self._send(json.dumps(results))
        elif path == "/api/classes":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                classes = _read_classes()
                teaching = [{"code": c["code"], "name": c["name"], "school": c["school"],
                             "students": c.get("students", [])}
                            for c in classes.values() if c.get("teacher") == user]
                joined = [{"code": c["code"], "name": c["name"], "school": c["school"],
                           "teacher": c.get("teacher")}
                          for c in classes.values() if user in c.get("students", [])]
                self._send(json.dumps({"teaching": teaching, "joined": joined}))
        elif m := re.match(r"^/api/class/([A-Za-z0-9_-]+)/reports$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                c = _read_classes().get(m.group(1))
                if not c or c.get("teacher") != user:
                    self._send('{"error": "not found"}', code=404)
                else:
                    reps = []
                    if CLASS_REPORTS_FILE.exists():
                        for line in CLASS_REPORTS_FILE.read_text().splitlines():
                            if not line.strip():
                                continue
                            try:
                                r = json.loads(line)
                            except Exception:
                                continue
                            if r.get("class_id") == c["code"]:
                                reps.append(r)
                    self._send(json.dumps({"reports": list(reversed(reps))[:200]}))
        elif path == "/api/stats":
            self._send(json.dumps(compute_stats(user)))
        elif m := re.match(r"^/api/test/([a-z0-9_]+)$", path):
            f = self._test_file(m.group(1), user)
            if f and f.exists():
                self._send(f.read_bytes())
            else:
                self._send('{"error": "not found"}', code=404)
        else:
            self._send('{"error": "not found"}', code=404)

    def do_POST(self):
        path = self.path.split("?")[0]
        user = self._user()
        if path == "/api/register":
            data = self._read_body()
            username = (data.get("username") or "").strip().lower()
            password = data.get("password") or ""
            if not username or not password:
                self._send(json.dumps({"error": "username and password required"}), code=400)
                return
            if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
                self._send(json.dumps({"error": "username must be 3-32 chars, lowercase letters/numbers/underscore"}), code=400)
                return
            users = _read_users()
            if username in users:
                self._send(json.dumps({"error": "username taken"}), code=409)
                return
            role = data.get("role") or "student"
            if role not in ("student", "teacher"):
                role = "student"
            school = (data.get("school") or "").strip()[:80]
            if role == "teacher" and not school:
                self._send(json.dumps({"error": "school / organization name required for teacher accounts"}), code=400)
                return
            salt, key = _hash_password(password)
            users[username] = {"username": username, "salt": salt, "key": key,
                               "role": role, "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            if school:
                users[username]["school"] = school
            _write_users(users)
            sid = _make_session(username)
            self._send(json.dumps({"ok": True, "user": username}), cookies=[self._cookie("session_id", sid, SESSION_DAYS * 86400)])
        elif path == "/api/login":
            data = self._read_body()
            username = (data.get("username") or "").strip().lower()
            password = data.get("password") or ""
            users = _read_users()
            u = users.get(username)
            if not u or not _verify_password(password, u["salt"], u["key"]):
                self._send(json.dumps({"error": "invalid username or password"}), code=401)
                return
            sid = _make_session(username)
            self._send(json.dumps({"ok": True, "user": username}), cookies=[self._cookie("session_id", sid, SESSION_DAYS * 86400)])
        elif path == "/api/logout":
            cookies = _parse_cookies(self.headers.get("Cookie"))
            sid = cookies.get("session_id")
            if sid:
                _delete_session(sid)
            self._send(json.dumps({"ok": True}), cookies=[self._cookie("session_id", clear=True)])
        elif path == "/api/result":
            if not user:
                # guests can take tests but results aren't persisted
                self._send('{"ok": true, "guest": true}')
                return
            try:
                data = self._read_body()
                rfile = _results_file(user)
                rec = {
                    "test_id": data.get("test_id"),
                    "title": data.get("title"),
                    "competition": data.get("competition"),
                    "score": data.get("score"),
                    "total": data.get("total"),
                    "answered": data.get("answered", 0),
                    "duration_s": data.get("duration_s"),
                    "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "user": user,
                }
                rfile.parent.mkdir(parents=True, exist_ok=True)
                with rfile.open("a") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                # push a report copy to every class this student belongs to
                try:
                    mine = [c for c in _read_classes().values() if user in c.get("students", [])]
                    if mine:
                        total = rec.get("total")
                        pct = round(rec["score"] / total * 100, 1) if total else None
                        with _store_lock:
                            with CLASS_REPORTS_FILE.open("a") as f:
                                for c in mine:
                                    rep = {"class_id": c["code"], "student": user,
                                           "test_id": rec.get("test_id"), "title": rec.get("title"),
                                           "competition": rec.get("competition"),
                                           "score": rec.get("score"), "total": total, "pct": pct,
                                           "answered": rec.get("answered", 0),
                                           "duration_s": rec.get("duration_s"),
                                           "submitted_at": rec.get("submitted_at")}
                                    f.write(json.dumps(rep, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                self._send('{"ok": true}')
            except Exception as e:
                self._send(json.dumps({"error": str(e)}), code=400)
        elif m := re.match(r"^/api/friends/(request|accept|decline|remove)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                data = self._read_body()
                other = (data.get("username") or "").strip().lower()
                users = _read_users()
                action = m.group(1)
                if not other or other == user:
                    self._send('{"error": "invalid username"}', code=400)
                elif other not in users:
                    self._send('{"error": "user not found"}', code=404)
                else:
                    d = _read_friends()
                    mine = _friend_entry(d, user)
                    theirs = _friend_entry(d, other)
                    if action == "request":
                        if other in mine["friends"]:
                            self._send('{"error": "already friends"}', code=409)
                        elif user in theirs["incoming"] or other in mine["outgoing"]:
                            self._send('{"error": "request already sent"}', code=409)
                        else:
                            mine["outgoing"].append(other)
                            theirs["incoming"].append(user)
                            _write_friends(d)
                            self._send('{"ok": true}')
                    elif action in ("accept", "decline"):
                        if user not in theirs["outgoing"] or other not in mine["incoming"]:
                            self._send('{"error": "no such request"}', code=404)
                        else:
                            theirs["outgoing"].remove(user)
                            mine["incoming"].remove(other)
                            if action == "accept":
                                if other not in mine["friends"]:
                                    mine["friends"].append(other)
                                if user not in theirs["friends"]:
                                    theirs["friends"].append(user)
                            _write_friends(d)
                            self._send('{"ok": true}')
                    else:  # remove
                        if other not in mine["friends"]:
                            self._send('{"error": "not friends"}', code=404)
                        else:
                            mine["friends"].remove(other)
                            if user in theirs["friends"]:
                                theirs["friends"].remove(user)
                            _write_friends(d)
                            self._send('{"ok": true}')
        elif m := re.match(r"^/api/chat/([a-z0-9_]+)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                other = m.group(1)
                mine = _friend_entry(_read_friends(), user)
                if other not in mine["friends"]:
                    self._send('{"error": "not friends"}', code=403)
                else:
                    data = self._read_body()
                    text = (data.get("text") or "").strip()[:500]
                    if not text:
                        self._send('{"error": "empty message"}', code=400)
                    else:
                        msg = append_message(user, other, text)
                        self._send(json.dumps({"ok": True, "message": msg}))
        elif path == "/api/class/create":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                u = _read_users().get(user) or {}
                if u.get("role", "student") != "teacher":
                    self._send('{"error": "teacher account required"}', code=403)
                else:
                    data = self._read_body()
                    name = (data.get("name") or "").strip()[:60]
                    code = (data.get("code") or "").strip().upper().replace(" ", "-")
                    if not name or not re.fullmatch(r"[A-Z0-9_-]{3,24}", code):
                        self._send(json.dumps({"error": "class name and a 3-24 char code (letters/numbers/-_) required"}), code=400)
                    else:
                        classes = _read_classes()
                        if code in classes:
                            self._send(json.dumps({"error": "code already taken"}), code=409)
                        else:
                            classes[code] = {"code": code, "name": name,
                                             "school": u.get("school", ""),
                                             "teacher": user, "students": [],
                                             "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                            _write_classes(classes)
                            self._send(json.dumps({"ok": True, "code": code}))
        elif path == "/api/class/join":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                data = self._read_body()
                code = (data.get("code") or "").strip().upper().replace(" ", "-")
                classes = _read_classes()
                c = classes.get(code)
                if not c:
                    self._send(json.dumps({"error": "invalid class code"}), code=404)
                elif user == c.get("teacher"):
                    self._send(json.dumps({"error": "you teach this class"}), code=400)
                else:
                    if user not in c["students"]:
                        c["students"].append(user)
                        _write_classes(classes)
                    self._send(json.dumps({"ok": True, "name": c["name"], "school": c["school"]}))
        elif m := re.match(r"^/api/pk/(challenge|respond|start)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                data = self._read_body()
                action = m.group(1)
                if action == "challenge":
                    mode = data.get("mode") or "duel"
                    slug = (data.get("slug") or "").strip()
                    difficulty = (data.get("difficulty") or "").strip()
                    if slug not in COMP_META or COMP_META[slug][4]:
                        self._send(json.dumps({"error": "competition not available for PK"}), code=400)
                    elif difficulty not in PK_LEVELS:
                        self._send(json.dumps({"error": "invalid difficulty"}), code=400)
                    else:
                        gid = secrets.token_hex(8)
                        now = time.strftime("%Y-%m-%d %H:%M:%S")
                        if mode == "race":
                            ops = [o.strip().lower() for o in (data.get("opponents") or []) if isinstance(o, str)][:20]
                            ops = [o for o in dict.fromkeys(ops) if o and o != user]
                            mine = _friend_entry(_read_friends(), user)
                            if not ops or any(o not in mine["friends"] for o in ops):
                                self._send(json.dumps({"error": "pick at least one friend to invite"}), code=403)
                                return
                            game = {"id": gid, "mode": "race", "host": user,
                                    "players": [user] + ops, "accepted": [user],
                                    "slug": slug, "difficulty": difficulty,
                                    "status": "pending", "test_id": None, "created_at": now}
                        else:
                            opponent = (data.get("opponent") or "").strip().lower()
                            mine = _friend_entry(_read_friends(), user)
                            if opponent not in mine["friends"]:
                                self._send(json.dumps({"error": "not friends"}), code=403)
                                return
                            game = {"id": gid, "challenger": user, "opponent": opponent,
                                    "slug": slug, "difficulty": difficulty,
                                    "status": "pending", "test_id": None, "created_at": now}
                        _write_pk(game)
                        self._send(json.dumps({"ok": True, "id": gid}))
                elif action == "start":
                    gid = (data.get("game_id") or "").strip()
                    game = _read_pk(gid)
                    if not game or game.get("mode") != "race" or game.get("host") != user:
                        self._send('{"error": "not found"}', code=404)
                    elif game["status"] != "pending":
                        self._send('{"error": "already started"}', code=409)
                    elif len(game.get("accepted", [])) < 2:
                        self._send(json.dumps({"error": "need at least 2 accepted players"}), code=400)
                    elif build_pk_test(game):
                        _write_pk(game)
                        self._send(json.dumps({"ok": True, "test_id": game["test_id"]}))
                    else:
                        self._send('{"error": "could not build test for this competition"}', code=400)
                else:
                    gid = (data.get("game_id") or "").strip()
                    accept = bool(data.get("accept"))
                    game = _read_pk(gid)
                    if not game or not _pk_user_in(game, user):
                        self._send('{"error": "not found"}', code=404)
                    elif game["status"] != "pending":
                        self._send('{"error": "already responded"}', code=409)
                    elif game.get("mode") == "race":
                        if accept:
                            if user not in game["accepted"]:
                                game["accepted"].append(user)
                            _write_pk(game)
                            self._send('{"ok": true}')
                        else:
                            game["players"].remove(user)
                            if len(game["players"]) <= 1:
                                game["status"] = "declined"
                            _write_pk(game)
                            self._send('{"ok": true}')
                    elif not accept:
                        game["status"] = "declined"
                        _write_pk(game)
                        self._send('{"ok": true}')
                    elif build_pk_test(game):
                        _write_pk(game)
                        self._send(json.dumps({"ok": True, "test_id": game["test_id"]}))
                    else:
                        self._send('{"error": "could not build test for this competition"}', code=400)
        else:
            self._send('{"error": "not found"}', code=404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"MockTest Maker → http://localhost:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

"""MockTest Maker — localhost web app.

Run:  .venv/bin/python app/server.py  (then open http://localhost:8000)
Stdlib only. Serves tests from tests/*.json, generates new tests from bank/<slug>_*.json.
"""
import json
import random
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
BANK = ROOT / "bank"
STATIC = ROOT / "app" / "static"
RESULTS = ROOT / "results.jsonl"
PORT = 8000

COMP_META = {  # slug -> (display name, question count, time limit min, category, rounds)
    "amc8": ("AMC 8", 25, 40, "Math", None),
    "amc10": ("AMC 10", 25, 75, "Math", None),
    "amc12": ("AMC 12", 25, 75, "Math", None),
    "aime": ("AIME", 15, 180, "Math", None),
    "imo": ("IMO", 6, 270, "Math", None),
    "usamo": ("USAMO", 6, 270, "Math", None),
    "putnam": ("Putnam", 12, 360, "Math", None),
    "apmo": ("APMO", 5, 240, "Math", None),
    "hmmt": ("HMMT", 10, 50, "Math", {"General": (10, 50), "Theme": (10, 50)}),
    "mathcounts": ("MATHCOUNTS", 30, 40, "Math", {"Sprint": (30, 40), "Target": (8, 24), "Team": (10, 20)}),
    "smt": ("SMT", 25, 110, "Math", {"General": (25, 110), "Algebra": (10, 50), "Calculus": (10, 50), "Discrete": (10, 50), "Geometry": (10, 50), "Team": (15, 50)}),
    "pumac": ("PUMaC", 8, 60, "Math", {"Algebra": (8, 60), "Geometry": (8, 60), "Combinatorics": (8, 60), "Number Theory": (8, 60), "Individual Finals": (4, 60), "Team": (15, 90), "Power": (11, 90)}),
    "bmt": ("BMT", 25, 90, "Math", {"General": (25, 90), "Algebra": (11, 60), "Calculus": (11, 60), "Discrete": (11, 60), "Geometry": (11, 60), "Guts": (27, 75), "Power": (3, 60)}),
    "cmimc": ("CMIMC", 10, 60, "Math", {"Algebra": (10, 50), "Combinatorics": (10, 50), "Geometry": (10, 50), "Computer Science": (10, 50), "Team": (10, 30)}),
    "comc": ("COMC", 8, 150, "Math", None),
    "cmo": ("CMO", 5, 180, "Math", None),
    "usamts": ("USAMTS", 5, 240, "Math", None),
    "ukmt": ("UKMT", 25, 60, "Math", None),
    "mathkangaroo": ("Math Kangaroo", 10, 45, "Math", None),
    "fma": ("F=ma", 15, 45, "Physics", None),
    "physicsbowl": ("Physics Bowl", 15, 45, "Physics", None),
}

ROUND_PATTERNS = {  # slug -> regex extracting round name from a variant's source string
    "mathcounts": r"(Sprint|Target|Team)",
    "hmmt": r"(General|Theme)",
    "smt": r"SMT (\w+) Problem",
    "pumac": r"PUMaC ([\w ]+?) Problem",
    "bmt": r"(?:BMT|BmMT) (\w+) Problem",
    "cmimc": r"CMIMC ([\w ]+?) Problem",
}

CATEGORY_ORDER = ["Math", "Physics", "Chemistry", "Biology", "Informatics",
                  "Astronomy & Earth", "Economics", "Linguistics", "Other"]


def list_tests():
    out = []
    for f in sorted(TESTS.glob("*.json")):
        if f.name.endswith(".meta.json"):
            continue
        try:
            d = json.loads(f.read_text())
            out.append({
                "id": d["id"], "title": d["title"], "competition": d["competition"],
                "n_questions": len(d["questions"]), "time_limit_min": d.get("time_limit_min"),
            })
        except Exception:
            continue
    return out


def used_sources():
    """Sources already consumed by previously generated tests (no-overlap rule)."""
    used = set()
    for f in TESTS.glob("*_rand_*.json"):
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


def load_bank(slug):
    """All variants for a slug as a flat list."""
    out = []
    for f in sorted(BANK.glob(f"{slug}_*.json")):
        try:
            d = json.loads(f.read_text())
            out.extend(d.get("variants", []))
        except Exception:
            continue
    return out


def list_banks():
    """Generator cards: one per competition (or per round for round-based ones)."""
    used = used_sources()
    by_slug = {}
    for f in sorted(BANK.glob("*_*.json")):
        slug = f.name.split("_")[0]
        try:
            d = json.loads(f.read_text())
            by_slug.setdefault(slug, []).extend(d.get("variants", []))
        except Exception:
            continue
    out = []
    for slug, variants in by_slug.items():
        if slug not in COMP_META:
            continue
        name, n_q, tlim, category, rounds = COMP_META[slug]
        if rounds:
            for rname, (rn_q, rn_tlim) in rounds.items():
                rv = [v for v in variants if round_of(slug, v.get("source")) == rname]
                if not rv:
                    continue
                pos_src = {}
                for v in rv:
                    pos_src.setdefault(v["position"], set()).add(v.get("source"))
                ready = len(pos_src) >= rn_q
                min_unused = min((len(s - used) for s in pos_src.values()), default=0)
                out.append({
                    "slug": slug, "round": rname, "name": f"{name} — {rname}",
                    "category": category, "n_questions": rn_q, "time_limit_min": rn_tlim,
                    "ready": ready, "total_variants": len(rv),
                    "positions_covered": len(pos_src), "tests_remaining": min_unused,
                })
        else:
            pos_src = {}
            for v in variants:
                pos_src.setdefault(v["position"], set()).add(v.get("source"))
            ready = len(pos_src) >= n_q
            counts = [len(s) for p, s in pos_src.items() if p <= n_q]
            min_src = min(counts, default=0)
            counts_unused = [len(s - used) for p, s in pos_src.items() if p <= n_q]
            out.append({
                "slug": slug, "round": None, "name": name, "category": category,
                "n_questions": n_q, "time_limit_min": tlim, "ready": ready,
                "total_variants": len(variants), "positions_covered": len(pos_src),
                "tests_remaining": min(counts_unused, default=0), "tests_total": min_src,
            })
    return out


def generate_test(slug, round_name=None):
    """Assemble a new mock: one variant per position, never reusing a source
    that appeared in any previously generated test."""
    name, n_q, tlim, category, rounds = COMP_META[slug]
    if rounds:
        if not round_name or round_name not in rounds:
            return None
        n_q, tlim = rounds[round_name]
        display = f"{name} — {round_name}"
    else:
        display = name
    used = used_sources()
    by_pos, by_pos_unused = {}, {}
    for v in load_bank(slug):
        if rounds and round_of(slug, v.get("source")) != round_name:
            continue
        by_pos.setdefault(v["position"], {})[v["source"]] = v
        if v["source"] not in used:
            by_pos_unused.setdefault(v["position"], {})[v["source"]] = v
    if len(by_pos) < n_q:
        return None
    questions = []
    reused = 0
    for pos in range(1, n_q + 1):
        pool = by_pos_unused.get(pos) or by_pos[pos]  # fallback if pool exhausted
        if not by_pos_unused.get(pos):
            reused += 1
        v = random.choice(list(pool.values()))
        questions.append({
            "n": pos, "source": v["source"], "question": v["question"],
            "choices": v["choices"], "answer": v["answer"], "solution": v.get("solution"),
            "type": v.get("type", "integer_answer" if slug == "aime" else "multiple_choice"),
        })
    integer = slug in ("aime", "mathcounts")
    proof = slug in ("imo", "usamo", "putnam", "apmo", "hmmt", "pumac", "usamts", "cmo", "comc", "cmimc", "bmt", "smt")
    n_existing = len(list(TESTS.glob(f"{slug}_rand_*.json")))
    instr_extra = ("Answers are integers from 000 to 999." if integer
                   else "Proof-based problems: write full solutions, then compare with the official solutions." if proof
                   else "1 point per correct answer, no penalty for wrong answers.")
    gen_time = time.strftime("%Y-%m-%d %H:%M")
    test = {
        "id": f"{slug}_rand_{n_existing + 1:02d}",
        "competition": display,
        "category": category,
        "title": f"{display} — Random Mock #{n_existing + 1} · {gen_time}",
        "instructions": f"{n_q} questions · {tlim} minutes · No calculator. " + instr_extra,
        "time_limit_min": tlim,
        "questions": questions,
    }
    (TESTS / f"{test['id']}.json").write_text(json.dumps(test, ensure_ascii=False, indent=1))
    test["reused_positions"] = reused
    return test


def read_results():
    if not RESULTS.exists():
        return []
    out = []
    for line in RESULTS.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def compute_stats():
    results = read_results()
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
    def _send(self, body, ctype="application/json", code=200):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send((STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/tests":
            self._send(json.dumps(list_tests()))
        elif path == "/api/banks":
            self._send(json.dumps(list_banks()))
        elif m := re.match(r"^/api/generate/([a-z0-9]+)(?:/(.+))?$", path):
            from urllib.parse import unquote
            test = generate_test(m.group(1), unquote(m.group(2)) if m.group(2) else None)
            if test:
                self._send(json.dumps({"ok": True, "id": test["id"]}))
            else:
                self._send('{"error": "bank incomplete for this competition"}', code=400)
        elif path == "/api/results":
            self._send(json.dumps(read_results()))
        elif path == "/api/stats":
            self._send(json.dumps(compute_stats()))
        elif m := re.match(r"^/api/test/([a-z0-9_]+)$", path):
            f = TESTS / f"{m.group(1)}.json"
            if f.exists():
                self._send(f.read_bytes())
            else:
                self._send('{"error": "not found"}', code=404)
        else:
            self._send('{"error": "not found"}', code=404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/result":
            n = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
                rec = {
                    "test_id": data.get("test_id"),
                    "title": data.get("title"),
                    "competition": data.get("competition"),
                    "score": data.get("score"),
                    "total": data.get("total"),
                    "answered": data.get("answered", 0),
                    "duration_s": data.get("duration_s"),
                    "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                with RESULTS.open("a") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                self._send('{"ok": true}')
            except Exception as e:
                self._send(json.dumps({"error": str(e)}), code=400)
        else:
            self._send('{"error": "not found"}', code=404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"MockTest Maker → http://localhost:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

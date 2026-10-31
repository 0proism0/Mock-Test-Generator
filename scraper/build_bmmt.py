"""Build BMmT (Berkeley mini Math Tournament) bank from berkeley.mt event archives.

Ingests the Individual and Team rounds (2021-2025) — both are short-answer
rounds in the same format as BMT: numbered problems, "Answer:"/"Solution:" in
the official solution PDFs. Skips relay (chained answers), pacer (live round),
puzzle (cross-number grids), tiebreakers, and 2012-2019 (legacy PDF naming).
Answers and worked solutions are extracted from the official solution PDFs.
Entries whose answer is an integer get exact-match grading ("integer"),
plain decimals get 2%-tolerance grading ("numeric"); everything else stays
proof-type with the worked solution attached (shown, not auto-graded).
"""
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "bmmt"
PDF_DIR.mkdir(parents=True, exist_ok=True)
BASE = "https://berkeley.mt"
UA = {"User-Agent": "Mozilla/5.0"}

ROUND_NAMES = {"individual": "Individual", "team": "Team"}
FIRST_YEAR = 2021  # earlier events use legacy PDF naming; 2026 has no solutions yet

# Running heads/footers that pypdf leaks into the text stream.
HEADER = re.compile(r"^BmMT \d{4} .*$", re.M)


def _text(path):
    out = []
    for p in PdfReader(path).pages:
        try:
            out.append(p.extract_text())
        except Exception:
            continue
    return HEADER.sub("", "\n".join(out))


def parse_problems(text):
    parts = re.split(r"\n(?=\d{1,2}[\.\)] )", text)
    probs = {}
    for part in parts:
        m = re.match(r"\s*(\d{1,2})[\.\)]\s*", part)
        if not m:
            continue
        probs[int(m.group(1))] = re.sub(r"\s+", " ", part[m.end():]).strip()
    return probs


def parse_solutions(text, ns):
    """Return {n: (answer, solution)} (same approach as build_bmt.py)."""
    cands = [(int(m.group(1)), m.start())
             for m in re.finditer(r"(?m)^(\d{1,2})[\.\)] ", text)]
    chosen = []
    used = set()
    for n in ns:
        pick = None
        for i, (cn, pos) in enumerate(cands):
            if i in used or cn != n:
                continue
            if "Answer:" in text[pos:pos + 700]:
                pick = i
                break
            if pick is None:
                pick = i
        if pick is None:
            continue
        used.add(pick)
        chosen.append(cands[pick])
    out = {}
    for j, (n, pos) in enumerate(chosen):
        end = chosen[j + 1][1] if j + 1 < len(chosen) else len(text)
        body = text[pos:end]
        am = re.search(r"Answer:\s*", body)
        if not am:
            out[n] = (None, _clean(body))
            continue
        rest = body[am.end():]
        sm = re.search(r"Solution(?: \d+)?:\s*", rest)
        if sm:
            ans, sol = rest[:sm.start()], rest[sm.end():]
        else:
            ans, sol = rest, None
        out[n] = (_clean(ans), _clean(sol) if sol else None)
    return out


def _clean(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.split(r"Solution 2:", s)[0].strip()
    return s[:1200]


def normalize_answer(a):
    """Normalise a raw answer string; return None if not a plain number."""
    if not a:
        return None
    a = a.replace("−", "-").strip().rstrip(".")
    m = re.search(r"or (-?\d+\.\d+)$", a)
    if m:
        a = m.group(1)
    a = re.sub(r"(\d) \.(\d)", r"\1.\2", a)
    a = a.replace(",", "")
    if re.fullmatch(r"-?\d+", a):
        return a
    if re.fullmatch(r"-?\d+\.\d+", a):
        return a
    return None


def main():
    html = requests.get(f"{BASE}/archives/", headers=UA, timeout=30).text
    soup = BeautifulSoup(html, "lxml")
    events = sorted({a["href"] for a in soup.find_all("a", href=True)
                     if re.search(r"/archives/bmmt-\d{4}", a["href"])})
    print(len(events), "events")
    variants = []
    for ev in events:
        slug = ev.rstrip("/").split("/")[-1]
        m = re.search(r"bmmt-(\d{4})", slug)
        if not m:
            continue
        year = int(m.group(1))
        if year < FIRST_YEAR or "online" in slug:
            continue  # online events duplicate the canonical year's problems
        try:
            ev_url = ev if ev.startswith("http") else f"{BASE}{ev}"
            page = requests.get(ev_url, headers=UA, timeout=30).text
        except Exception:
            continue
        soup2 = BeautifulSoup(page, "lxml")
        hrefs = {a["href"] for a in soup2.find_all("a", href=True)
                 if a["href"].endswith(".pdf") and "results" not in a["href"]}
        prob_hrefs = sorted(h for h in hrefs if h.endswith("-problems.pdf"))
        for href in prob_hrefs:
            stem = href.split("/")[-1].replace("-problems.pdf", "")
            if stem not in ROUND_NAMES:
                continue
            rnd = stem
            rname = ROUND_NAMES[rnd]
            sol_href = href.replace("-problems.pdf", "-solutions.pdf")

            def fetch(name, h):
                pf = PDF_DIR / f"{slug}_{rnd}{name}.pdf"
                if pf.exists():
                    return pf
                url = h if h.startswith("http") else (ev + h if ev.endswith("/") else ev + "/" + h)
                try:
                    r = requests.get(url, headers=UA, timeout=40)
                    if r.status_code == 200 and r.content.startswith(b"%PDF"):
                        pf.write_bytes(r.content)
                        time.sleep(0.3)
                        return pf
                except Exception:
                    pass
                return None

            try:
                pf = fetch("", href)
                if not pf:
                    continue
                probs = parse_problems(_text(pf))
                sols = {}
                sf = fetch("_solutions", sol_href) if sol_href in hrefs else None
                if not sf:
                    print(slug, rnd, "no solutions PDF — skipped")
                    continue
                sols = parse_solutions(_text(sf), sorted(probs))
            except Exception as e:
                print("fail", slug, rnd, e)
                continue
            n_with_ans = 0
            for n, q in probs.items():
                if n > 25:
                    continue  # page-number artifacts (e.g. a stray "41.")
                if len(q) < 25 or re.search(r"submit an integer between", q, re.I):
                    continue
                ans_raw, sol = sols.get(n, (None, None))
                ans = normalize_answer(ans_raw)
                if ans is not None:
                    qtype = "integer" if re.fullmatch(r"-?\d+", ans) else "numeric"
                    if not sol:
                        sol = f"Answer: {ans}."
                    n_with_ans += 1
                else:
                    qtype = "proof"
                variants.append({
                    "position": n,
                    "source": f"{year} BMMT {rname} Problem {n}",
                    "question": q, "choices": None, "answer": ans, "type": qtype,
                    "solution": sol,
                    "has_diagram": "diagram" in q.lower() or "figure" in q.lower() or "shown" in q.lower(),
                })
            print(slug, rnd, len(probs), f"({n_with_ans} with numeric answer)")
    json.dump({"competition": "BMMT", "set": "A", "variants": variants},
              open(ROOT / "bank" / "bmmt_A.json", "w"), ensure_ascii=False, indent=1)
    print("TOTAL:", len(variants))


if __name__ == "__main__":
    main()

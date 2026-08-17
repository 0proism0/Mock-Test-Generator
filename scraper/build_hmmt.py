"""Build HMMT bank from hmmt.org archive solutions PDFs.

Downloads gen/thm round solutions PDFs (they contain problem + Answer + Solution),
parses them into bank/hmmt_A.json (type: proof-style, real problems).
"""
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "hmmt"
PDF_DIR.mkdir(parents=True, exist_ok=True)
BASE = "https://www.hmmt.org"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/125.0.0.0 Safari/537.36"}

ROUND_NAMES = {"gen": "General", "thm": "Theme"}


def event_links():
    html = requests.get(f"{BASE}/www/archive/problems", headers=UA, timeout=30).text
    soup = BeautifulSoup(html, "lxml")
    links = set()
    for a in soup.find_all("a", href=True):
        m = re.fullmatch(r"/www/archive/(\d+)", a["href"])
        if m:
            links.add(m.group(1))
    return sorted(links, key=int)


def round_pdfs(event_id):
    html = requests.get(f"{BASE}/www/archive/{event_id}", headers=UA, timeout=30).text
    out = {}
    for m in re.finditer(r"//hmmt-archive\.s3\.amazonaws\.com/tournaments/(\d{4})/(\w+)/(\w+)/solutions\.pdf", html):
        year, session, rnd = m.groups()
        if rnd in ROUND_NAMES:
            out[(int(year), session, rnd)] = "https:" + m.group(0)
    return out


def parse_solutions_pdf(path):
    text = "\n".join(p.extract_text() for p in PdfReader(path).pages)
    # split at problem starts: "N. " at line start
    parts = re.split(r"\n(?=\d{1,2}\. )", text)
    problems = []
    for part in parts:
        m = re.match(r"\s*(\d{1,2})\. ", part)
        if not m:
            continue
        n = int(m.group(1))
        body = part[m.end():]
        am = re.search(r"Proposed by:.*?\nAnswer:(.*?)\nSolution:(.*)", body, re.S)
        if not am:
            # problem statement without solution (older format?)
            problems.append({"n": n, "question": body.strip(), "answer": None, "solution": None})
            continue
        q = body[: am.start()].strip()
        # cut trailing "Proposed by" leftovers
        ans = am.group(1).strip()
        sol = am.group(2).strip()
        problems.append({"n": n, "question": q, "answer": ans, "solution": sol})
    return problems


def clean_text(t):
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace("◦", "°").replace("−", "-")
    return t


def main():
    events = event_links()
    print(f"{len(events)} events")
    all_pdfs = {}
    for i, ev in enumerate(events):
        all_pdfs.update(round_pdfs(ev))
        time.sleep(0.4)
    print(f"{len(all_pdfs)} gen/thm solution PDFs found")

    variants = []
    for (year, session, rnd), url in sorted(all_pdfs.items()):
        fname = PDF_DIR / f"{year}_{session}_{rnd}_solutions.pdf"
        if not fname.exists():
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code != 200 or not r.content.startswith(b"%PDF"):
                print("skip", url, r.status_code)
                continue
            fname.write_bytes(r.content)
            time.sleep(0.5)
        try:
            probs = parse_solutions_pdf(fname)
        except Exception as e:
            print("parse fail", fname, e)
            continue
        for p in probs:
            q = clean_text(p["question"])
            if len(q) < 25:
                continue
            sol = clean_text(p["solution"]) if p["solution"] else None
            ans = p["answer"]
            full_sol = (f"Answer: {ans}. " if ans else "") + (sol or "")
            variants.append({
                "position": p["n"],
                "source": f"{year} HMMT {'November' if session == 'nov' else 'February'} {ROUND_NAMES[rnd]} Problem {p['n']}",
                "question": q,
                "choices": None,
                "answer": None,
                "type": "proof",
                "solution": full_sol or None,
                "has_diagram": False,
            })
        print(year, session, rnd, len(probs))

    json.dump({"competition": "HMMT", "set": "A", "variants": variants},
              open(ROOT / "bank" / "hmmt_A.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("TOTAL:", len(variants), dict(sorted(Counter(v["position"] for v in variants).items())))


if __name__ == "__main__":
    main()

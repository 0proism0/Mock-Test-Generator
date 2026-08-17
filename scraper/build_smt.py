"""Build SMT (Stanford Math Tournament) bank from official past-test PDFs.

Pattern: https://stanfordmathtournament.com/pdfs/smt{year}/{round}-{problems,solutions}.pdf
Rounds: algebra, calculus, discrete, general, geometry, team (individual + team).
Parses solutions PDFs (problem + answer + solution) into bank/smt_A.json.
"""
import json
import re
import time
from pathlib import Path

import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "smt"
PDF_DIR.mkdir(parents=True, exist_ok=True)
BASE = "https://stanfordmathtournament.com/pdfs/smt{year}/{rnd}-{part}.pdf"
YEARS = [2011, 2012, 2013, 2014, 2018, 2019, 2020, 2021, 2022, 2023]
ROUNDS = ["algebra", "calculus", "discrete", "general", "geometry", "team"]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/125.0.0.0 Safari/537.36"}


def _pages_text(path):
    out = []
    for p in PdfReader(path).pages:
        try:
            out.append(p.extract_text())
        except Exception:
            continue
    return "\n".join(out)


def download(url, fname):
    if fname.exists() and fname.stat().st_size > 1000:
        return True
    try:
        r = requests.get(url, headers=UA, timeout=30)
        if r.status_code == 200 and r.content.startswith(b"%PDF"):
            fname.write_bytes(r.content)
            time.sleep(0.4)
            return True
    except Exception:
        pass
    return False


def parse_problems(text):
    """Split at 'N. ' problem starts."""
    parts = re.split(r"\n(?=\d{1,2}\.\s)", text)
    probs = {}
    for part in parts:
        m = re.match(r"\s*(\d{1,2})\.\s", part)
        if not m:
            continue
        probs[int(m.group(1))] = re.sub(r"\s+", " ", part[m.end():]).strip()
    return probs


def parse_solutions(text):
    """Solutions PDF: sections per problem with 'Answer:' markers."""
    sols = {}
    # split at problem starts
    parts = re.split(r"\n(?=\d{1,2}\.\s)", text)
    for part in parts:
        m = re.match(r"\s*(\d{1,2})\.\s", part)
        if not m:
            continue
        n = int(m.group(1))
        body = part[m.end():]
        am = re.search(r"Answer:\s*(.+?)(?:\n|Solution)", body, re.S)
        ans = None
        if am:
            ans = re.sub(r"\s+", " ", am.group(1)).strip()[:120]
        sols[n] = (ans, re.sub(r"\s+", " ", body).strip())
    return sols


def clean(t):
    return re.sub(r"\s+", " ", t).strip()


def main():
    variants = []
    for year in YEARS:
        for rnd in ROUNDS:
            pf = PDF_DIR / f"smt{year}_{rnd}_problems.pdf"
            sf = PDF_DIR / f"smt{year}_{rnd}_solutions.pdf"
            if not download(BASE.format(year=year, rnd=rnd, part="problems"), pf):
                continue
            has_sol = download(BASE.format(year=year, rnd=rnd, part="solutions"), sf)
            try:
                probs = parse_problems(_pages_text(pf))
                sols = parse_solutions(_pages_text(sf)) if has_sol else {}
            except Exception as e:
                print("parse fail", year, rnd, e)
                continue
            for n, q in probs.items():
                if len(q) < 25:
                    continue
                ans, sol = sols.get(n, (None, None))
                ans_num = None
                if ans:
                    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*[a-zA-Z$°]*", ans)
                    if m and re.fullmatch(r"-?\d+", m.group(1)) and 0 <= int(m.group(1)) <= 999:
                        ans_num = str(int(m.group(1)))
                full_sol = (f"Answer: {ans}. " if ans else "") + (sol or "")
                variants.append({
                    "position": n,
                    "source": f"{year} SMT {rnd.capitalize()} Problem {n}",
                    "question": clean(q),
                    "choices": None,
                    "answer": ans_num,
                    "type": "integer_answer" if ans_num else "proof",
                    "solution": full_sol or None,
                    "has_diagram": "diagram" in q.lower() or "figure" in q.lower() or "shown" in q.lower(),
                })
            print(year, rnd, len(probs))
    json.dump({"competition": "SMT", "set": "A", "variants": variants},
              open(ROOT / "bank" / "smt_A.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("TOTAL:", len(variants), Counter(v["type"] for v in variants))
    print("with answers:", sum(1 for v in variants if v["answer"] or "Answer:" in (v["solution"] or "")))


if __name__ == "__main__":
    main()

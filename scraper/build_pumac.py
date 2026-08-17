"""Build PUMaC bank from pumac.princeton.edu/archives /s/ PDF links.

Pairs problem PDFs with their solution PDFs by (year, round, division),
parses them into bank/pumac_A.json.
"""
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "pumac"
PDF_DIR.mkdir(parents=True, exist_ok=True)
BASE = "https://pumac.princeton.edu"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/125.0.0.0 Safari/537.36"}

SOL_PAT = re.compile(r"sol", re.I)


def get_links():
    html = requests.get(f"{BASE}/archives", headers=UA, timeout=30).text
    soup = BeautifulSoup(html, "lxml")
    return [a["href"] for a in soup.find_all("a", href=True)
            if a["href"].startswith("/s/") and a["href"].lower().endswith(".pdf")]


def year_of(name):
    m = re.search(r"(19|20)(\d{2})", name)
    return int(m.group(1) + m.group(2)) if m else None


def round_of(name):
    n = name.lower()
    for r in ["algebra", "geometry", "combinatorics", "combo", "nt", "number", "indiv", "team", "power"]:
        if r in n:
            return {"combo": "Combinatorics", "nt": "Number Theory", "number": "Number Theory",
                    "indiv": "Individual Finals", "team": "Team", "power": "Power"}.get(r, r.capitalize())
    return None


def division_of(name):
    n = name.lower().replace("sols", "").replace("solutions", "").replace("sol", "")
    m = re.search(r"(?:^|[_\-\s])([ab])(?:[_\-\s.]|$|div)", n)
    return m.group(1).upper() if m else ""


def _text(path):
    out = []
    for p in PdfReader(path).pages:
        try:
            out.append(p.extract_text())
        except Exception:
            continue
    return "\n".join(out)


def parse_problems(text):
    parts = re.split(r"\n(?=\d{1,2}[\.\)])", text)
    probs = {}
    for part in parts:
        m = re.match(r"\s*(\d{1,2})[\.\)]\s*", part)
        if not m:
            continue
        probs[int(m.group(1))] = re.sub(r"\s+", " ", part[m.end():]).strip()
    return probs


def main():
    links = get_links()
    print(len(links), "pdf links")
    # group: key = (year, round, division) -> {"prob": url, "sol": url}
    groups = {}
    for href in links:
        name = href.split("/")[-1]
        y, r, d = year_of(name), round_of(name), division_of(name)
        if not y or not r:
            continue
        key = (y, r, d)
        g = groups.setdefault(key, {})
        if SOL_PAT.search(name):
            g["sol"] = href
        else:
            g.setdefault("prob", href)

    variants = []
    for (y, r, d), g in sorted(groups.items()):
        pf = PDF_DIR / f"{y}_{r}_{d}_prob.pdf"
        sf = PDF_DIR / f"{y}_{r}_{d}_sol.pdf"
        if "prob" not in g:
            continue
        try:
            if not pf.exists():
                resp = requests.get(BASE + g["prob"], headers=UA, timeout=40)
                if resp.status_code == 200 and resp.content.startswith(b"%PDF"):
                    pf.write_bytes(resp.content)
                    time.sleep(0.3)
                else:
                    continue
            probs = parse_problems(_text(pf))
            sols = {}
            if "sol" in g:
                if not sf.exists():
                    resp = requests.get(BASE + g["sol"], headers=UA, timeout=40)
                    if resp.status_code == 200 and resp.content.startswith(b"%PDF"):
                        sf.write_bytes(resp.content)
                        time.sleep(0.3)
                if sf.exists():
                    sols = parse_problems(_text(sf))
        except Exception as e:
            print("fail", y, r, d, e)
            continue
        for n, q in probs.items():
            if len(q) < 25:
                continue
            sol = sols.get(n)
            ans = None
            if sol:
                m = re.search(r"[Aa]nswer[:\s]*\$?([^\n\.]{1,40})", sol)
                if m:
                    ans = m.group(1).strip("$ ")
            ans_num = None
            if ans:
                m2 = re.match(r"^(-?\d+)$", ans)
                if m2 and 0 <= int(ans) <= 999:
                    ans_num = ans
            div = f" ({d})" if d else ""
            variants.append({
                "position": n,
                "source": f"{y} PUMaC {r}{div} Problem {n}",
                "question": q, "choices": None, "answer": ans_num,
                "type": "integer_answer" if ans_num else "proof",
                "solution": ((f"Answer: {ans}. " if ans else "") + (sol or "")) or None,
                "has_diagram": "diagram" in q.lower() or "figure" in q.lower() or "shown" in q.lower(),
            })
        print(y, r, d, len(probs))
    json.dump({"competition": "PUMaC", "set": "A", "variants": variants},
              open(ROOT / "bank" / "pumac_A.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("TOTAL:", len(variants), Counter(v["type"] for v in variants))


if __name__ == "__main__":
    main()

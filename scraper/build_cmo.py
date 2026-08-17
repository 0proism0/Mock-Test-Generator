"""Build CMO bank from cms.math.ca CMO page (exam1969-2020, sol1994-2020, plus 2021-2026)."""
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "cmo"
PDF_DIR.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}


def _text(path):
    out = []
    for p in PdfReader(path).pages:
        try:
            out.append(p.extract_text())
        except Exception:
            continue
    return "\n".join(out)


def parse_problems(text):
    parts = re.split(r"\n(?=P?\d{1,2}[\.\)])", text)
    probs = {}
    for part in parts:
        m = re.match(r"\s*P?(\d{1,2})[\.\)]\s*", part)
        if not m:
            continue
        probs[int(m.group(1))] = re.sub(r"\s+", " ", part[m.end():]).strip()
    return probs


def get_links():
    html = requests.get("https://cms.math.ca/competitions/cmo/", headers=UA, timeout=30).text
    soup = BeautifulSoup(html, "lxml")
    prob, sol = {}, {}
    for a in soup.find_all("a", href=True):
        h = a["href"]
        name = h.split("/")[-1].lower()
        if not name.endswith(".pdf") or "cjmo" in name:
            continue
        m = re.match(r"exam(\d{4})\.pdf", name)
        if m:
            prob[int(m.group(1))] = h
            continue
        m = re.match(r"sol(\d{4})\.pdf", name)
        if m:
            sol[int(m.group(1))] = h
            continue
        m = re.match(r"cmo(\d{4})-problems\.pdf", name)
        if m:
            prob[int(m.group(1))] = h
            continue
        m = re.match(r"(\d{4})cmo-exam-en\.pdf", name)
        if m:
            prob[int(m.group(1))] = h
            continue
        if re.match(r"cmo\d{4}-solutions-en\.pdf|cmo\d{4}-solutions\.pdf|\d{4}cmo_solutions_en.*\.pdf", name):
            y = re.search(r"(19|20)\d{2}", name)
            if y:
                sol[int(y.group(0))] = h
    return prob, sol


def download(url, fname):
    if fname.exists() and fname.stat().st_size > 500:
        return True
    try:
        r = requests.get(url, headers=UA, timeout=60)
        if r.status_code == 200 and r.content.startswith(b"%PDF"):
            fname.write_bytes(r.content)
            time.sleep(0.3)
            return True
    except Exception:
        pass
    return False


def main():
    prob, sol = get_links()
    print(len(prob), "problem sets,", len(sol), "solution sets")
    variants = []
    for y in sorted(prob):
        pf = PDF_DIR / f"cmo{y}_prob.pdf"
        sf = PDF_DIR / f"cmo{y}_sol.pdf"
        if not download(prob[y], pf):
            print(y, "prob download fail")
            continue
        if y in sol:
            download(sol[y], sf)
        try:
            probs = parse_problems(_text(pf))
            sols = parse_problems(_text(sf)) if sf.exists() else {}
        except Exception as e:
            print(y, "parse fail", e)
            continue
        for n, q in probs.items():
            if len(q) < 25:
                continue
            variants.append({
                "position": n,
                "source": f"{y} CMO Problem {n}",
                "question": q, "choices": None, "answer": None, "type": "proof",
                "solution": sols.get(n),
                "has_diagram": "diagram" in q.lower() or "figure" in q.lower() or "shown" in q.lower(),
            })
        print(y, len(probs))
    json.dump({"competition": "CMO", "set": "A", "variants": variants},
              open(ROOT / "bank" / "cmo_A.json", "w"), ensure_ascii=False, indent=1)
    print("TOTAL:", len(variants), "| with sol:", sum(1 for v in variants if v["solution"]))


if __name__ == "__main__":
    main()

"""Build BMT (Berkeley Math Tournament) bank from berkeley.mt event archives.

Event pages: /resources/archives/{event}/ with per-round problem PDFs
(no official solutions published) -> proof-type entries without solutions.
"""
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "bmt"
PDF_DIR.mkdir(parents=True, exist_ok=True)
BASE = "https://berkeley.mt"
UA = {"User-Agent": "Mozilla/5.0"}

ROUND_NAMES = {"general": "General", "algebra": "Algebra", "calculus": "Calculus",
               "discrete": "Discrete", "geometry": "Geometry", "guts": "Guts", "power": "Power"}


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
    html = requests.get(f"{BASE}/resources/archives/", headers=UA, timeout=30).text
    soup = BeautifulSoup(html, "lxml")
    events = sorted({a["href"] for a in soup.find_all("a", href=True)
                     if re.search(r"/resources/archives/(bmt|bmmt)-\d{4}", a["href"])})
    print(len(events), "events")
    variants = []
    for ev in events:
        slug = ev.rstrip("/").split("/")[-1]
        try:
            ev_url = ev if ev.startswith("http") else f"{BASE}{ev}"
            page = requests.get(ev_url, headers=UA, timeout=30).text
        except Exception:
            continue
        soup2 = BeautifulSoup(page, "lxml")
        pdfs = {a["href"] for a in soup2.find_all("a", href=True)
                if a["href"].endswith("-problems.pdf") and "tiebreaker" not in a["href"]}
        for href in pdfs:
            rnd = href.split("/")[-1].replace("-problems.pdf", "")
            rname = ROUND_NAMES.get(rnd)
            if not rname:
                continue
            url = href if href.startswith("http") else (ev + href if ev.endswith("/") else ev + "/" + href)
            pf = PDF_DIR / f"{slug}_{rnd}.pdf"
            try:
                if not pf.exists():
                    r = requests.get(url, headers=UA, timeout=40)
                    if r.status_code == 200 and r.content.startswith(b"%PDF"):
                        pf.write_bytes(r.content)
                        time.sleep(0.3)
                    else:
                        continue
                probs = parse_problems(_text(pf))
            except Exception as e:
                print("fail", slug, rnd, e)
                continue
            comp = "BMT" if slug.startswith("bmt") else "BmMT"
            year = slug.split("-")[-1]
            for n, q in probs.items():
                if len(q) < 25:
                    continue
                variants.append({
                    "position": n,
                    "source": f"{year} {comp} {rname} Problem {n}",
                    "question": q, "choices": None, "answer": None, "type": "proof",
                    "solution": None,
                    "has_diagram": "diagram" in q.lower() or "figure" in q.lower() or "shown" in q.lower(),
                })
            print(slug, rnd, len(probs))
    json.dump({"competition": "BMT", "set": "A", "variants": variants},
              open(ROOT / "bank" / "bmt_A.json", "w"), ensure_ascii=False, indent=1)
    print("TOTAL:", len(variants))


if __name__ == "__main__":
    main()

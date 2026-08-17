"""Build COMC bank from CMS exam archive official solutions PDFs (2011-2021)."""
import json
import re
import time
from pathlib import Path

import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "comc"
PDF_DIR.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}
YEARS = list(range(2011, 2022))


def _text(path):
    out = []
    for p in PdfReader(path).pages:
        try:
            out.append(p.extract_text())
        except Exception:
            continue
    return "\n".join(out)


def parse_problems(text):
    """COMC official solutions PDF: problems with 'Part A/B/C' sections, numbered solutions."""
    # solutions doc contains each problem restated with solution
    parts = re.split(r"\n(?=(?:A|B|C)?\d{1,2}[\.\)]\s)", text)
    probs = {}
    for part in parts:
        m = re.match(r"\s*(?:([ABC])[\s-]?)?(\d{1,2})[\.\)]\s", part)
        if not m:
            continue
        sec = m.group(1) or ""
        n = int(m.group(2))
        probs[(sec, n)] = re.sub(r"\s+", " ", part[m.end():]).strip()
    return probs


def download(url, fname):
    if fname.exists() and fname.stat().st_size > 1000:
        return True
    r = requests.get(url, headers=UA, timeout=40)
    if r.status_code == 200 and r.content.startswith(b"%PDF"):
        fname.write_bytes(r.content)
        time.sleep(0.4)
        return True
    return False


def main():
    variants = []
    for y in YEARS:
        f = PDF_DIR / f"comc{y}_sol.pdf"
        if not download(f"https://www2.cms.math.ca/Competitions/COMC/examarchive/comc{y}-official-solutions-en.pdf", f):
            print(y, "missing")
            continue
        try:
            probs = parse_problems(_text(f))
        except Exception as e:
            print(y, "parse fail", e)
            continue
        n = 0
        for (sec, pnum), q in probs.items():
            if len(q) < 30:
                continue
            variants.append({
                "position": pnum,
                "source": f"{y} COMC Problem {sec}{pnum}",
                "question": q, "choices": None, "answer": None, "type": "proof",
                "solution": q,  # the doc contains problem+solution together
                "has_diagram": "diagram" in q.lower() or "figure" in q.lower() or "shown" in q.lower(),
            })
            n += 1
        print(y, n)
    json.dump({"competition": "COMC", "set": "A", "variants": variants},
              open(ROOT / "bank" / "comc_A.json", "w"), ensure_ascii=False, indent=1)
    print("TOTAL:", len(variants))


if __name__ == "__main__":
    main()

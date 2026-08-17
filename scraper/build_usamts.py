"""Build USAMTS bank from files.usamts.org.

Pattern: Problems_{ed}_{round}.pdf / Solutions_{ed}_{round}.pdf
editions ~ 25..36, rounds 1..3 (some have 4).
Proof-type real problems with official solutions -> bank/usamts_A.json
"""
import json
import re
import time
from pathlib import Path

import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "usamts"
PDF_DIR.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/125.0.0.0 Safari/537.36"}


def _text(path):
    out = []
    for p in PdfReader(path).pages:
        try:
            out.append(p.extract_text())
        except Exception:
            continue
    return "\n".join(out)


def parse_problems(text):
    parts = re.split(r"\n(?=\d{1,2}[\./]\s|\d{1,2}\n)", text)
    probs = {}
    for part in parts:
        m = re.match(r"\s*(\d{1,2})[\./]?\s*\n?", part)
        if not m:
            continue
        probs[int(m.group(1))] = re.sub(r"\s+", " ", part[m.end():]).strip()
    return probs


def download(url, fname):
    if fname.exists() and fname.stat().st_size > 1000:
        return True
    try:
        r = requests.get(url, headers=UA, timeout=30)
        if r.status_code == 200 and r.content.startswith(b"%PDF"):
            fname.write_bytes(r.content)
            time.sleep(0.3)
            return True
    except Exception:
        pass
    return False


def main():
    variants = []
    for ed in range(25, 37):
        year = 1988 + ed  # USAMTS edition 1 = 1989
        for rnd in range(1, 5):
            pf = PDF_DIR / f"P_{ed}_{rnd}.pdf"
            sf = PDF_DIR / f"S_{ed}_{rnd}.pdf"
            if not download(f"https://files.usamts.org/Problems_{ed}_{rnd}.pdf", pf):
                continue
            download(f"https://files.usamts.org/Solutions_{ed}_{rnd}.pdf", sf)
            try:
                probs = parse_problems(_text(pf))
                sols = parse_problems(_text(sf)) if sf.exists() else {}
            except Exception as e:
                print("fail", ed, rnd, e)
                continue
            for n, q in probs.items():
                if len(q) < 30:
                    continue
                variants.append({
                    "position": n,
                    "source": f"USAMTS Year {ed} Round {rnd} Problem {n}",
                    "question": q, "choices": None, "answer": None, "type": "proof",
                    "solution": sols.get(n),
                    "has_diagram": "diagram" in q.lower() or "figure" in q.lower() or "shown" in q.lower(),
                })
            print("edition", ed, "round", rnd, len(probs))
    json.dump({"competition": "USAMTS", "set": "A", "variants": variants},
              open(ROOT / "bank" / "usamts_A.json", "w"), ensure_ascii=False, indent=1)
    print("TOTAL:", len(variants), "| with solutions:", sum(1 for v in variants if v["solution"]))


if __name__ == "__main__":
    main()

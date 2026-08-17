"""Build CMIMC bank from cmimc.math.cmu.edu past-problems (Google Drive PDFs)."""
import json
import re
import time
from pathlib import Path

import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "cmimc"
PDF_DIR.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}
YEARS = list(range(2016, 2026))
VALID_ROUNDS = {"algebra": "Algebra", "combinatorics": "Combinatorics", "geometry": "Geometry",
                "computer science": "Computer Science", "team": "Team"}


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


def page_links(year):
    html = requests.get(f"https://cmimc.math.cmu.edu/math/past-problems/{year}",
                        headers=UA, timeout=30).text
    chunks = re.split(r"(https://drive\.google\.com/file/d/[^\"]+)", html)
    out, label = [], None
    for c in chunks:
        if c.startswith("https://drive"):
            out.append((label, c))
        else:
            txt = re.sub(r"<[^>]+>|\\u003c[^>]*", " ", c)
            txt = re.sub(r"[^a-zA-Z ]", " ", txt)
            words = [w for w in txt.split()
                     if w in ("Algebra", "Combinatorics", "Geometry", "Computer", "Science",
                              "Team", "Solutions", "Integration", "Bee", "Individual", "Mini", "Events")]
            if words:
                label = " ".join(words[-3:])
    return out


def drive_download(url, fname):
    if fname.exists() and fname.stat().st_size > 1000:
        return True
    m = re.search(r"/d/([^/]+)", url)
    if not m:
        return False
    dl = f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    for attempt in range(3):
        try:
            r = requests.get(dl, headers=UA, timeout=30)
            if r.status_code == 200 and r.content.startswith(b"%PDF"):
                fname.write_bytes(r.content)
                time.sleep(0.4)
                return True
            return False
        except Exception:
            time.sleep(2)
    return False


def main():
    variants = []
    for year in YEARS:
        try:
            links = page_links(year)
        except Exception as e:
            print(year, "page fail", e)
            continue
        # pair: problem link followed by its Solutions link
        current = None
        for label, url in links:
            lab = (label or "").lower()
            is_sol = "solutions" in lab
            rnd = None
            for key in VALID_ROUNDS:
                if key in lab:
                    rnd = VALID_ROUNDS[key]
                    break
            if rnd and not is_sol:
                current = (rnd, url, None)
                variants_tmp = current
                pf = PDF_DIR / f"cmimc{year}_{rnd.replace(' ', '')}_prob.pdf"
                if drive_download(url, pf):
                    current = (rnd, pf, None)
                else:
                    current = None
            elif is_sol and current:
                sf = PDF_DIR / f"cmimc{year}_{current[0].replace(' ', '')}_sol.pdf"
                if drive_download(url, sf):
                    current = (current[0], current[1], sf)
                    # process the pair
                    rnd, pf, solf = current
                    try:
                        probs = parse_problems(_text(pf))
                        sols = parse_problems(_text(solf))
                    except Exception as e:
                        print(year, rnd, "parse fail", e)
                        current = None
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
                        ans_num = ans if (ans and re.fullmatch(r"-?\d+", ans) and 0 <= int(ans) <= 999) else None
                        variants.append({
                            "position": n,
                            "source": f"{year} CMIMC {rnd} Problem {n}",
                            "question": q, "choices": None, "answer": ans_num,
                            "type": "integer_answer" if ans_num else "proof",
                            "solution": ((f"Answer: {ans}. " if ans else "") + (sol or "")) or None,
                            "has_diagram": "diagram" in q.lower() or "figure" in q.lower() or "shown" in q.lower(),
                        })
                    print(year, rnd, len(probs))
                    current = None
    json.dump({"competition": "CMIMC", "set": "A", "variants": variants},
              open(ROOT / "bank" / "cmimc_A.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("TOTAL:", len(variants), Counter(v["type"] for v in variants))


if __name__ == "__main__":
    main()

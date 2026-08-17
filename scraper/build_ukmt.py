"""Build UKMT bank (JMC/IMC/SMC) from official past-paper PDFs.

Paper PDF: 'N. question A x B x C x D x E y' inline choices.
Solutions PDF: 'N. X Note that ...' where X = answer letter.
Output: bank/ukmt_A.json (multiple_choice, real problems).
"""
import json
import re
import time
from pathlib import Path

import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "ukmt"
PDF_DIR.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}

SETS = [
    # (level, year, paper_url, solutions_url)
    ("JMC", 2026, "https://ukmt.org.uk/wp-content/uploads/2026/05/JMC_Paper_2026.pdf", "https://ukmt.org.uk/wp-content/uploads/2026/05/JMC_Solutions_2026.pdf"),
    ("JMC", 2025, "https://ukmt.org.uk/wp-content/uploads/2025/05/JMC-2025-Paper.pdf", "https://ukmt.org.uk/wp-content/uploads/2025/05/JMC-2025-Solutions.pdf"),
    ("JMC", 2024, "https://ukmt.org.uk/wp-content/uploads/2024/04/JMC-2024-Question-Paper-4.pdf", "https://ukmt.org.uk/wp-content/uploads/2024/04/JMC-2024-Solutions-1.pdf"),
    ("JMC", 2023, "https://ukmt.org.uk/wp-content/uploads/2023/08/JMC-2023_Paper.pdf", "https://ukmt.org.uk/wp-content/uploads/2023/08/JMC-2023-Solutions.pdf"),
    ("IMC", 2026, "https://ukmt.org.uk/wp-content/uploads/2026/01/IMC_Paper_2026.pdf", "https://ukmt.org.uk/wp-content/uploads/2026/01/IMC_Solutions_2026.pdf"),
    ("IMC", 2025, "https://ukmt.org.uk/wp-content/uploads/2025/01/IMC-2025-Paper.pdf", "https://ukmt.org.uk/wp-content/uploads/2025/01/IMC-2025-Solutions.pdf"),
    ("IMC", 2024, "https://ukmt.org.uk/wp-content/uploads/2024/02/IMC_2024-Paper.pdf", "https://ukmt.org.uk/wp-content/uploads/2024/02/IMC-2024-Solutions.pdf"),
    ("IMC", 2023, "https://ukmt.org.uk/wp-content/uploads/2023/08/IMC_2023_Paper-1.pdf", "https://ukmt.org.uk/wp-content/uploads/2023/08/IMC-2023-Solutions-.pdf"),
    ("SMC", 2025, "https://ukmt.org.uk/wp-content/uploads/2025/10/SMC_2025_paper.pdf", "https://ukmt.org.uk/wp-content/uploads/2025/10/SMC_2025_Solutions.pdf"),
    ("SMC", 2024, "https://ukmt.org.uk/wp-content/uploads/2024/10/SMC-2024-Paper.pdf", "https://ukmt.org.uk/wp-content/uploads/2024/10/SMC_2024_Solutions.pdf"),
    ("SMC", 2023, "https://ukmt.org.uk/wp-content/uploads/2023/10/SMC-2023-Paper.pdf", "https://ukmt.org.uk/wp-content/uploads/2023/10/SMC-2023-Solutions.pdf"),
]

LEVEL_NAMES = {"JMC": "Junior Mathematical Challenge", "IMC": "Intermediate Mathematical Challenge",
               "SMC": "Senior Mathematical Challenge"}


def download(url, fname):
    if fname.exists() and fname.stat().st_size > 1000:
        return True
    for attempt in range(6):
        try:
            r = requests.get(url, headers=UA, timeout=40)
            if r.status_code == 200 and r.content.startswith(b"%PDF"):
                fname.write_bytes(r.content)
                time.sleep(0.4)
                return True
            print(f"  HTTP {r.status_code}, retry {attempt}", url.split("/")[-1])
        except Exception as e:
            print(f"  {e}, retry {attempt}")
        time.sleep(2 + attempt * 2)
    print("download failed", url)
    return False


def _text(path):
    out = []
    for p in PdfReader(path).pages:
        try:
            out.append(p.extract_text())
        except Exception:
            continue
    return "\n".join(out)


def parse_paper(text):
    """Return {n: (question, {A..E: choice})}"""
    text = re.sub(r"/u[0-9A-Fa-f]{6}", "?", text)  # broken math-glyph refs
    parts = re.split(r"(?m)^(\d{1,2})\.\s", text)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        n = int(parts[i])
        body = parts[i + 1]
        # find choice block: first standalone 'A ' marker
        cm = re.search(r"\sA\s+", body)
        if not cm:
            continue
        q = body[: cm.start()]
        rest = body[cm.start():]
        # split choices on standalone letter markers
        cm2 = re.split(r"\s([A-E])\s+", rest)
        # cm2: ['', 'A', 'textA', 'B', 'textB', ...]
        choices = {}
        for j in range(1, len(cm2) - 1, 2):
            choices[cm2[j]] = cm2[j + 1].strip()
        q = re.sub(r"\s+", " ", q).strip()
        choices = {k: re.sub(r"\s+", " ", v).strip() for k, v in choices.items()}
        if q and set(choices) >= set("ABCDE") and all(choices.values()):
            out[n] = (q, {k: choices[k] for k in "ABCDE"})
    return out


def parse_answers(text):
    out = {}
    for m in re.finditer(r"(?m)^(\d{1,2})\.\s*([A-E])\s", text):
        out[int(m.group(1))] = m.group(2)
    return out


def main():
    variants = []
    for level, year, paper_url, sol_url in SETS:
        pf = PDF_DIR / f"{level}{year}_paper.pdf"
        sf = PDF_DIR / f"{level}{year}_sol.pdf"
        if not pf.exists():
            if not download(paper_url, pf):
                continue
        if not sf.exists():
            download(sol_url, sf)
        probs = parse_paper(_text(pf))
        answers = parse_answers(_text(sf)) if sf.exists() else {}
        n_ok = 0
        for n, (q, choices) in probs.items():
            ans = answers.get(n)
            if not ans:
                continue
            if "diagram" in q.lower() or "figure" in q.lower() or "shown" in q.lower():
                continue  # skip diagram-dependent
            variants.append({
                "position": n,
                "source": f"{year} UKMT {level} Problem {n}",
                "question": q,
                "choices": choices,
                "answer": ans,
                "type": "multiple_choice",
                "solution": None,
                "has_diagram": False,
            })
            n_ok += 1
        print(level, year, len(probs), "parsed,", n_ok, "with answers")
    json.dump({"competition": "UKMT", "set": "A", "variants": variants},
              open(ROOT / "bank" / "ukmt_A.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("TOTAL:", len(variants), Counter(v["source"].split(" Problem")[0][5:12] for v in variants))


if __name__ == "__main__":
    main()

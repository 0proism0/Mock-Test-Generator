"""Build Putnam bank from kskedlaya.org/putnam-archive TeX sources.

Downloads YYYY.tex (problems) and YYYYs.tex (solutions), parses \\item[A1]/\\item[B1]
structure into bank/putnam_A.json (proof-type, real problems).
"""
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TEX_DIR = ROOT / "raw" / "putnam_tex"
TEX_DIR.mkdir(parents=True, exist_ok=True)
BASE = "https://kskedlaya.org/putnam-archive/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,*/*",
}

POS_ORDER = {f"{s}{n}": (0 if s == "A" else 6) + n for s in "AB" for n in range(1, 7)}


def get_years():
    html = requests.get(BASE, headers=HEADERS, timeout=30).text
    years = sorted({int(m.group(1)) for m in re.finditer(r'(?<!\d)(19|20)(\d{2})\.tex', html) for m in [re.match(r"(19\d{2}|20\d{2})\.tex", f"{m.group(1) or ''}{m.group(2)}.tex")] if False})
    # simpler: find all YYYY.tex
    return sorted({int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\.tex\b", html)})


def download(year, suffix=""):
    fname = TEX_DIR / f"{year}{suffix}.tex"
    if fname.exists() and fname.stat().st_size > 100:
        return fname
    r = requests.get(f"{BASE}{year}{suffix}.tex", headers=HEADERS, timeout=30)
    if r.status_code == 200 and r.text.strip().startswith("\\documentclass"):
        fname.write_text(r.text)
        time.sleep(0.5)
        return fname
    return None


def parse_items(tex):
    """Split TeX into {label: text} at \\item[XX] boundaries."""
    items = {}
    parts = re.split(r"\\item\[([^\]]+)\]", tex)
    # parts[0] = preamble; then alternating label, body
    for i in range(1, len(parts) - 1, 2):
        label = parts[i].strip()
        body = parts[i + 1]
        # cut at \end{itemize} or \end{enumerate}
        body = re.split(r"\\end\{(itemize|enumerate)\}", body)[0]
        items[label] = body.strip()
    return items


def clean_tex(t):
    t = re.sub(r"%.*", "", t)  # comments
    t = re.sub(r"\\begin\{(enumerate|itemize)\}", "", t)
    t = re.sub(r"\\end\{(enumerate|itemize)\}", "", t)
    t = re.sub(r"\\item\[([^\]]+)\]", r"[\1] ", t)
    t = re.sub(r"\\item\b", "- ", t)
    t = t.replace("\\ ", " ").replace("~", " ")
    t = re.sub(r"\\label\{[^}]*\}", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def main():
    years = get_years()
    print(f"{len(years)} years: {years[0]}..{years[-1]}")
    variants = []
    for y in years:
        f = download(y)
        fs = download(y, "s")
        if not f:
            print(y, "no problems tex")
            continue
        probs = parse_items(f.read_text())
        sols = parse_items(fs.read_text()) if fs else {}
        for label, body in probs.items():
            label_clean = label.replace("–", "-").strip()
            m = re.fullmatch(r"([AB])\s*-?\s*(\d+)", label_clean)
            if not m:
                continue
            key = f"{m.group(1)}{m.group(2)}"
            pos = POS_ORDER.get(key)
            if not pos:
                continue
            q = clean_tex(body)
            if len(q) < 20:
                continue
            sol = None
            for sk in (label, key, label_clean):
                if sk in sols:
                    sol = clean_tex(sols[sk])
                    break
            variants.append({
                "position": pos,
                "source": f"{y} Putnam Problem {key}",
                "question": q, "choices": None, "answer": None, "type": "proof",
                "solution": sol,
                "has_diagram": False,
            })
        print(y, len([v for v in variants if v["source"].startswith(str(y))]))
    variants.sort(key=lambda v: (v["position"], v["source"]))
    json.dump({"competition": "Putnam", "set": "A", "variants": variants},
              open(ROOT / "bank" / "putnam_A.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("TOTAL:", len(variants), dict(sorted(Counter(v["position"] for v in variants).items())))
    print("with solutions:", sum(1 for v in variants if v["solution"]))


if __name__ == "__main__":
    main()

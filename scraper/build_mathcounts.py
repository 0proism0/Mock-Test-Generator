"""Build MATHCOUNTS bank from official 2026 Chapter/State PDFs (browser-downloaded).

Parses sprint/target/team problems (layout mode), answer keys, and solutions
into bank/mathcounts_A.json (real problems; integer_answer or proof type).
"""
import json
import re
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "raw" / "pdfs" / "mathcounts"

ROUNDS = [("sprint", "Sprint", 30), ("target", "Target", 8), ("team", "Team", 10)]


def _pages_text(path, layout=False):
    out = []
    for p in PdfReader(path).pages:
        try:
            out.append(p.extract_text(extraction_mode="layout") if layout else p.extract_text())
        except Exception:
            continue
    return "\n".join(out)


def extract_problems(path, n_expected):
    text = _pages_text(path, layout=True)
    # cut copyright footers
    text = re.sub(r"Copyright MATHCOUNTS[^\n]*", "", text)
    # split at 'N. ____' markers at line start
    parts = re.split(r"(?m)^\s*(\d{1,2})\.\s+_{3,}\S*\s*", text)
    # parts: [pre, num1, body1, num2, body2, ...]
    probs = {}
    for i in range(1, len(parts) - 1, 2):
        n = int(parts[i])
        body = parts[i + 1]
        # cut trailing blanks/footer artifacts
        body = re.sub(r"\n{3,}.*$", "", body, flags=re.S)
        body = re.sub(r"\s+", " ", body).strip()
        if len(body) > 15:
            probs[n] = body
    return probs


def extract_answers(path):
    text = _pages_text(path, layout=True)
    text = re.sub(r"Copyright MATHCOUNTS[^\n]*", "", text)
    # section headers
    answers = {}
    section = None
    for line in text.splitlines():
        if "Sprint Round" in line:
            section = "sprint"
            continue
        if "Target Round" in line:
            section = "target"
            continue
        if "Team Round" in line:
            section = "team"
            continue
        for m in re.finditer(r"(\d{1,2})\.\s*_{3,}\s*([^_\n]+)", line):
            n, ans = int(m.group(1)), m.group(2).strip()
            ans = re.sub(r"\s+", " ", ans).strip()
            if section and ans:
                answers[(section, n)] = ans
    return answers


def extract_solutions(path):
    text = _pages_text(path, layout=True)
    text = re.sub(r"Copyright MATHCOUNTS[^\n]*", "", text)
    parts = re.split(r"(?m)^\s*(Sprint|Target|Team)\s+(\d{1,2})\s*$", text)
    sols = {}
    for i in range(1, len(parts) - 2, 3):
        rnd, n, body = parts[i].lower(), int(parts[i + 1]), parts[i + 2]
        body = re.sub(r"\s+", " ", body).strip()
        sols[(rnd, n)] = body
    return sols


def clean(t):
    t = re.sub(r"\s+", " ", t).strip()
    return t


def main():
    variants = []
    for level, prefix in [("Chapter", "chapter"), ("State", "state")]:
        probs_by_round = {}
        for rnd, rname, n_exp in ROUNDS:
            probs_by_round[rnd] = extract_problems(PDF / f"{prefix}_{rnd}.pdf", n_exp)
        answers = extract_answers(PDF / f"{prefix}_key.pdf")
        sols = extract_solutions(PDF / f"{prefix}_solutions.pdf")
        for rnd, rname, n_exp in ROUNDS:
            for n in range(1, n_exp + 1):
                q = probs_by_round[rnd].get(n)
                if not q:
                    continue
                ans = answers.get((rnd, n))
                sol = sols.get((rnd, n))
                full_sol = (f"Answer: {ans}. " if ans else "") + (sol or "")
                # numeric answer if the key starts with a number (units stripped)
                ans_num = None
                if ans:
                    mnum = re.match(r"^(-?[\d,]+(?:\.\d+)?)\s*[a-zA-Z$°¢%]*", ans)
                    if mnum:
                        v = mnum.group(1).replace(",", "")
                        if re.fullmatch(r"-?\d+", v) and 0 <= int(v) <= 999:
                            ans_num = str(int(v))
                variants.append({
                    "position": n,
                    "source": f"2026 MATHCOUNTS {level} {rname} Problem {n}",
                    "question": clean(q),
                    "choices": None,
                    "answer": ans_num,
                    "type": "integer_answer" if ans_num else "proof",
                    "solution": full_sol or None,
                    "has_diagram": "diagram" in q.lower() or "figure" in q.lower() or "shown" in q.lower(),
                })
    json.dump({"competition": "MATHCOUNTS", "set": "A", "variants": variants},
              open(ROOT / "bank" / "mathcounts_A.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("TOTAL:", len(variants))
    print("by type:", Counter(v["type"] for v in variants))
    print("by source round:", Counter(v["source"].split(" Problem")[0].split("MATHCOUNTS ")[1] for v in variants))
    print("with answers:", sum(1 for v in variants if v["answer"] or (v["solution"] and "Answer:" in v["solution"])))


if __name__ == "__main__":
    main()

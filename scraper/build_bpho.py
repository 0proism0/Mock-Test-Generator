"""Build bank/bpho_r1_A.json from BPhO Round 1 PDFs (raw/pdfs/bpho/).

Section 1 of each year's Q1 paper is "Question 1" with ~13-16 independent
short parts (a, b, c, ...). The matching _S.pdf holds worked solutions and
final answers. We extract each part as one bank variant:

  position  = part letter index (a=1, b=2, ...)
  points    = sum of [n] mark tags in the part
  question  = part text (figure-dependent parts dropped)
  solution  = worked solution from the S pdf
  answer    = final numeric value + unit (parts without a confident numeric
              final answer are dropped)
  type      = "numeric"  (frontend grades with relative tolerance)

Usage: .venv/bin/python scraper/build_bpho.py
"""
import json
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).parent))
from bpho_text import page_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "raw" / "pdfs" / "bpho"
OUT = ROOT / "bank" / "bpho_r1_A.json"

# stop Section 1 parsing at these markers
STOP_PAT = re.compile(r"Section 2|End of Section 1|^\s*Question\s*2", re.M)
# a part header line: optional paren + single letter + ')'
PART_PAT = re.compile(r"^\s*\(?([a-z])\)\s+", re.M)
# marks tag
MARKS_PAT = re.compile(r"\[\s*(\d+)\s*\]")
# figure dependence -> drop the part
FIGURE_PAT = re.compile(
    r"\bFig(?:ure)?\.?\s*\d|\bas shown\b|\bshown in\b|\bthe (?:figure|diagram)\b|"
    r"\bdiagram shows\b|\bin Figure\b", re.I)
# final numeric answer in a solution: "= 4500 N", "= 16 kmh^{-1}", "= 1.5 V"
NUM_ANS_PAT = re.compile(
    r'=\s*(-?\d[\d,]*(?:\.\d+)?(?:\s*\\times\s*10\^?\{?-?\d+\}?)?)'
    r'(?:\$?\s*(\\?[A-Za-zµΩ°][A-Za-zµΩℓ^{}\\_0-9-]{0,14}))?')
# plausible physics units (reject captured English words like "when")
UNIT_RE = re.compile(
    r'^[µμmμkncMGTpf]?'  # metric prefix
    r'(ms|min|s|m|g|kg|gs|t|N|J|W|V|A|C|F|H|T|Pa|K|Hz|eV|MeV|GeV|TeV|mol|Wb|'
    r'lm|cd|Nm|Js|JK|Jkg|Nkg|kmh|kWh|bar|atm|rpm|dB)'  # base unit
    r'(?:[\^_]\{?-?\d+\}?)?$'  # optional power
    r'|^(?:hours?|days?|weeks?|years?|months?|minutes?|mins?|seconds?|turns?|'
    r'orbits?|times|°C|°F|K|mA|kW|MW|GW)$')


def pdf_pages(path):
    try:
        with pdfplumber.open(path) as pdf:
            out = []
            for p in pdf.pages:
                t = page_text(p)
                lines = t.split("\n")
                # drop page-number footer (lone 1-2 digit last line)
                if lines and re.fullmatch(r"\s*\d{1,2}\s*", lines[-1]):
                    lines.pop()
                out.append("\n".join(lines))
            return out
    except Exception as e:
        print(f"  !! cannot read {path.name}: {e}")
        return None


def section1_text(pages):
    """Return Section 1 text of a Q1 paper (from 'Question 1' to end of S1)."""
    start = None
    for i, t in enumerate(pages):
        m = re.search(r"^\s*(?:Question\s*1|Q\s?1)\s*[.:]?\s*$", t, re.M)
        if m:
            start = (i, m.end())
            break
    if start is None:  # fallback: inline mention, e.g. 'Question 1.' mid-line
        for i, t in enumerate(pages):
            m = re.search(r"\b(?:Question\s*1|Q\s?1)\b[.:]?", t)
            if m:
                start = (i, m.end())
                break
    if start is None:
        return ""
    chunks = []
    for j in range(start[0], len(pages)):
        t = pages[j][start[1]:] if j == start[0] else pages[j]
        stop = STOP_PAT.search(t)
        if stop:
            chunks.append(t[:stop.start()])
            break
        chunks.append(t)
    return "\n".join(chunks)


def split_parts(text):
    """Split Section 1 text into ordered parts by letter progression a,b,c..."""
    parts = {}  # letter -> body text
    matches = list(PART_PAT.finditer(text))
    expected = "a"
    for i, m in enumerate(matches):
        letter = m.group(1)
        if letter != expected:
            continue  # sub-part like (i), or out-of-sequence noise
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # body runs until next *accepted* part header; approximate with next match
        body = text[m.end():end]
        parts[letter] = body
        expected = chr(ord(expected) + 1)
    return parts


def _merge_math_spans(s):
    """$a$$b$ -> $ab$ so KaTeX doesn't read $$ as display-math delimiter."""
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\$([^$]+)\$\$([^$]+)\$', r'$\1\2$', s)
    return s


def clean_question(body):
    body = MARKS_PAT.sub("", body)
    body = re.sub(r"\s+", " ", body).strip()
    # de-hyphenate words split across lines ("solid- ified" -> "solidified")
    body = re.sub(r"(\w)-\s+(?=[a-z])", r"\1", body)
    body = _merge_math_spans(_prettify_fractions(body))
    return body


def part_points(body):
    return sum(int(x) for x in MARKS_PAT.findall(body))


def clean_solution(text):
    lines = []
    for ln in text.split("\n"):
        ln = ln.strip().lstrip("•").strip()
        if ln:
            lines.append(ln)
    s = " ".join(lines)
    s = re.sub(r"^\(?[a-z]\)\s*\S[^.?!]*\.\s+", "", s)  # topic label line
    s = re.sub(r"\(\d+\s*marks?\)", "", s)
    s = _prettify_fractions(s)
    s = _merge_math_spans(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


FRAC_RUN = re.compile(r"(?:\^\{[^{}]*\}|_\{[^{}]*\})+")


def _prettify_fractions(s):
    """Rewrite stacked-fraction scramble from S PDFs: ^{1}_{3} -> $\\frac{1}{3}$.

    pdfplumber reads numerator (superscript-size) and denominator
    (subscript-size) of a stacked fraction as adjacent script groups; a run
    containing both kinds is (almost) always a fraction.
    """
    def repl(m):
        run = m.group(0)
        sup = re.findall(r"\^\{([^{}]*)\}", run)
        sub = re.findall(r"_\{([^{}]*)\}", run)
        if sup and sub:
            return "$\\frac{" + "".join(sup) + "}{" + "".join(sub) + "}$"
        return run
    return FRAC_RUN.sub(repl, s)


def extract_answer(sol):
    """Final numeric answer from a solution string. Returns 'VALUE UNIT' or None."""
    tail = sol[-200:]
    matches = list(NUM_ANS_PAT.finditer(tail))
    for m in reversed(matches):
        num = m.group(1).replace(",", "").replace(" ", "")
        unit = (m.group(2) or "").strip()
        if unit and not UNIT_RE.match(unit):
            unit = ""  # captured an English word, not a unit
        try:
            if float(num) == 0:
                continue
        except ValueError:
            continue
        # reject bare integers that are likely part of a fraction like "16/12"
        end = m.end()
        if tail[end:end + 1] == "/":
            continue
        ans = num + (" " + unit if unit else "")
        return ans
    return None


def main():
    years = sorted({int(re.search(r"(\d{4})", p.name).group(1))
                    for p in PDF_DIR.glob("BPhO_R1_*_Q1.pdf")})
    variants, dropped = [], {"fig": 0, "noans": 0, "nosol": 0}
    for year in years:
        q_pages = pdf_pages(PDF_DIR / f"BPhO_R1_{year}_Q1.pdf")
        if not q_pages:
            continue
        s_file = PDF_DIR / f"BPhO_R1_{year}_S.pdf"
        s_pages = pdf_pages(s_file) if s_file.exists() else None
        q_parts = split_parts(section1_text(q_pages))
        s_parts = split_parts("\n".join(s_pages)) if s_pages else {}
        n_year = 0
        for letter, body in q_parts.items():
            if FIGURE_PAT.search(body):
                dropped["fig"] += 1
                continue
            question = clean_question(body)
            if len(question) < 40:
                continue
            sol = clean_solution(s_parts.get(letter, ""))
            if not sol:
                dropped["nosol"] += 1
                continue
            ans = extract_answer(sol)
            if not ans:
                dropped["noans"] += 1
                continue
            variants.append({
                "source": f"BPhO R1 {year} 1({letter})",
                "position": ord(letter) - ord("a") + 1,
                "question": question,
                "answer": ans,
                "solution": sol,
                "points": part_points(body) or 3,
                "type": "numeric",
                "subject": "Physics",
            })
            n_year += 1
        print(f"{year}: {len(q_parts)} parts, {n_year} kept, "
              f"{len(q_parts) - n_year} dropped")

    by_pos = {}
    for v in variants:
        by_pos.setdefault(v["position"], set()).add(v["source"])
    print("\npositions:", {k: len(s) for k, s in sorted(by_pos.items())})
    print(f"total variants: {len(variants)}, dropped: {dropped}")

    OUT.write_text(json.dumps({
        "competition": "bpho_r1", "round": "Round 1",
        "variants": variants}, ensure_ascii=False, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

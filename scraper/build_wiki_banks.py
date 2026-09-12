"""Build new bank sets from raw/wikitext_problems.jsonl (AoPS wiki dumps).

Parses AMC 8/10/12 and AIME problems with solutions, cleans wikitext to
KaTeX-ready LaTeX, extracts choices and answers, and cross-verifies answers
against local answer keys:
  - raw/amc12_full.jsonl  (AMC 12 A/B 2000-2025, answer letters)
  - raw/aime_1983_2024.csv (AIME answers 1983-2024)

Output: bank/{slug}_wiki.json with real (unmodified) problems.

Problems are skipped when: they contain figures/diagrams ([asy]/Image),
choices can't be parsed (AMC), no boxed answer is found and no key exists,
the answer contradicts a key, or text is abnormally long.
"""
import json, re, csv, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
BANK = ROOT / "bank"

CONTEST_SLUG = {
    "AMC 8": "amc8",
    "AMC 10": "amc10", "AMC 10A": "amc10", "AMC 10B": "amc10",
    "AMC 12": "amc12", "AMC 12A": "amc12", "AMC 12B": "amc12",
    "AIME": "aime", "AIME I": "aime", "AIME II": "aime",
}

# ---------- answer keys ----------
def load_amc12_keys():
    keys = {}
    for line in open(RAW / "amc12_full.jsonl"):
        d = json.loads(line)
        keys[d["problem_id"]] = d["answer"].strip()
    return keys

def load_aime_keys():
    keys = {}
    for r in csv.DictReader(open(RAW / "aime_1983_2024.csv")):
        parts = r["ID"].split("-")
        num = parts[-1]
        part = parts[1] if len(parts) == 3 else ""
        keys[(r["Year"], part, num)] = r["Answer"].strip()
    return keys

# ---------- existing sources (avoid duplicating current banks) ----------
def existing_sources():
    srcs = set()
    for f in BANK.glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        for v in d.get("variants", []):
            if v.get("source"):
                srcs.add(v["source"])
    return srcs

# ---------- wikitext cleaning ----------
def strip_links(text):
    text = re.sub(r"\[\[(?:Image|File):[^\]]*\]\]", "", text)  # drop image refs wholly
    text = re.sub(r"\{\|.*?\|\}", "", text, flags=re.S)  # wikitable markup
    text = re.sub(r"\[\[([^|\]]*)\|([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    return text

def strip_templates(text):
    # remove {{...}} (possibly nested, simple iterative approach)
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return text

def latexify(text):
    text = re.sub(r"<cmath>(.*?)</cmath>", lambda m: "$$" + m.group(1).strip() + "$$", text, flags=re.S)
    text = re.sub(r"<imath>(.*?)</imath>", lambda m: "$" + m.group(1).strip() + "$", text, flags=re.S)
    text = re.sub(r"<math>(.*?)</math>", lambda m: "$" + m.group(1).strip() + "$", text, flags=re.S)
    return text

def first_solution_subsection(text):
    """If a Solution section contains ===Solution N=== subsections, keep only
    the first one; also strip any leftover ===...=== header lines."""
    lines = text.split("\n")
    out, in_first = [], False
    for ln in lines:
        if re.match(r"^=\s*Solution", ln.strip().strip("=").strip(), re.I) and ln.strip().startswith("==="):
            if in_first:
                break
            in_first = True
            continue
        if re.match(r"^===+.*?===+\s*$", ln):
            if in_first:
                break
            continue
        out.append(ln)
    return "\n".join(out)

def latex_dialect_fix(text):
    """Convert LaTeX dialect KaTeX can't parse."""
    text = re.sub(r"\\begin\{tabular\}(\{[^{}]*\})?", r"\\begin{array}\1", text)
    text = re.sub(r"\\end\{tabular\}", r"\\end{array}", text)
    text = re.sub(r"\\root\{(.*?)\}\\of\{", r"\\sqrt[\1]{", text)
    text = text.replace("&#36;", "\\$")  # currency dollar: keep escaped for KaTeX
    text = text.replace("\\overarc", "\\widehat")  # KaTeX lacks \overarc
    text = text.replace("\\ds", "")            # displaystyle shorthand
    # nested \(...\) inside $$...$$ blocks is invalid; unwrap it
    def fix_display(m):
        return "$$" + m.group(1).replace("\\(", " ").replace("\\)", " ") + "$$"
    text = re.sub(r"\$\$(.*?)\$\$", fix_display, text, flags=re.S)
    return text

def clean_inline(text):
    text = re.sub(r"\[asy\].*?\[/asy\]", "", text, flags=re.S)
    text = re.sub(r"<asy>.*?</asy>", "", text, flags=re.S)
    text = strip_links(text)
    text = strip_templates(text)
    text = latexify(text)
    text = re.sub(r"<youtube>.*?</youtube>", "", text, flags=re.S)
    text = re.sub(r"^\s*https?://\S+\s*$", "", text, flags=re.M)  # bare url lines
    text = re.sub(r"^[ \t]*~[^\n]*$", "", text, flags=re.M)        # ~Signature lines
    text = re.sub(r"<[^>]+>", "", text)  # stray html tags (<tt>, <youtube>, etc.)
    text = re.sub(r"~[A-Za-z][\w.-]*\)?\.?\s*$", "", text, flags=re.M)  # ~Sig). at line end
    text = re.sub(r"[ \t]+~[A-Za-z][\w.-]{2,}\)?", "", text)  # inline ~Signature
    text = latex_dialect_fix(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_sections(content):
    """Return dict of section-name -> text."""
    sections = {}
    cur_name, cur_lines = None, []
    for line in content.split("\n"):
        m = re.match(r"^==\s*([^=]+?)\s*==\s*$", line)
        if m:
            if cur_name is not None:
                sections[cur_name] = "\n".join(cur_lines)
            cur_name, cur_lines = m.group(1), []
        elif cur_name is not None:
            cur_lines.append(line)
    if cur_name is not None:
        sections[cur_name] = "\n".join(cur_lines)
    return sections

FIGURE_PAT = re.compile(r"\[asy|<asy|\[\[\s*(Image|File)\s*:", re.I)
FIGURE_WORDS = re.compile(r"figure below|in the figure|as shown|shown below|diagram below|pictured|in the diagram", re.I)

CHOICE_MARK = re.compile(r"\\textbf\{\s*\(?([A-E])\)?\s*\}")

def _unescape_dollars(text):
    """Replace \\$ -> $ only OUTSIDE math/imath/cmath tags."""
    parts = re.split(r"(<(?:imath|math|cmath)>.*?</(?:imath|math|cmath)>)", text, flags=re.S)
    for i in range(0, len(parts), 2):
        parts[i] = parts[i].replace("\\$", "$")
    return "".join(parts)

def _clean_choice(body):
    body = re.sub(r"</?(?:imath|math|cmath)>\s*", "", body)
    body = body.strip()
    # mediawiki artifacts inside choice text
    body = re.sub(r"\[\[Category:[^\]]*\]\]", "", body)
    # mediawiki triple-brace args, possibly containing nested LaTeX braces
    while True:
        new = re.sub(r"\{\{\{(.*?)\}\}\}", lambda m: m.group(1), body, flags=re.S)
        if new == body:
            break
        body = new
    body = strip_templates(body)
    body = strip_links(body)
    body = latexify(body)
    body = latex_dialect_fix(body)
    # drop a leading '}' if braces end up unbalanced
    while body.startswith("}") and body.count("{") < body.count("}"):
        body = body[1:].strip()
    while body.endswith("}") and body.count("{") > body.count("}"):
        body = body[:-1].strip()
    body = re.sub(r"^(?:\\[ ,;]|\s)+", "", body)
    body = re.sub(r"\\[qv]quad", "", body)  # separator spacing not needed
    body = body.strip()
    if "\\" in body and "\\$" not in body:
        body = body.replace("$", "")  # frontend wraps whole choice in $...$
    else:
        body = re.sub(r"\$\s*$", "", body).strip()   # stray trailing $
        body = re.sub(r"^\s*\$", "", body).strip()   # stray leading $
        if body.count("$") == 1:
            body = body.replace("$", "")
    return body

def extract_choices(problem_raw):
    """Return (question_text, choices dict) or (None, None) if unparseable."""
    marks = list(CHOICE_MARK.finditer(problem_raw))
    if len(marks) < 3:
        return None, None
    letters = [m.group(1) for m in marks]
    uniq = sorted(set(letters))
    if uniq != list("ABCDE"[:len(uniq)]) or len(set(letters)) != len(letters):
        return None, None
    if letters[0] != "A":
        return None, None
    # question = everything before the first mark; drop dangling opening tags
    q = problem_raw[: marks[0].start()]
    q = re.sub(r"<(imath|math|cmath)>\s*$", "", q).strip()
    choices = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(problem_raw)
        body = _clean_choice(problem_raw[m.end():end])
        if not body:
            return None, None
        choices[m.group(1)] = body
    if len(choices) != 5:
        return None, None
    return q, choices

BOXED = re.compile(r"\\boxed\s*\{")

def extract_boxed_letter(sol):
    m = re.search(r"\\boxed\s*\{\s*\\textbf\s*\{\s*\(?([A-E])\)?", sol)
    return m.group(1) if m else None

def extract_boxed_int(sol):
    for m in re.finditer(r"\\boxed\s*\{([^{}]*)\}", sol):
        val = m.group(1).strip().strip("$").strip()
        if re.fullmatch(r"0*\d{1,3}", val):
            return str(int(val))
    return None

def norm_int(s):
    s = s.strip()
    return str(int(s)) if re.fullmatch(r"0*\d+", s) else None

def main():
    amc12_keys = load_amc12_keys()
    aime_keys = load_aime_keys()
    have = existing_sources()

    out = {}   # slug -> list of variants
    stats = {"parse_fail": 0, "figure": 0, "no_solution": 0, "no_answer": 0,
             "key_mismatch": 0, "dup": 0, "bad_choices": 0, "too_long": 0, "ok": 0}
    per_slug = {}

    with open(RAW / "wikitext_problems.jsonl") as f:
        for line in f:
            d = json.loads(line)
            title, content = d["title"], d.get("content") or ""
            m = re.match(r"^(\d{4}) (.+?) Problems/Problem (\d+)$", title)
            if not m:
                continue
            year, contest, num = m.group(1), m.group(2), m.group(3)
            slug = CONTEST_SLUG.get(contest)
            if not slug:
                continue
            if not content or FIGURE_PAT.search(content.split("==")[0] if "==" in content else content):
                pass  # checked more precisely below on the problem section only

            sections = split_sections(content)
            prob_raw = None
            for name, text in sections.items():
                if re.fullmatch(r"\s*Problem\s*\d*\s*", name):
                    prob_raw = text
                    break
            if prob_raw is None:
                stats["parse_fail"] += 1
                continue
            if FIGURE_PAT.search(prob_raw):
                stats["figure"] += 1
                continue

            sol_raw = None
            for name, text in sections.items():
                if re.match(r"\s*Solutions?\b", name, re.I):
                    sol_raw = text
                    break
            if not sol_raw or len(sol_raw.strip()) < 30:
                stats["no_solution"] += 1
                continue

            source = f"{year} {contest} Problem {num}"

            # ---- question & choices ----
            is_aime = slug == "aime"
            if is_aime:
                if CHOICE_MARK.search(prob_raw):
                    stats["bad_choices"] += 1
                    continue
                question = prob_raw
                choices = None
            else:
                question, choices = extract_choices(prob_raw)
                if question is None:
                    stats["bad_choices"] += 1
                    continue

            question = clean_inline(question)
            if not question or len(question) > 1500:
                stats["too_long"] += 1
                continue
            if FIGURE_WORDS.search(question):
                stats["figure"] += 1
                continue

            solution = clean_inline(first_solution_subsection(sol_raw))
            solution = re.sub(r"\n=+\s*$", "", solution).strip()
            if len(solution) > 3000 or len(solution) < 30:
                stats["too_long"] += 1
                continue

            # ---- answer & verification ----
            if is_aime:
                ans = extract_boxed_int(solution)
                key = aime_keys.get((year, contest.split()[-1] if contest != "AIME" else "", num))
                if key:
                    keyn = norm_int(key)
                    if ans is not None and keyn is not None and ans != keyn:
                        stats["key_mismatch"] += 1
                        continue
                    if ans is None and keyn is not None:
                        ans = keyn
                if ans is None:
                    stats["no_answer"] += 1
                    continue
            else:
                ans = extract_boxed_letter(solution)
                ab = "A" if contest.endswith("A") else "B" if contest.endswith("B") else None
                key = amc12_keys.get(f"{year}{ab}-P{num}") if slug == "amc12" and ab else None
                if key:
                    if ans is not None and ans != key:
                        stats["key_mismatch"] += 1
                        continue
                    if ans is None:
                        ans = key
                if ans is None or ans not in (choices or {}):
                    stats["no_answer"] += 1
                    continue

            if source in have:
                stats["dup"] += 1
                continue

            out.setdefault(slug, []).append({
                "position": int(num),
                "source": source,
                "question": question,
                "choices": choices,
                "answer": ans,
                "solution": solution,
            })
            stats["ok"] += 1
            per_slug[slug] = per_slug.get(slug, 0) + 1

    for slug, variants in out.items():
        doc = {"competition": slug.upper(), "set": "wiki", "variants": variants}
        path = BANK / f"{slug}_wiki.json"
        path.write_text(json.dumps(doc, indent=1))
        print(f"WROTE {path.name}: {len(variants)} variants")

    print("\nstats:", json.dumps(stats, indent=1))
    print("per slug:", per_slug)

if __name__ == "__main__":
    main()

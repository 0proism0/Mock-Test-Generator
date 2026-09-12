"""Build additional bank sets from data/all_questions.jsonl.

This file is a pre-cleaned dataset (question/choices/answer/solutions already
parsed from AoPS wiki), covering AMC 8/10/12 + AIME. It overlaps heavily with
the wikitext dump, so sources already present in bank/*.json are skipped.

Answer verification:
  - AMC 12 vs raw/amc12_full.jsonl answer letters
  - AIME   vs raw/aime_1983_2024.csv integer answers
  - AMC 8/10: boxed letter in the chosen solution must agree with the
    dataset answer when a boxed letter exists.

Output: bank/{slug}_allq.json
"""
import json, re, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
DATA = ROOT / "data"
BANK = ROOT / "bank"

FIGURE_WORDS = re.compile(
    r"figure below|in the figure|as shown|shown below|diagram below|"
    r"pictured|in the diagram|\[\[Image|\[\[File", re.I)

def load_amc12_keys():
    return {json.loads(l)["problem_id"]: json.loads(l)["answer"].strip()
            for l in open(RAW / "amc12_full.jsonl")}

def load_aime_keys():
    keys = {}
    for r in csv.DictReader(open(RAW / "aime_1983_2024.csv")):
        parts = r["ID"].split("-")
        part = parts[1] if len(parts) == 3 else ""
        keys[(r["Year"], part, parts[-1])] = r["Answer"].strip()
    return keys

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

def latex_dialect_fix(text):
    text = re.sub(r"\\begin\{tabular\}(\{[^{}]*\})?", r"\\begin{array}\1", text)
    text = re.sub(r"\\end\{tabular\}", r"\\end{array}\1".replace("\\1", ""), text)
    text = re.sub(r"\\root\{(.*?)\}\\of\{", r"\\sqrt[\1]{", text)
    text = text.replace("&#36;", "\\$")  # currency dollar: keep escaped for KaTeX
    text = text.replace("\\overarc", "\\widehat")  # KaTeX lacks \overarc
    def fix_display(m):
        return "$$" + m.group(1).replace("\\(", " ").replace("\\)", " ") + "$$"
    text = re.sub(r"\$\$(.*?)\$\$", fix_display, text, flags=re.S)
    return text

def clean(text):
    text = re.sub(r"\[asy\].*?\[/asy\]", "", text, flags=re.S)
    text = re.sub(r"<asy>.*?</asy>", "", text, flags=re.S)
    text = re.sub(r"\[\[Category:[^\]]*\]\]", "", text)
    # mediawiki links: [[target|display]] -> display, [[target]] -> target
    text = re.sub(r"\[\[(?:Image|File):[^\]]*\]\]", "", text)  # drop image refs wholly
    text = re.sub(r"\{\|.*?\|\}", "", text, flags=re.S)  # wikitable markup
    text = re.sub(r"\[\[([^|\]]*)\|([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    # mediawiki triple-brace args, possibly containing nested LaTeX braces
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\{\{\{(.*?)\}\}\}", lambda m: m.group(1), text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)  # stray html
    text = text.replace("{}", "")        # emptied template args
    text = re.sub(r"^[ \t]*~[^\n]*$", "", text, flags=re.M)
    text = re.sub(r"\$\\,\\\$|\\,\\\$\$", "", text)  # stray currency artifacts
    text = latex_dialect_fix(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def clean_choice_text(text):
    t = clean(text)
    if "\\" in t and "\\$" not in t:
        # math-y choice: strip all $ so the frontend wraps it wholly in $...$
        t = t.replace("$", "")
    else:
        t = re.sub(r"\$\s*$", "", t).strip()
        t = re.sub(r"^\s*\$", "", t).strip()
        if t.count("$") == 1:
            t = t.replace("$", "")
    return t.strip()

def pick_solution(solutions):
    """Shortest solution >= 100 chars; fall back to the first."""
    if not solutions:
        return None
    cands = [str(s) for s in solutions if len(str(s)) >= 100]
    if cands:
        return min(cands, key=len)
    return str(solutions[0])

def boxed_letter(text):
    m = re.search(r"\\boxed\s*\{\s*\\textbf\s*\{\s*\(?([A-E])\)?", text)
    return m.group(1) if m else None

def boxed_int(text):
    for m in re.finditer(r"\\boxed\s*\{([^{}]*)\}", text):
        v = m.group(1).strip().strip("$").strip()
        if re.fullmatch(r"0*\d{1,3}", v):
            return str(int(v))
    return None

def contest_slug(d):
    c = d["competition"]
    return {"AMC 8": "amc8", "AMC 10": "amc10", "AMC 12": "amc12", "AIME": "aime"}.get(c)

def source_str(d):
    return f'{d["year"]} {d["contest"].split(str(d["year"]))[-1].strip()} Problem {d["problem_number"]}'

def main():
    amc12_keys = load_amc12_keys()
    aime_keys = load_aime_keys()
    have = existing_sources()

    out = {}
    stats = {"dup": 0, "figure": 0, "no_sol": 0, "bad_type": 0, "len": 0,
             "key_mismatch": 0, "boxed_mismatch": 0, "no_answer": 0, "ok": 0}

    for line in open(DATA / "all_questions.jsonl"):
        d = json.loads(line)
        slug = contest_slug(d)
        if not slug or d.get("type") == "unknown":
            stats["bad_type"] += 1
            continue
        source = source_str(d)
        if source in have:
            stats["dup"] += 1
            continue

        question = clean(d["question"])
        if not question or len(question) > 1500 or FIGURE_WORDS.search(question):
            stats["figure"] += 1
            continue

        sol = pick_solution(d.get("solutions"))
        if not sol:
            stats["no_sol"] += 1
            continue
        sol = clean(sol)
        if len(sol) < 40 or len(sol) > 2500:
            stats["len"] += 1
            continue

        is_aime = slug == "aime"
        answer = str(d.get("answer", "")).strip()
        if is_aime:
            ans = str(int(answer)) if re.fullmatch(r"0*\d{1,3}", answer) else None
            part = ""
            m = re.search(r"AIME\s+(I+)$", d["contest"])
            if m:
                part = m.group(1)
            key = aime_keys.get((str(d["year"]), part, str(d["problem_number"])))
            if key and ans is not None and str(int(key)) != ans:
                stats["key_mismatch"] += 1
                continue
            if ans is None:
                boxed = boxed_int(sol)
                if boxed:
                    ans = boxed
            if ans is None:
                stats["no_answer"] += 1
                continue
            choices = None
        else:
            choices = {k: clean_choice_text(str(v)) for k, v in (d.get("choices") or {}).items()}
            if sorted(choices) != ["A", "B", "C", "D", "E"] or answer not in choices:
                stats["no_answer"] += 1
                continue
            if any(not v or len(v) > 200 for v in choices.values()):
                stats["no_answer"] += 1
                continue
            boxed = boxed_letter(sol)
            if boxed and boxed != answer:
                stats["boxed_mismatch"] += 1
                continue
            # AMC 12 cross-check with local key
            ab = "A" if d["contest"].endswith("A") else "B" if d["contest"].endswith("B") else None
            key = amc12_keys.get(f'{d["year"]}{ab}-P{d["problem_number"]}') if slug == "amc12" and ab else None
            if key and key != answer:
                stats["key_mismatch"] += 1
                continue
            ans = answer

        out.setdefault(slug, []).append({
            "position": int(d["problem_number"]),
            "source": source,
            "question": question,
            "choices": choices,
            "answer": ans,
            "solution": sol,
        })
        stats["ok"] += 1

    for slug, variants in out.items():
        path = BANK / f"{slug}_allq.json"
        path.write_text(json.dumps(
            {"competition": slug.upper(), "set": "allq", "variants": variants}, indent=1))
        print(f"WROTE {path.name}: {len(variants)} variants")
    print("\nstats:", json.dumps(stats, indent=1))

if __name__ == "__main__":
    main()

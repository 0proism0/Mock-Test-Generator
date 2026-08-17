"""Parse scraped AoPS wikitext into clean per-competition JSON datasets.

Input : raw/wikitext_problems.jsonl  ({"title", "content"})
Output: data/amc8.json, data/amc10.json, data/amc12.json, data/aime.json
        data/all_questions.jsonl (combined)
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
DATA = ROOT / "data"

PROBLEM_PAT = re.compile(
    r"^(\d{4}) (AMC 8|AMC 10|AMC 12|AIME)(A|B|P| I{1,2})? Problems/Problem (\d+)$"
)
REDIRECT_PAT = re.compile(r"^\s*#REDIRECT\s*\[\[(.+?)\]\]", re.I)
CHOICE_MARK = re.compile(
    r"\\(?:textbf|mathrm|text|textrm)\s*\{\s*\(\s*([A-E])\s*\)\s*\\?\s*\}"
    r"|\(\s*\\(?:mathrm|text|textbf)\s*\{?\s*([A-E])\s*\}?\s*\)\s*\\?\s*"
)

# valid contest naming per competition
def valid_contest(comp, variant, year, pnum):
    if comp in ("AMC 8", "AMC 10", "AMC 12") and not (1 <= pnum <= 25):
        return False
    if comp == "AIME" and not (1 <= pnum <= 15):
        return False
    if comp == "AMC 8":
        return variant == "" and 1999 <= year <= 2026
    if comp in ("AMC 10", "AMC 12"):
        if variant == "":
            return year in (2000, 2001)
        return year >= 2002
    if comp == "AIME":
        if variant == "":
            return 1983 <= year <= 1999
        return year >= 2000
    return False


def texify(text: str) -> str:
    text = re.sub(r"<cmath>(.*?)</cmath>", lambda m: "$$" + m.group(1) + "$$", text, flags=re.S)
    text = re.sub(r"<imath>(.*?)</imath>", lambda m: "$" + m.group(1) + "$", text, flags=re.S)
    text = re.sub(r"<math>(.*?)</math>", lambda m: "$" + m.group(1) + "$", text, flags=re.S)
    return text


def split_sections(wikitext: str):
    parts = re.split(r"^==\s*(.+?)\s*==.*$", wikitext, flags=re.M)
    prelude = parts[0]
    sections = []
    for i in range(1, len(parts) - 1, 2):
        sections.append((parts[i].strip(), parts[i + 1].strip()))
    return prelude, sections


def strip_templates(text: str) -> str:
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[Category:[^\]]*\]\]", "", text)
    return text


def strip_dangling_dollar(s: str) -> str:
    s = s.rstrip()
    while s.endswith("$") and s.count("$") % 2 == 1:
        s = s[:-1].rstrip()
    return s


INLINE_CHOICE = re.compile(
    r"\\(?:textbf|mathrm|text|textrm)\s*\{\s*\(\s*([A-E])\s*\)?\s*\\?\s*([^}]*?)\s*\}"
)


def clean_choice_value(val: str) -> str:
    val = re.sub(r"^(\\qquad|\\quad|\\hspace\{[^}]*\}|\\\s|[\s}])+", "", val)
    val = re.sub(r"(\\qquad|\\quad|\\hspace\{[^}]*\}|\\\s|\s)+$", "", val)
    while val.endswith("}") and val.count("}") > val.count("{"):
        val = val[:-1].rstrip()
    return strip_dangling_dollar(val.strip())


def extract_choices(problem_text: str):
    text = problem_text
    matches = list(CHOICE_MARK.finditer(text))
    if len(matches) < 5:
        # normalize double braces like \textbf{{(B)}} and retry
        text = re.sub(r"\\(textbf|mathrm|text|textrm)\s*\{\s*\{\s*\(", r"\\\1{(", text)
        matches = list(CHOICE_MARK.finditer(text))
    if len(matches) >= 5:
        letters = [(m.group(1) or m.group(2)) for m in matches]
        if letters == ["A", "B", "C", "D", "E"]:
            stem = text[: matches[0].start()].strip()
            choices = {}
            for i, m in enumerate(matches):
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                val = text[m.end() : end]
                choices[m.group(1) or m.group(2)] = clean_choice_value(val)
            return strip_dangling_dollar(stem), choices
    # last resort: value inside braces, e.g. \mathrm{(A) \ 48 }
    matches = list(INLINE_CHOICE.finditer(text))
    if len(matches) >= 5 and [m.group(1) for m in matches[:5]] == ["A", "B", "C", "D", "E"]:
        stem = text[: matches[0].start()].strip()
        choices = {m.group(1): clean_choice_value(m.group(2)) for m in matches[:5]}
        return strip_dangling_dollar(stem), choices
    return problem_text.strip(), None


def extract_asy(text: str):
    """Pull [asy]...[/asy] blocks out; returns (text_without_asy, [asy_blocks])."""
    blocks = re.findall(r"\[asy\].*?\[/asy\]", text, flags=re.S)
    cleaned = re.sub(r"\[asy\].*?\[/asy\]", "[Diagram]", text, flags=re.S)
    return cleaned.strip(), blocks


def parse_answer_key(content: str):
    answers = []
    for line in content.splitlines():
        m = re.match(r"\s*#\s*(.+?)\s*$", line)
        if m:
            answers.append(m.group(1))
    return answers


def main():
    DATA.mkdir(exist_ok=True)
    raw = {}
    for line in (RAW / "wikitext_problems.jsonl").read_text().splitlines():
        if line.strip():
            item = json.loads(line)
            raw[item["title"]] = item["content"]

    def resolve(title, hops=0):
        content = raw.get(title, "")
        m = REDIRECT_PAT.match(content)
        if m and hops < 5:
            target = m.group(1).split("|")[0].replace("_", " ").strip()
            return resolve(target, hops + 1)
        return content

    answer_keys = {}
    for title, content in raw.items():
        if title.endswith(" Answer Key") and content:
            answer_keys[title[: -len(" Answer Key")]] = parse_answer_key(content)

    records = []
    skipped = {"junk": 0, "empty": 0}
    for title, content0 in raw.items():
        m = PROBLEM_PAT.match(title)
        if not m:
            continue
        year, comp, variant, pnum = (
            int(m.group(1)), m.group(2), m.group(3) or "", int(m.group(4)),
        )
        if not valid_contest(comp, variant, year, pnum):
            skipped["junk"] += 1
            continue
        content = strip_templates(resolve(title))
        if not content or REDIRECT_PAT.match(content):
            skipped["empty"] += 1
            continue
        contest = f"{year} {comp}{variant}"
        problem_raw, solutions = "", []
        prelude, sections = split_sections(content)
        for head, body in sections:
            hl = head.lower()
            if hl.startswith("problem"):
                problem_raw = body
            elif hl.startswith("solution") and "video" not in hl:
                solutions.append(body.strip())
        if not problem_raw.strip():
            problem_raw = prelude  # problem text before first heading
        problem_tex = texify(problem_raw)
        stem, choices = extract_choices(problem_tex)
        stem, asy_blocks = extract_asy(stem)
        if not stem and not asy_blocks:
            skipped["empty"] += 1
            continue
        comp_id = comp.replace(" ", "") + variant.replace(" ", "")
        rec = {
            "id": f"{year}_{comp_id}_P{pnum}",
            "competition": comp,
            "year": year,
            "contest": contest,
            "problem_number": pnum,
            "type": "multiple_choice" if choices else ("integer_answer" if comp == "AIME" else "unknown"),
            "question": stem,
            "choices": choices,
            "answer": None,
            "solutions": [texify(s) for s in solutions],
            "diagram_asy": asy_blocks,
            "has_diagram": bool(asy_blocks) or "[asy]" in content,
            "source_url": "https://artofproblemsolving.com/wiki/index.php/" + title.replace(" ", "_"),
        }
        keys = answer_keys.get(contest)
        if keys and 1 <= pnum <= len(keys):
            rec["answer"] = keys[pnum - 1]
        records.append(rec)

    by_comp = {}
    for r in records:
        by_comp.setdefault(r["competition"], []).append(r)
    all_recs = []
    for comp, recs in sorted(by_comp.items()):
        # drop stub/vandal contests (e.g. 2026 AMC 12A with a single page)
        sizes = {}
        for r in recs:
            sizes[r["contest"]] = sizes.get(r["contest"], 0) + 1
        tiny = {c for c, n in sizes.items() if n < 10}
        if tiny:
            print(f"  dropping stub contests: {sorted(tiny)}")
            recs = [r for r in recs if r["contest"] not in tiny]
        recs.sort(key=lambda r: (r["year"], r["contest"], r["problem_number"]))
        slug = comp.lower().replace(" ", "")
        (DATA / f"{slug}.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1))
        all_recs.extend(recs)
        n_ans = sum(1 for r in recs if r["answer"])
        n_ch = sum(1 for r in recs if r["choices"])
        print(f"{comp}: {len(recs)} problems, {len({r['contest'] for r in recs})} contests, "
              f"{n_ans} with answers, {n_ch} with choices")
    with (DATA / "all_questions.jsonl").open("w") as f:
        for r in all_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"TOTAL {len(all_recs)} problems | skipped: {skipped}")


if __name__ == "__main__":
    main()

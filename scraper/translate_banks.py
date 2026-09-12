"""Batch-translate bank questions/solutions to Chinese (question_zh / solution_zh).

Uses any OpenAI-compatible chat-completions API (OpenAI, DeepSeek, Moonshot,
or a local server). Config via environment variables:

  TRANSLATE_BASE_URL   e.g. https://api.openai.com/v1  (or https://api.deepseek.com)
  TRANSLATE_API_KEY    your key
  TRANSLATE_MODEL      e.g. gpt-4o-mini / deepseek-chat

Usage:
  .venv/bin/python scraper/translate_banks.py [--slug amc8] [--limit 50] [--solutions]

Only variants missing question_zh are translated. The prompt instructs the model
to preserve ALL LaTeX ($...$, $$...$$, \command{...}) unchanged and translate
only the surrounding prose. Results are written back into the bank JSON files.
"""
import json, os, re, sys, time, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "bank"
LOG = ROOT / "scraper" / "translation_log.jsonl"

BASE_URL = os.environ.get("TRANSLATE_BASE_URL", "https://api.openai.com/v1")
API_KEY = os.environ.get("TRANSLATE_API_KEY", "")
MODEL = os.environ.get("TRANSLATE_MODEL", "gpt-4o-mini")

PROMPT_Q = """Translate the following competition math problem into Simplified Chinese.
Rules:
- Keep ALL LaTeX math exactly as-is: $...$, $$...$$, every \\command{{...}} must be preserved character-for-character.
- Translate only the English prose around the math.
- Keep names, units and proper nouns as-is (common Chinese renderings ok, e.g. Tom→汤姆).
- Output ONLY the translated text, no explanations, no quotes.

Problem:
{text}"""

PROMPT_S = """Translate the following competition math solution into Simplified Chinese.
Rules:
- Keep ALL LaTeX math exactly as-is: $...$, $$...$$, every \\command{{...}} must be preserved character-for-character.
- Translate only the English prose around the math.
- Output ONLY the translated text, no explanations, no quotes.

Solution:
{text}"""


def call_api(prompt, retries=4):
    import urllib.request
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"  api error (attempt {attempt+1}): {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None


def latex_intact(orig, trans):
    """Extract all LaTeX segments from original and check they exist in translation."""
    segs = re.findall(r"\$\$.*?\$\$|\$[^$]+\$", orig, flags=re.S)
    return all(s in trans for s in segs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="only translate this slug (e.g. amc8)")
    ap.add_argument("--limit", type=int, default=0, help="max variants per file")
    ap.add_argument("--solutions", action="store_true", help="also translate solutions")
    args = ap.parse_args()

    if not API_KEY:
        sys.exit("Set TRANSLATE_API_KEY (and optionally TRANSLATE_BASE_URL / TRANSLATE_MODEL)")

    files = sorted(BANK.glob(f"{args.slug}*.json" if args.slug else "*.json"))
    done = skipped = failed = 0
    for f in files:
        d = json.loads(f.read_text())
        variants = d.get("variants", [])
        changed = False
        for v in variants:
            todo_q = not v.get("question_zh") and v.get("question")
            todo_s = args.solutions and not v.get("solution_zh") and v.get("solution")
            if not (todo_q or todo_s):
                skipped += 1
                continue
            if todo_q:
                src = v["question"][:4000]
                zh = call_api(PROMPT_Q.format(text=src))
                if zh and latex_intact(src, zh):
                    v["question_zh"] = zh
                    changed = True
                    done += 1
                else:
                    failed += 1
                    LOG.open("a").write(json.dumps(
                        {"file": f.name, "source": v.get("source"), "field": "question",
                         "ok": False}) + "\n")
                    continue
            if todo_s:
                src = v["solution"][:4000]
                zh = call_api(PROMPT_S.format(text=src))
                if zh and latex_intact(src, zh):
                    v["solution_zh"] = zh
                    changed = True
                    done += 1
                else:
                    failed += 1
            if args.limit and done >= args.limit:
                break
        if changed:
            f.write_text(json.dumps(d, indent=1, ensure_ascii=False))
            print(f"updated {f.name}")
    print(f"\ntranslated={done} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()

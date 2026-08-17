"""Scrape AoPS wiki problem pages (wikitext) via MediaWiki API.

Uses a Cloudflare clearance session (cookie + UA + chrome TLS impersonation).
Reads the problem index from raw/allproblems.json (vqbc/trivial) and fetches:
  - AMC 8  (1999-2026)
  - AMC 10 (2000-2026)
  - AMC 12 (2000-2026)
  - AIME   (1983-2026)
plus per-contest Answer Key pages.

Output: raw/wikitext_problems.jsonl  {"title": ..., "content": ...}
Resumable: already-saved titles are skipped.
"""
import json
import random
import re
import sys
import time
from pathlib import Path

from curl_cffi import requests as creq

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = RAW / "wikitext_problems.jsonl"
API = "https://artofproblemsolving.com/wiki/api.php"
BATCH = 40
MAX_YEAR = 2026

CONTEST_PATTERNS = [
    ("AMC 8", re.compile(r"^(\d{4}) AMC 8 Problems/Problem (\d+)$")),
    ("AMC 10", re.compile(r"^(\d{4}) AMC 10(A|B|P)? Problems/Problem (\d+)$")),
    ("AMC 12", re.compile(r"^(\d{4}) AMC 12(A|B|P)? Problems/Problem (\d+)$")),
    ("AIME", re.compile(r"^(\d{4}) AIME( I{1,2})? Problems/Problem (\d+)$")),
]


def build_targets():
    index = json.loads((RAW / "allproblems.json").read_text())
    titles, contests = [], set()
    for t in index:
        for name, pat in CONTEST_PATTERNS:
            m = pat.match(t)
            if m and int(m.group(1)) <= MAX_YEAR:
                titles.append(t)
                contests.add(t.split(" Problems/")[0])
                break
    # answer key pages for every contest we found
    for c in sorted(contests):
        titles.append(f"{c} Answer Key")
    return sorted(set(titles))


def load_session():
    sess = json.loads((ROOT / "scraper" / "aops_session.json").read_text())
    s = creq.Session(impersonate="chrome123")
    s.headers["User-Agent"] = sess["user_agent"]
    s.headers.update({
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://artofproblemsolving.com/wiki/index.php/AMC_Problems_and_Solutions",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    })
    for k, v in sess["cookies"].items():
        s.cookies.set(k, v, domain=".artofproblemsolving.com")
    return s


def main():
    s = load_session()

    done = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["title"])

    targets = [t for t in build_targets() if t not in done]
    print(f"already have {len(done)}, to fetch {len(targets)}", flush=True)

    n_ok = n_fail = 0
    with OUT.open("a") as f:
        for i in range(0, len(targets), BATCH):
            batch = targets[i : i + BATCH]
            params = {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "format": "json",
                "formatversion": "2",
                "titles": "|".join(batch),
            }
            ok = False
            for attempt in range(12):
                try:
                    r = s.get(API, params=params, timeout=40)
                    if r.status_code == 200:
                        ok = True
                        break
                    print(f"  batch {i}: HTTP {r.status_code}, retry {attempt}", flush=True)
                    if r.status_code == 403:
                        time.sleep(20)
                        s = load_session()  # pick up refreshed cookies if file was updated
                except Exception as e:
                    print(f"  batch {i}: {e}, retry {attempt}", flush=True)
                time.sleep(min(60, 5 * (attempt + 1)))
            if not ok:
                print(f"FATAL: cannot fetch batch starting at {i}", flush=True)
                sys.exit(1)
            pages = r.json()["query"]["pages"]
            for p in pages:
                content = ""
                if "revisions" in p:
                    content = p["revisions"][0]["slots"]["main"]["content"]
                f.write(json.dumps({"title": p["title"], "content": content}, ensure_ascii=False) + "\n")
                if content:
                    n_ok += 1
                else:
                    n_fail += 1
            print(f"fetched {i + len(batch)}/{len(targets)} (ok={n_ok} empty/missing={n_fail})", flush=True)
            time.sleep(2.5 + random.random() * 2)
    print(f"DONE ok={n_ok} empty={n_fail}", flush=True)


if __name__ == "__main__":
    main()

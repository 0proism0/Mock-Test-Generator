"""Slow, resumable AoPS-wiki download manager driven by competitions.yaml.

Uses a real Chromium (Playwright) so Cloudflare challenges auto-pass.
Fetches problem pages via the MediaWiki API through the browser context
(valid clearance cookie + real TLS fingerprint).

State: scraper/state.json  (per competition: status, discovered titles, done titles)
Raw output: raw/aops_wiki/<slug>.jsonl  ({"title", "content"})
Log: scraper/download.log

Run:  .venv/bin/python scraper/download_manager.py [--only slug1,slug2] [--fast]
"""
import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import yaml
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw" / "aops_wiki"
STATE = ROOT / "scraper" / "state.json"
LOG = ROOT / "scraper" / "download.log"
REGISTRY = ROOT / "competitions.yaml"
API = "https://artofproblemsolving.com/wiki/api.php"
WIKI_HOME = "https://artofproblemsolving.com/wiki/index.php/Main_Page"

BATCH = 20


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {}


def save_state(state):
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False))


def iter_pending(only=None):
    reg = yaml.safe_load(REGISTRY.read_text())
    for cat_key, cat in reg["categories"].items():
        for comp in cat["competitions"]:
            if comp.get("adapter") != "aops_wiki" or comp.get("status") != "pending":
                continue
            if only and comp["slug"] not in only:
                continue
            yield cat_key, comp


class WikiFetcher:
    def __init__(self, fast=False):
        self.fast = fast
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=True, channel="chrome")
        self.ctx = self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        self.page = self.ctx.new_page()
        self._pass_challenge()

    def _pass_challenge(self):
        for attempt in range(5):
            self.page.goto(WIKI_HOME, timeout=60000)
            title = self.page.title()
            if "Just a moment" not in title and "请稍候" not in title:
                log(f"challenge passed (attempt {attempt})")
                return
            time.sleep(8 + attempt * 5)
        raise RuntimeError("could not pass Cloudflare challenge")

    def fetch_titles(self, titles):
        """Fetch wikitext for a list of titles via in-page fetch (browser TLS+cookies)."""
        params = {
            "action": "query", "prop": "revisions", "rvprop": "content",
            "rvslots": "main", "format": "json", "formatversion": "2",
            "titles": "|".join(titles),
        }
        url = API + "?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
        for attempt in range(6):
            try:
                result = self.page.evaluate(
                    """async (url) => {
                        const r = await fetch(url, {credentials: 'include'});
                        return {status: r.status, body: await r.text()};
                    }""",
                    url,
                )
                if result["status"] == 200:
                    data = json.loads(result["body"])
                    out = {}
                    for p in data["query"]["pages"]:
                        content = ""
                        if "revisions" in p:
                            content = p["revisions"][0]["slots"]["main"]["content"]
                        out[p["title"]] = content
                    return out
                log(f"  HTTP {result['status']}, attempt {attempt}")
            except Exception as e:
                log(f"  error {e}, attempt {attempt}")
            time.sleep(10 * (attempt + 1))
            if attempt >= 1:
                try:
                    self._pass_challenge()
                except Exception as e:
                    log(f"  challenge refresh failed: {e}")
        return None

    def close(self):
        self.browser.close()
        self.pw.stop()


LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def discover(fetcher, comp):
    """Return list of problem-page titles for a competition via its index page."""
    idx = comp["aops_index"]
    res = fetcher.fetch_titles([idx])
    if not res or not res.get(idx):
        return []
    content = res[idx]
    links = LINK_RE.findall(content)
    problem_pages = sorted({l for l in links if re.search(r"Problems?/Problem ", l)})
    year_pages = sorted({l for l in links if re.search(r"\d{4}.*Problems?$", l)})
    # second level: year pages link to individual problem pages
    for i in range(0, len(year_pages), BATCH):
        res = fetcher.fetch_titles(year_pages[i : i + BATCH])
        if not res:
            continue
        for c in res.values():
            problem_pages |= set()  # noqa
            for l in LINK_RE.findall(c or ""):
                if re.search(r"Problems?/Problem ", l):
                    problem_pages.add(l)
        problem_pages = sorted(problem_pages)
        time.sleep(2 if fetcher.fast else 6 + random.random() * 6)
    return sorted(problem_pages)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="comma-separated slugs")
    ap.add_argument("--fast", action="store_true", help="short delays")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    fetcher = WikiFetcher(fast=args.fast)

    try:
        for cat_key, comp in iter_pending(only):
            slug = comp["slug"]
            st = state.setdefault(slug, {"status": "downloading", "done": [], "category": cat_key})
            out_path = RAW_DIR / f"{slug}.jsonl"
            done = set(st.get("done", []))

            if "titles" not in st:
                log(f"[{slug}] discovering pages via '{comp['aops_index']}' ...")
                titles = discover(fetcher, comp)
                st["titles"] = titles
                save_state(state)
                log(f"[{slug}] discovered {len(titles)} problem pages")
            titles = st["titles"]
            todo = [t for t in titles if t not in done]
            log(f"[{slug}] to fetch {len(todo)} (have {len(done)})")

            with out_path.open("a") as f:
                for i in range(0, len(todo), BATCH):
                    batch = todo[i : i + BATCH]
                    res = fetcher.fetch_titles(batch)
                    if res is None:
                        log(f"[{slug}] FATAL batch failure, pausing competition")
                        break
                    for t, c in res.items():
                        if c:
                            f.write(json.dumps({"title": t, "content": c}, ensure_ascii=False) + "\n")
                            done.add(t)
                    st["done"] = sorted(done)
                    save_state(state)
                    log(f"[{slug}] {len(done)}/{len(titles)}")
                    time.sleep(3 if args.fast else 8 + random.random() * 8)
            if len(done) >= len(titles):
                st["status"] = "done"
                save_state(state)
                log(f"[{slug}] DONE ({len(done)} pages)")
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()

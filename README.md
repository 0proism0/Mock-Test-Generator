# MockTest Maker

Mock exams for math competitions — two modes per competition:

- **Modified variants** (`Modified from …`): real problems with numbers changed, answers recomputed & script-verified (AMC/AIME family, Math Kangaroo, HMMT variants)
- **Real problems** (`Real problem · …`): official past papers from competitions whose organizers publish them free for practice (IMO, USAMO, Putnam, APMO, HMMT, MATHCOUNTS)

Generator rules: mock Problem N always comes from a real Problem N (difficulty ramp preserved),
sources are mixed across years within one test, and no source problem is ever reused
across generated tests (tracked in `tests/*_rand_*.json`).

## Run the web app

The backend is a single stdlib-Python file; the frontend is a vanilla-JS single page inlined in `app/static/index.html`.
No `npm`, no `requirements.txt`, and no virtual-env packages are required for the app itself.

```bash
python app/server.py    # then open http://localhost:8000
```

Or, if you prefer a venv:

```bash
python -m venv .venv
.venv/bin/python app/server.py
```

## Layout

- `competitions.yaml` — registry of target competitions (categories, source adapters, status)
- `bank/` — question pools (`<slug>_<set>.json`): variants + real problems with sources
- `bank_real/` — archived raw scrapes (real problems, reference)
- `tests/` — generated mock tests (JSON)
- `app/` — stdlib Python server + single-page exam UI (KaTeX loaded from CDN)
- `scraper/` — collection pipelines (AoPS wiki via browser, official PDFs/TeX/HTML)
- `raw/` — raw downloads (wikitext, PDFs, TeX)
- `data/` — clean per-competition JSON of AMC/AIME 真题

## Current banks (19 competitions, ~7,500 problems)

| Competition | Content | Type |
|---|---|---|
| AMC 8 | 554 variants (3 modified sets + ~480 real, verified vs keys) | MC |
| AMC 10 | 1095 variants (3 modified sets + ~1000 real) | MC |
| AMC 12 | 1133 variants (2 modified sets + ~1050 real, cross-checked vs answer key) | MC |
| AIME | 955 variants (2 modified sets + ~900 real, cross-checked vs answer key) | integer |
| Math Kangaroo | 11 variants | MC, modified |
| HMMT | 353 real + variants (2011–2025, answers+solutions) | short answer |
| SMT | 734 real (2011–2023, answers+solutions) | short answer |
| PUMaC | 1149 real (2019–2025, solutions) | short answer/proof |
| BMT | 589 real (2011–2025) | short answer |
| CMIMC | 458 real (2016–2025, solutions) | short answer |
| MATHCOUNTS | 95 real (2026 Chapter+State, answers+solutions) | short answer |
| UKMT | 198 real (JMC/IMC/SMC 2023–2026, answers) | MC |
| BPhO R1 | 24 real (2023–2024 Section 1 parts, worked solutions; typed mark schemes only — older years are scans) | numeric (2% tolerance) |
| COMC | 119 real (2011–2021, official solutions) | short answer/proof |
| CMO | 121 real (1969–2026, most with solutions) | proof |
| IMO | 397 real (1959–2026, with solutions) | proof |
| USAMO | 300 real (1972–2026, with solutions) | proof |
| Putnam | 300 real (1985–2025, official TeX + solutions) | proof |
| USAMTS | 237 real (editions 25–36, most with solutions) | proof |
| APMO | 28 real (partial) | proof |

## Pipelines (scraper/)

- `build_wiki_banks.py` — raw/wikitext_problems.jsonl (AoPS wiki dump) → `bank/*_wiki.json` (real AMC 8/10/12 + AIME problems with solutions; answers verified against local answer keys, figure problems filtered out)
- `build_allq_banks.py` — data/all_questions.jsonl (clean per-contest scrape) → `bank/*_allq.json` (same competitions, dedup'd against existing banks)
- `build_bpho.py` + `bpho_text.py` — BPhO Round 1 PDFs (raw/pdfs/bpho/, physicswithstefan mirror) → `bank/bpho_r1_A.json`. pdfplumber char-level reconstruction rebuilds super/subscripts (pypdf loses `10^8` → `108`), converts Unicode math italics to LaTeX, synthesizes spaces from x-gaps, and un-jumbles stacked fractions. Each Section-1 part (a/b/c…) becomes one numeric-answer variant graded with 2% tolerance; figure-dependent parts and parts without a confident numeric final answer are dropped. Only 2023+2024 mark schemes have a text layer (older S PDFs are scans), so the bank currently holds 24 parts; OCR would expand it.
- `scrape_aops.py` / browser worker — AoPS wiki (Cloudflare-challenged; browser fetch)
- `build_putnam.py` — Kedlaya Putnam archive TeX → bank
- `build_hmmt.py` — hmmt.org archive solutions PDFs → bank
- `build_mathcounts.py` — official MATHCOUNTS PDFs (problems+keys+solutions) → bank
- `build_dataset.py` — AMC/AIME wikitext → clean JSON

Next candidates (Tier-1 free sources): CEMC Waterloo series, UKMT/BMO, Purple Comet
(old contests need supervisor login), CMS COMC/CMO, USAMTS, university tournaments
(SMT, PUMaC, BMT, DMM, JHMT, CMIMC).

## FAQ

### What are all the `.b64` files?

They are base64-encoded official PDFs (mostly MATHCOUNTS Chapter/State and USAPhO past papers) used as temporary binary caches when downloading contest sources through a browser or a restricted network. The active pipeline now reads standard PDFs from `raw/pdfs/`; any `.b64` files left in the repo are legacy caches or copies inside the `Mock-Test-Generator/` subtree and are not loaded by `app/server.py`. You can ignore or delete them if you are not rebuilding the MATHCOUNTS/USAPhO banks.

### Why is there no `requirements.txt`?

The core web app is intentionally dependency-free: `app/server.py` uses only the Python standard library, and `app/static/index.html` is a plain HTML/CSS/JS single-page app (no React/Vue build step). Only a few scraper helpers need third-party packages (`pypdf` for `build_mathcounts.py`, `requests` for `push_github.py`). Install those ad-hoc when you actually run the scrapers, e.g.:

```bash
pip install pypdf requests
```

### Is there a frontend framework?

No separate frontend project. The UI is a single self-contained `index.html` with vanilla JavaScript; `server.py` just serves it and exposes a small JSON API. KaTeX is pulled from a CDN for math rendering.

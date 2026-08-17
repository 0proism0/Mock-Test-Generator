# MockTest Maker

Mock exams for math competitions — two modes per competition:

- **Modified variants** (`Modified from …`): real problems with numbers changed, answers recomputed & script-verified (AMC/AIME family, Math Kangaroo, HMMT variants)
- **Real problems** (`Real problem · …`): official past papers from competitions whose organizers publish them free for practice (IMO, USAMO, Putnam, APMO, HMMT, MATHCOUNTS)

Generator rules: mock Problem N always comes from a real Problem N (difficulty ramp preserved),
sources are mixed across years within one test, and no source problem is ever reused
across generated tests (tracked in `tests/*_rand_*.json`).

## Run the web app

```bash
.venv/bin/python app/server.py    # then open http://localhost:8000
```

## Layout

- `competitions.yaml` — registry of target competitions (categories, source adapters, status)
- `bank/` — question pools (`<slug>_<set>.json`): variants + real problems with sources
- `bank_real/` — archived raw scrapes (real problems, reference)
- `tests/` — generated mock tests (JSON)
- `app/` — stdlib Python server + single-page exam UI (KaTeX)
- `scraper/` — collection pipelines (AoPS wiki via browser, official PDFs/TeX/HTML)
- `raw/` — raw downloads (wikitext, PDFs, TeX)
- `data/` — clean per-competition JSON of AMC/AIME 真题

## Current banks (19 competitions, ~5,300 problems)

| Competition | Content | Type |
|---|---|---|
| AMC 8 | 75 variants (3 sets) | MC, modified |
| AMC 10 | 50 variants (2 sets) | MC, modified |
| AMC 12 | 50 variants (2 sets) | MC, modified |
| AIME | 30 variants (2 sets) | integer, modified |
| Math Kangaroo | 11 variants | MC, modified |
| HMMT | 353 real + variants (2011–2025, answers+solutions) | short answer |
| SMT | 734 real (2011–2023, answers+solutions) | short answer |
| PUMaC | 1149 real (2019–2025, solutions) | short answer/proof |
| BMT | 589 real (2011–2025) | short answer |
| CMIMC | 458 real (2016–2025, solutions) | short answer |
| MATHCOUNTS | 95 real (2026 Chapter+State, answers+solutions) | short answer |
| UKMT | 198 real (JMC/IMC/SMC 2023–2026, answers) | MC |
| COMC | 119 real (2011–2021, official solutions) | short answer/proof |
| CMO | 121 real (1969–2026, most with solutions) | proof |
| IMO | 397 real (1959–2026, with solutions) | proof |
| USAMO | 300 real (1972–2026, with solutions) | proof |
| Putnam | 300 real (1985–2025, official TeX + solutions) | proof |
| USAMTS | 237 real (editions 25–36, most with solutions) | proof |
| APMO | 28 real (partial) | proof |

## Pipelines (scraper/)

- `scrape_aops.py` / browser worker — AoPS wiki (Cloudflare-challenged; browser fetch)
- `build_putnam.py` — Kedlaya Putnam archive TeX → bank
- `build_hmmt.py` — hmmt.org archive solutions PDFs → bank
- `build_mathcounts.py` — official MATHCOUNTS PDFs (problems+keys+solutions) → bank
- `build_dataset.py` — AMC/AIME wikitext → clean JSON

Next candidates (Tier-1 free sources): CEMC Waterloo series, UKMT/BMO, Purple Comet
(old contests need supervisor login), CMS COMC/CMO, USAMTS, university tournaments
(SMT, PUMaC, BMT, DMM, JHMT, CMIMC).

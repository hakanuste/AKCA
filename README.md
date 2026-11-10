# AKÇA — Independent Financial Research

AKÇA is an independent research and decision-support platform for public markets, company fundamentals, institutional research, valuation, portfolio risk, IPO performance and direct-market price tracking.

**AKÇA does not connect to a broker to place orders and does not execute trades.** It records evidence and research views; it is not a substitute for licensed investment advice.

## Current first-release scope

- Responsive public product introduction in the web directory.
- GitHub Pages deployment workflow.
- FastAPI service and SQLite persistence.
- Imported 2022 CPI reference basket: 409 item codes; historical prices are deliberately not imported.
- Vendor-price observations with source URL, timestamp, region, channel, unit, stock, delivery, membership and campaign fields.
- Manual approval queue. New observations are pending and excluded from calculations until approved.
- Explicit product/quality/pack-size variants. Same-item variants are not blended without declared within-item weights.
- Unit normalization for mass, volume, count, length, area, volume and service/hour units.
- Fixed-weight month-over-month price index. Calculation is blocked when official item weights, within-item variant weights, previous-month observations or minimum seller coverage are incomplete.
- Protected write API using an environment API key.
- CLI, automated tests and GitHub Actions CI.

## What is not yet connected

There are no automatic price scrapers or live market feeds in this release. Provider access, API licensing, terms of use and credentials must be assessed before integrations are enabled. No sample or synthetic prices are loaded into the database. Public market and company-data modules are the next development stage.

## Run locally (macOS / Linux)

Use Python 3.11 or newer.

    git clone https://github.com/hakanuste/AKCA.git
    cd AKCA
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    pip install -e ".[dev]"
    cp .env.example .env

Generate a private API key:

    openssl rand -hex 32

Set AKCA_API_KEY to the generated value in .env. Keep .env private; it is ignored by Git.

Initialize the reference data and database:

    akca init
    akca item-count
    akca check-weights

Start the API:

    uvicorn akca.api:app --reload

- API health: http://127.0.0.1:8000/health
- Interactive API docs: http://127.0.0.1:8000/docs
- Reference items: http://127.0.0.1:8000/items
- Weight readiness: http://127.0.0.1:8000/weights/status

### Local introduction page

    python -m http.server 8080 --directory web

Open http://127.0.0.1:8080.

## Price observation workflow

1. Add a specific comparable product variant to a 2022 basket item. Use a stable variant key for the same SKU, quality and pack definition across sellers.
2. Set a documented within-item weight. Keep weight_verified=false until the representative product mix and its source are actually established.
3. Record seller observations for that exact variant, including price, package quantity, unit, source URL, timestamp, region, channel, stock and delivery conditions.
4. Review the source and product match. Only approved observations enter calculations.
5. Collect at least three distinct sellers for each variant in both the current and immediately previous calendar month.
6. Set and verify official 2022 item weights from an authoritative source. The supplied basket workbook does not contain these weights.
7. Calculate the month. The system blocks the index if any required data or weight is missing.

Example CLI command structure (the weight value below is illustrative only and must not be copied as an actual TÜİK weight):

    akca add-variant 0111101 rice-1kg "Pirinç, aynı marka/SKU ve 1 kg paket" 100 "Temsil metodolojisi ve kaynak URL"
    akca set-item-weight 0111101 2.5 "Resmî 2022 ağırlık tablosu URL ve satır bilgisi" --verified
    akca calculate-index 2026-11

## Authenticated API write requests

Send the header X-AKCA-API-Key with your secret to write endpoints. If AKCA_API_KEY is not configured, writes are disabled. The browser must never contain a production secret in a public HTML file or public repository.

## API routes

| Method | Route | Purpose |
|---|---|---|
| GET | /health | Health and write-state |
| GET | /reference/source | Reference basket provenance and caveats |
| GET | /items | Search and paginate the 409 reference items |
| GET | /items/{item_code}/variants | List comparable variants |
| POST | /items/{item_code}/variants | Register a product variant (API key) |
| GET | /weights/status | Validate item and within-item weights |
| POST | /observations | Record a pending seller price (API key) |
| GET | /observations | Review queue and observation list (API key) |
| PATCH | /observations/{id}/review | Approve/reject/return observation (API key) |
| POST | /index/{YYYY-MM} | Calculate a month (API key) |
| GET | /stats/{YYYY-MM} | Retrieve monthly detail |
| GET | /dashboard/summary | Summary metrics |

## Price index method and safeguards

See docs/METHODOLOGY.md. The AKÇA independent fixed-basket price index is not the official TÜFE. It is not published as a complete monthly index unless coverage and every required weight are verified.

## Development

    python -m compileall -q src
    pytest -q
    ruff check src tests

Continuous integration runs compile and pytest on pushes and pull requests to main.

## Project independence

AKÇA has its own repository, database, runtime and API. It is separate from ÜLGEN and ÖTÜKEN and does not import or depend on their code.

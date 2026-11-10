# AKÇA architecture

## Independent project boundary

AKÇA has its own repository, database, services and user interface. It has no runtime dependency on ÜLGEN or ÖTÜKEN and does not import their code or databases.

## First-release layers

- web/: static product introduction site.
- src/akca/api.py: FastAPI HTTP API, CORS and API-key protected writes.
- src/akca/db.py: SQLite schema and database bootstrap.
- src/akca/pricing.py: price-observation validation, unit normalization and review state.
- src/akca/index.py: variant, item and fixed-basket monthly calculation gates.
- src/akca/ingest.py: reference-item import and item/variant weight management.
- src/akca/cli.py: local operations and management commands.
- data/reference/: version-controlled reference lists.
- tests/: automated correctness and coverage checks.

## Data trust

Every price observation stores a source URL, vendor, timestamp, region, channel, product description and purchase conditions. New observations are pending by default. The index cannot be calculated from missing or unverified weights.

## Before production deployment

- Move from SQLite to PostgreSQL and add a migration tool.
- Add user/role identity, audit logs, rate limiting and secret management.
- Implement licensed provider adapters and a source registry.
- Add backup/restore and monitoring.
- Deploy the API behind TLS; GitHub Pages hosts only the static website, not the database or API.
- Validate market/financial data quality, source dependency and backtest methodology.

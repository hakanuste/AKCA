import sqlite3
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS items (
    item_code TEXT PRIMARY KEY,
    name_tr TEXT NOT NULL,
    name_en TEXT,
    group_name TEXT NOT NULL,
    weight_percent REAL,
    unit_definition TEXT,
    matching_note TEXT,
    weight_source TEXT,
    weight_verified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS item_variants (
    item_code TEXT NOT NULL REFERENCES items(item_code) ON DELETE CASCADE,
    variant_key TEXT NOT NULL,
    label TEXT NOT NULL,
    within_item_weight_percent REAL NOT NULL,
    weight_source TEXT NOT NULL,
    weight_verified INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_code, variant_key),
    CHECK (within_item_weight_percent >= 0 AND within_item_weight_percent <= 100)
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    item_code TEXT NOT NULL,
    variant_key TEXT NOT NULL,
    vendor TEXT NOT NULL,
    product_description TEXT NOT NULL,
    region TEXT NOT NULL,
    channel TEXT NOT NULL,
    quantity REAL NOT NULL CHECK(quantity > 0),
    unit TEXT NOT NULL,
    normalized_unit TEXT,
    price_try REAL NOT NULL CHECK(price_try > 0),
    normalized_price_try REAL,
    in_stock INTEGER NOT NULL,
    shipping_try REAL NOT NULL DEFAULT 0,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    membership_required INTEGER NOT NULL DEFAULT 0,
    campaign_condition TEXT,
    quality_status TEXT NOT NULL DEFAULT 'pending',
    review_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_code, variant_key)
      REFERENCES item_variants(item_code, variant_key) ON DELETE RESTRICT,
    UNIQUE(period, item_code, variant_key, vendor, product_description, region, channel, observed_at)
);

CREATE INDEX IF NOT EXISTS idx_obs_period_item_variant
    ON observations(period, item_code, variant_key);
CREATE INDEX IF NOT EXISTS idx_obs_vendor ON observations(vendor);
CREATE INDEX IF NOT EXISTS idx_obs_status_period ON observations(quality_status, period);

CREATE TABLE IF NOT EXISTS variant_monthly_stats (
    period TEXT NOT NULL,
    item_code TEXT NOT NULL,
    variant_key TEXT NOT NULL,
    seller_count INTEGER NOT NULL,
    min_price REAL NOT NULL,
    max_price REAL NOT NULL,
    mean_price REAL NOT NULL,
    median_price REAL NOT NULL,
    previous_mean_price REAL,
    monthly_change_pct REAL,
    normalized_unit TEXT NOT NULL,
    sufficient_data INTEGER NOT NULL,
    notes TEXT,
    PRIMARY KEY(period, item_code, variant_key),
    FOREIGN KEY(item_code, variant_key)
      REFERENCES item_variants(item_code, variant_key)
);

CREATE TABLE IF NOT EXISTS item_monthly_stats (
    period TEXT NOT NULL,
    item_code TEXT NOT NULL REFERENCES items(item_code),
    variant_count INTEGER NOT NULL,
    seller_count INTEGER NOT NULL,
    min_price REAL,
    max_price REAL,
    mean_price REAL,
    median_price REAL,
    monthly_change_pct REAL,
    weight_percent REAL,
    weighted_contribution_pp REAL,
    sufficient_data INTEGER NOT NULL,
    normalized_unit TEXT,
    notes TEXT,
    PRIMARY KEY(period, item_code)
);

CREATE TABLE IF NOT EXISTS index_runs (
    period TEXT PRIMARY KEY,
    index_value REAL,
    monthly_inflation_pct REAL,
    coverage_weight_pct REAL NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_cache (
    cache_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS company_profiles (
    symbol TEXT PRIMARY KEY,
    company_name TEXT,
    exchange TEXT,
    currency TEXT,
    country TEXT,
    sector TEXT,
    industry TEXT,
    website TEXT,
    market_cap REAL,
    shares_outstanding REAL,
    last_price REAL,
    price_timestamp TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    retrieved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS financial_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    metric_code TEXT NOT NULL,
    period_end TEXT NOT NULL,
    period_type TEXT NOT NULL,
    value REAL NOT NULL,
    currency TEXT,
    unit TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    retrieved_at TEXT NOT NULL,
    UNIQUE(symbol, metric_code, period_end, period_type, source)
);
CREATE INDEX IF NOT EXISTS idx_financial_snapshot_symbol_period
    ON financial_snapshots(symbol, period_end, metric_code);
CREATE TABLE IF NOT EXISTS price_history (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL NOT NULL,
    adjusted_close REAL,
    volume REAL,
    currency TEXT,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY(symbol, trade_date, source)
);
CREATE INDEX IF NOT EXISTS idx_price_history_symbol_date
    ON price_history(symbol, trade_date);
CREATE TABLE IF NOT EXISTS research_reports (
    report_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    as_of TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    confidence REAL,
    data_completeness REAL NOT NULL,
    risk_flags_json TEXT NOT NULL,
    report_json TEXT NOT NULL,
    methodology_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY,
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS broker_research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    institution TEXT NOT NULL,
    analyst TEXT,
    recommendation TEXT,
    target_price REAL,
    currency TEXT,
    published_at TEXT NOT NULL,
    report_url TEXT NOT NULL,
    source_name TEXT NOT NULL,
    dependency_group TEXT,
    verified INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_broker_research_symbol_date
    ON broker_research(symbol, published_at);
CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_currency TEXT NOT NULL DEFAULT 'TRY',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS portfolio_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL CHECK(quantity >= 0),
    average_cost REAL,
    cost_currency TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(portfolio_id, symbol)
);


CREATE TABLE IF NOT EXISTS source_registry (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_category TEXT NOT NULL,
    access_type TEXT NOT NULL,
    license_status TEXT NOT NULL,
    terms_url TEXT,
    attribution TEXT,
    enabled INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS broker_forecast_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_research_id INTEGER NOT NULL REFERENCES broker_research(id) ON DELETE CASCADE,
    evaluation_date TEXT NOT NULL,
    reference_price REAL NOT NULL,
    actual_price REAL NOT NULL,
    target_price_error_pct REAL,
    realized_return_pct REAL,
    notes TEXT,
    UNIQUE(broker_research_id, evaluation_date)
);
CREATE TABLE IF NOT EXISTS ipo_records (
    symbol TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    offer_date TEXT NOT NULL,
    offer_price REAL NOT NULL CHECK(offer_price > 0),
    offer_currency TEXT NOT NULL,
    shares_offered REAL,
    source_url TEXT NOT NULL,
    source_name TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT,
    detail_json TEXT
);

"""

def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    # Forward-only lightweight migrations for existing local databases.
    broker_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(broker_research)").fetchall()
    }
    if "reference_price_at_publication" not in broker_columns:
        conn.execute("ALTER TABLE broker_research ADD COLUMN reference_price_at_publication REAL")
    if "horizon_days" not in broker_columns:
        conn.execute("ALTER TABLE broker_research ADD COLUMN horizon_days INTEGER")
    financial_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(financial_snapshots)").fetchall()
    }
    if "verified" not in financial_columns:
        conn.execute("ALTER TABLE financial_snapshots ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
    if "notes" not in financial_columns:
        conn.execute("ALTER TABLE financial_snapshots ADD COLUMN notes TEXT")
    return conn

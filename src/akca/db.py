import sqlite3
from pathlib import Path
from .config import DB_PATH

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS items (
 item_code TEXT PRIMARY KEY, name_tr TEXT NOT NULL, name_en TEXT,
 group_name TEXT NOT NULL, weight_percent REAL, unit_definition TEXT,
 matching_note TEXT, weight_source TEXT, weight_verified INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS observations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT NOT NULL,
 item_code TEXT NOT NULL REFERENCES items(item_code), vendor TEXT NOT NULL,
 product_description TEXT NOT NULL, region TEXT NOT NULL, channel TEXT NOT NULL,
 quantity REAL NOT NULL, unit TEXT NOT NULL, price_try REAL NOT NULL CHECK(price_try > 0),
 in_stock INTEGER NOT NULL, shipping_try REAL NOT NULL DEFAULT 0,
 source_url TEXT NOT NULL, observed_at TEXT NOT NULL,
 membership_required INTEGER NOT NULL DEFAULT 0, campaign_condition TEXT,
 quality_status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(period,item_code,vendor,product_description,region,channel,quantity,unit,observed_at)
);
CREATE INDEX IF NOT EXISTS idx_obs_period_item ON observations(period,item_code);
CREATE INDEX IF NOT EXISTS idx_obs_vendor ON observations(vendor);
CREATE TABLE IF NOT EXISTS item_monthly_stats (
 period TEXT NOT NULL, item_code TEXT NOT NULL REFERENCES items(item_code),
 seller_count INTEGER NOT NULL, min_price REAL NOT NULL, max_price REAL NOT NULL,
 mean_price REAL NOT NULL, median_price REAL NOT NULL, previous_mean_price REAL,
 monthly_change_pct REAL, weight_percent REAL, weighted_contribution_pp REAL,
 sufficient_data INTEGER NOT NULL, notes TEXT, PRIMARY KEY(period,item_code)
);
CREATE TABLE IF NOT EXISTS index_runs (
 period TEXT PRIMARY KEY, index_value REAL, monthly_inflation_pct REAL,
 coverage_weight_pct REAL NOT NULL, status TEXT NOT NULL, notes TEXT,
 calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

def connect(db_path: Path | None = None):
 path = db_path or DB_PATH
 path.parent.mkdir(parents=True, exist_ok=True)
 conn = sqlite3.connect(path)
 conn.row_factory = sqlite3.Row
 conn.executescript(SCHEMA)
 return conn

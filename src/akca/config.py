import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("AKCA_DB_PATH", str(ROOT / "data" / "akca.db")))
ITEMS_PATH = ROOT / "data" / "reference" / "tuik_2022_items.csv"
MIN_SELLERS = int(os.getenv("AKCA_MIN_SELLERS_PER_ITEM", "3"))
PRICE_MAX_AGE_DAYS = int(os.getenv("AKCA_PRICE_MAX_AGE_DAYS", "10"))

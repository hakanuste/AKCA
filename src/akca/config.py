import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DB_PATH = Path(os.getenv("AKCA_DB_PATH", str(ROOT / "data" / "akca.db")))
ITEMS_PATH = ROOT / "data" / "reference" / "tuik_2022_items.csv"
MIN_SELLERS = int(os.getenv("AKCA_MIN_SELLERS_PER_ITEM", "3"))
PRICE_MAX_AGE_DAYS = int(os.getenv("AKCA_PRICE_MAX_AGE_DAYS", "10"))
API_KEY = os.getenv("AKCA_API_KEY", "").strip()
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "AKCA_CORS_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5500,http://127.0.0.1:5500,https://hakanuste.github.io",
    ).split(",")
    if origin.strip()
]

from __future__ import annotations

import os
import httpx

from .common import source_record, utc_now

BASE = "https://api.coingecko.com/api/v3"

def search_coin(query: str) -> dict:
    token = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    headers = {"x-cg-demo-api-key": token} if token else {}
    with httpx.Client(timeout=25, headers=headers) as client:
        response = client.get(f"{BASE}/search", params={"query": query})
        response.raise_for_status()
        data = response.json()
    coins = data.get("coins", [])[:12]
    return {
        "query": query,
        "coins": [
            {"id": c.get("id"), "name": c.get("name"), "symbol": c.get("symbol"),
             "market_cap_rank": c.get("market_cap_rank"), "thumb": c.get("thumb")}
            for c in coins
        ],
        "provider": source_record(
            "coingecko", "CoinGecko API", "crypto_asset_discovery",
            "public_or_demo_api", "retrieved", "https://docs.coingecko.com/",
            [
                "Public endpoint is rate limited and may vary; Demo key is recommended for stable use.",
                "Commercial display/redistribution requires an appropriate plan and attribution.",
            ],
        ),
        "retrieved_at": utc_now(),
    }

def fetch_coin(coin_id: str, currency: str = "usd") -> dict:
    token = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    headers = {"x-cg-demo-api-key": token} if token else {}
    params = {
        "vs_currency": currency.lower(),
        "ids": coin_id,
        "order": "market_cap_desc",
        "per_page": 1,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h,7d,30d,1y",
    }
    with httpx.Client(timeout=25, headers=headers) as client:
        response = client.get(f"{BASE}/coins/markets", params=params)
        response.raise_for_status()
        data = response.json()
    if not data:
        raise ValueError(f"CoinGecko varlığı bulunamadı: {coin_id}")
    row = data[0]
    return {
        "id": row.get("id"), "symbol": row.get("symbol", "").upper(),
        "name": row.get("name"), "currency": currency.upper(),
        "current_price": row.get("current_price"),
        "market_cap": row.get("market_cap"), "market_cap_rank": row.get("market_cap_rank"),
        "total_volume": row.get("total_volume"), "high_24h": row.get("high_24h"),
        "low_24h": row.get("low_24h"), "price_change_24h_pct": row.get("price_change_percentage_24h"),
        "price_change_7d_pct": row.get("price_change_percentage_7d_in_currency"),
        "price_change_30d_pct": row.get("price_change_percentage_30d_in_currency"),
        "price_change_1y_pct": row.get("price_change_percentage_1y_in_currency"),
        "last_updated": row.get("last_updated"),
        "provider": source_record(
            "coingecko", "CoinGecko API", "crypto_market_data", "public_or_demo_api",
            "retrieved", "https://docs.coingecko.com/",
            ["Free public API quotas vary; commercial redistribution licensing must be checked."],
        ),
        "retrieved_at": utc_now(),
    }

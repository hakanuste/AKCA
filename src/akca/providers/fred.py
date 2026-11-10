from __future__ import annotations

import os
from datetime import date, timedelta

import httpx

from .common import source_record, utc_now

BASE = "https://api.stlouisfed.org/fred/series/observations"

DEFAULT_SERIES = {
    "FEDFUNDS": "US Federal Funds Rate",
    "DGS10": "US 10-Year Treasury Yield",
    "CPIAUCSL": "US CPI (All Urban Consumers)",
    "UNRATE": "US Unemployment Rate",
    "DEXUSAL": "US Dollar / Turkish Lira",
}

def fetch_macro(series_ids: list[str] | None = None, observation_count: int = 24) -> dict:
    api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "not_configured",
            "series": [],
            "provider": source_record(
                "fred", "Federal Reserve Bank of St. Louis FRED",
                "macro_economic_data", "api_key_required", "not_configured",
                "https://fred.stlouisfed.org/docs/api/fred/",
                ["FRED requires an application-specific API key.", "Terms of use and source attribution apply."],
            ),
        }
    requested = series_ids or list(DEFAULT_SERIES)
    result = []
    errors = []
    with httpx.Client(timeout=25) as client:
        for series_id in requested[:12]:
            params = {
                "api_key": api_key,
                "file_type": "json",
                "series_id": series_id,
                "sort_order": "desc",
                "limit": min(max(observation_count, 1), 100),
            }
            try:
                response = client.get(BASE, params=params)
                response.raise_for_status()
                rows = response.json().get("observations", [])
                values = []
                for row in reversed(rows):
                    value = row.get("value")
                    if value in (None, ".", ""):
                        continue
                    try:
                        values.append({"date": row.get("date"), "value": float(value)})
                    except (TypeError, ValueError):
                        continue
                result.append({
                    "series_id": series_id,
                    "name": DEFAULT_SERIES.get(series_id, series_id),
                    "observations": values,
                    "latest": values[-1] if values else None,
                    "previous": values[-2] if len(values) > 1 else None,
                })
            except Exception as exc:
                errors.append({"series_id": series_id, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
    return {
        "status": "partial" if errors else "ok",
        "series": result,
        "errors": errors,
        "provider": source_record(
            "fred", "Federal Reserve Bank of St. Louis FRED",
            "macro_economic_data", "api_key_required", "retrieved",
            "https://fred.stlouisfed.org/docs/api/fred/",
            ["Each FRED request needs the user's own API key.", "Observation release frequency varies by series."],
        ),
        "retrieved_at": utc_now(),
    }

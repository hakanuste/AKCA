from __future__ import annotations

import os
from datetime import date, timedelta

import httpx

from .common import source_record, utc_now

BASE_URL = os.getenv("TCMB_EVDS_BASE_URL", "https://evds3.tcmb.gov.tr/igmevdsms-dis/").rstrip("/") + "/"
DEFAULT_SERIES = {
    "TP.DK.USD.A.YTL": "USD/TRY döviz alış kuru",
    "TP.DK.EUR.A.YTL": "EUR/TRY döviz alış kuru",
    "TP.DK.GBP.A.YTL": "GBP/TRY döviz alış kuru",
    "TP.DK.CHF.A.YTL": "CHF/TRY döviz alış kuru",
}

def fetch_evds(
    series_codes: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    api_key = os.getenv("TCMB_EVDS_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "not_configured",
            "series": [],
            "provider": source_record(
                "tcmb_evds", "TCMB Elektronik Veri Dağıtım Sistemi",
                "turkiye_macro_fx_rates", "free_api_key_required", "not_configured",
                "https://evds3.tcmb.gov.tr/",
                ["TCMB EVDS hesabı açılarak API anahtarı alınmalıdır.", "API anahtarı yalnızca sunucu tarafında saklanmalıdır."],
            ),
        }
    end = end_date or date.today()
    start = start_date or (end - timedelta(days=365 * 3))
    if start > end:
        raise ValueError("Başlangıç tarihi bitiş tarihinden sonra olamaz.")
    codes = series_codes or list(DEFAULT_SERIES)
    if not codes or len(codes) > 20:
        raise ValueError("EVDS için 1-20 seri kodu gerekli.")
    # EVDS 3 Web Service uses the API key in the HTTP header named 'key'.
    service_path = (
        f"series={'-'.join(codes)}"
        f"&startDate={start.strftime('%d-%m-%Y')}"
        f"&endDate={end.strftime('%d-%m-%Y')}"
        "&type=json"
    )
    headers = {"key": api_key, "Accept": "application/json"}
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        response = client.get(BASE_URL + service_path, headers=headers)
        response.raise_for_status()
        payload = response.json()

    rows = payload if isinstance(payload, list) else (
        payload.get("items") or payload.get("data") or payload.get("dataItems") or []
    )
    series = []
    for code in codes:
        values = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_date = row.get("Tarih") or row.get("DATE") or row.get("date")
            if raw_date is None:
                continue
            value = None
            for key, cell in row.items():
                if key.strip().upper() == code.upper():
                    value = cell
                    break
            if value in (None, "", "-"):
                continue
            try:
                number = float(str(value).replace(",", "."))
            except ValueError:
                continue
            values.append({"date": str(raw_date), "value": number})
        series.append({
            "series_code": code,
            "name": DEFAULT_SERIES.get(code, code),
            "observations": values,
            "latest": values[-1] if values else None,
        })
    return {
        "status": "ok" if any(item["observations"] for item in series) else "empty",
        "series": series,
        "provider": source_record(
            "tcmb_evds", "TCMB Elektronik Veri Dağıtım Sistemi",
            "turkiye_macro_fx_rates", "free_api_key_required", "retrieved",
            "https://evds3.tcmb.gov.tr/",
            [
                "EVDS 3 beta is currently the new service; API response shape and catalogue may evolve.",
                "Series codes, units, frequency and aggregation method must be validated against EVDS metadata.",
                "The API key is kept server-side and must not be sent to the browser.",
            ],
        ),
        "retrieved_at": utc_now(),
    }

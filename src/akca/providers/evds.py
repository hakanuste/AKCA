from __future__ import annotations

import os
from datetime import date, timedelta

import httpx

from .common import source_record, utc_now

# EVDS 2's documented REST endpoint remains accessible alongside EVDS 3 beta.
# Users may override the service URL after reviewing the current TCMB guide.
BASE_URL = os.getenv(
    "TCMB_EVDS_BASE_URL",
    "https://evds2.tcmb.gov.tr/service/evds/",
).rstrip("/") + "/"

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
                [
                    "TCMB EVDS hesabı açılarak API anahtarı alınmalıdır.",
                    "Anahtar yalnızca sunucuda tutulmalıdır; tarayıcıya gönderilmez.",
                    "EVDS 3 beta ve EVDS 2 birlikte erişilebilir durumdadır.",
                ],
            ),
        }

    end = end_date or date.today()
    start = start_date or (end - timedelta(days=365 * 3))
    if start > end:
        raise ValueError("Başlangıç tarihi bitiş tarihinden sonra olamaz.")
    codes = [code.strip() for code in (series_codes or list(DEFAULT_SERIES)) if code.strip()]
    if not codes or len(codes) > 20:
        raise ValueError("EVDS için 1-20 seri kodu gerekli.")
    if any(len(code) > 100 for code in codes):
        raise ValueError("EVDS seri kodu 100 karakteri aşamaz.")

    # Official EVDS 2 guide documents this REST path and the 'key' request header.
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
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(
                "EVDS yanıtı JSON olarak çözümlenemedi. Seri kodu, tarih aralığı veya servis biçimini kontrol edin."
            ) from exc

    rows = payload if isinstance(payload, list) else (
        payload.get("items") or payload.get("data") or payload.get("dataItems") or []
    )
    if not isinstance(rows, list):
        raise ValueError("EVDS yanıtında beklenen veri satırları bulunamadı.")

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
                if key.strip().casefold() == code.casefold():
                    value = cell
                    break
            if value in (None, "", "-", "."):
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
                "This adapter uses the documented EVDS 2 REST compatibility endpoint while EVDS 3 beta remains available.",
                "EVDS 3 catalogue includes Turkey FX, domestic precious metals, BIST index/volume, repo/TLREF and government bond indicators.",
                "Confirm series codes, units, frequency and aggregation against current EVDS metadata before financial use.",
                "The API key is sent only from the server in the documented HTTP 'key' header.",
            ],
        ),
        "retrieved_at": utc_now(),
    }

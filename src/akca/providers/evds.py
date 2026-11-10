from __future__ import annotations

import os
from datetime import date, timedelta
from urllib.parse import quote

import httpx

from .common import source_record, utc_now

BASE_URL = os.getenv(
    "TCMB_EVDS_BASE_URL",
    "https://evds3.tcmb.gov.tr/igmevdsms-dis/",
).rstrip("/") + "/"

DEFAULT_SERIES = {
    "TP.DK.USD.A": "USD/TRY döviz alış kuru",
    "TP.DK.EUR.A": "EUR/TRY döviz alış kuru",
    "TP.DK.GBP.A": "GBP/TRY döviz alış kuru",
    "TP.DK.CHF.A": "CHF/TRY döviz alış kuru",
    "TP.APIFON4": "TCMB ağırlıklı ortalama fonlama maliyeti",
    "TP.BISTTLREF.KAPANIS": "BIST TLREF kapanış oranı",
}

def _request_json(path: str, api_key: str) -> dict | list:
    headers = {"key": api_key, "Accept": "application/json"}
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        response = client.get(BASE_URL + path.lstrip("/"), headers=headers)
        # Some early EVDS 3 clients documented a different auth header. Retry
        # only on authentication rejection; never retry data or server errors.
        if response.status_code in {401, 403}:
            fallback_headers = {"x-auth-token": api_key, "Accept": "application/json"}
            response = client.get(BASE_URL + path.lstrip("/"), headers=fallback_headers)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise ValueError(
                "EVDS 3 yanıtı JSON değil. API yolu, API anahtarı ve servis erişimini kontrol edin."
            ) from exc

def fetch_evds_catalogue(kind: str, code: str | None = None) -> dict:
    api_key = os.getenv("TCMB_EVDS_API_KEY", "").strip()
    if not api_key:
        return {"status": "not_configured", "items": []}
    kind = kind.strip().lower()
    if kind == "categories":
        path = "categories/type=json"
    elif kind == "datagroups":
        if code:
            path = "datagroups/mode=1&code=" + quote(code.strip(), safe="")
        else:
            path = "datagroups/mode=0&type=json"
    elif kind == "series":
        if not code:
            raise ValueError("Seri listesi için EVDS veri grubu veya seri kodu gerekli.")
        path = "serieList/type=json&code=" + quote(code.strip(), safe="")
    else:
        raise ValueError("kind categories, datagroups veya series olmalı.")
    payload = _request_json(path, api_key)
    if isinstance(payload, list):
        items = payload
    else:
        items = payload.get("items") or payload.get("data") or payload.get("datagroups") or []
    return {
        "status": "ok",
        "kind": kind,
        "query_code": code,
        "items": items,
        "source": "TCMB EVDS 3 catalogue",
        "retrieved_at": utc_now(),
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
                    "EVDS hesabı açılarak API anahtarı alınmalıdır.",
                    "Anahtar yalnızca sunucuda tutulmalıdır; tarayıcıya gönderilmez.",
                    "EVDS 3 beta ve EVDS 2 birlikte erişilebilir durumdadır.",
                ],
            ),
        }

    end = end_date or date.today()
    start = start_date or (end - timedelta(days=365 * 3))
    if start > end:
        raise ValueError("Başlangıç tarihi bitiş tarihinden sonra olamaz.")
    codes = [item.strip() for item in (series_codes or list(DEFAULT_SERIES)) if item.strip()]
    if not codes or len(codes) > 20:
        raise ValueError("EVDS için 1-20 seri kodu gerekli.")
    if any(len(item) > 100 for item in codes):
        raise ValueError("EVDS seri kodu 100 karakteri aşamaz.")

    path = (
        f"series={'-'.join(codes)}"
        f"&startDate={start.strftime('%d-%m-%Y')}"
        f"&endDate={end.strftime('%d-%m-%Y')}"
        "&type=json"
    )
    payload = _request_json(path, api_key)
    rows = payload if isinstance(payload, list) else (
        payload.get("items") or payload.get("data") or payload.get("dataItems") or []
    )
    if not isinstance(rows, list):
        raise ValueError("EVDS yanıtında beklenen veri satırları bulunamadı.")

    series = []
    for code in codes:
        normalized_key = code.replace(".", "_").casefold()
        values = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_date = row.get("Tarih") or row.get("DATE") or row.get("date")
            if raw_date is None:
                continue
            value = None
            for key, cell in row.items():
                if key.strip().casefold() in {code.casefold(), normalized_key}:
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
                "Uses the EVDS 3 beta igmevdsms-dis REST endpoint.",
                "The adapter retries x-auth-token only after key-header authentication failure.",
                "Catalogue coverage includes domestic FX, metals, BIST index/volume, TLREF/repo and government-bond indicators.",
                "Series codes, units, frequency and aggregation must be confirmed against live EVDS catalogue metadata before financial use.",
                "The API key is sent only from the server and is never exposed to browser JavaScript.",
            ],
        ),
        "retrieved_at": utc_now(),
    }

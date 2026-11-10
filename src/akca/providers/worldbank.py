from __future__ import annotations

import io
import os
import re
from functools import lru_cache

import httpx
from openpyxl import load_workbook

from .common import source_record, utc_now

WORLD_BANK_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
DEFAULT_XLSX = (
    "https://thedocs.worldbank.org/en/doc/"
    "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)
DATASET_LICENSE = "CC BY 4.0"

def _download_url() -> str:
    configured = os.getenv("WORLD_BANK_COMMODITY_XLSX_URL", "").strip()
    if configured:
        return configured
    try:
        with httpx.Client(timeout=25, follow_redirects=True) as client:
            page = client.get(WORLD_BANK_PAGE)
            page.raise_for_status()
        html = page.text
        matches = re.findall(
            r"(?:https://thedocs\.worldbank\.org)?/en/doc/[A-Za-z0-9-]+/related/CMO-Historical-Data-Monthly\.xlsx",
            html,
        )
        if matches:
            link = matches[0]
            return link if link.startswith("https://") else "https://thedocs.worldbank.org" + link
    except Exception:
        pass
    return DEFAULT_XLSX

@lru_cache(maxsize=1)
def _monthly_data() -> tuple[list[str], list[dict], str]:
    url = _download_url()
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        workbook_bytes = response.content
    workbook = load_workbook(io.BytesIO(workbook_bytes), read_only=True, data_only=True)
    sheet_name = next(
        (name for name in workbook.sheetnames if "monthly prices" in name.lower()),
        None,
    )
    if not sheet_name:
        raise ValueError("World Bank monthly workbook does not contain a Monthly Prices sheet.")
    sheet = workbook[sheet_name]
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    if len(rows) < 3:
        raise ValueError("World Bank commodity workbook has no usable observations.")
    header_index = None
    for i, row in enumerate(rows[:12]):
        if row and any(str(cell).strip().lower() in {"commodity", "crude oil", "gold", "silver"} for cell in row if cell is not None):
            header_index = i
            break
    if header_index is None:
        header_index = 0
    headers = [str(v).strip() if v is not None else "" for v in rows[header_index]]
    data = []
    for row in rows[header_index + 1:]:
        if not row:
            continue
        period = row[0]
        if period is None:
            continue
        period_text = str(period).strip()
        if not re.match(r"^\d{4}M\d{2}$", period_text):
            continue
        record = {"period": f"{period_text[:4]}-{period_text[5:7]}"}
        for idx, value in enumerate(row[1:], start=1):
            if idx >= len(headers) or not headers[idx]:
                continue
            if isinstance(value, (int, float)):
                record[headers[idx]] = float(value)
        if len(record) > 1:
            data.append(record)
    return headers[1:], data, url

def fetch_commodity_history(query: str | None = None, limit: int = 60) -> dict:
    headers, rows, source_url = _monthly_data()
    normalized = {h.casefold(): h for h in headers if h}
    selected = []
    if query:
        term = query.strip().casefold()
        selected = [name for lower, name in normalized.items() if term in lower]
    else:
        defaults = ("gold", "silver", "crude oil", "natural gas", "copper", "aluminum")
        selected = [
            name for name in headers
            if any(term in name.casefold() for term in defaults)
        ]
    series = []
    for name in selected[:30]:
        points = [
            {"period": row["period"], "price_usd": row.get(name)}
            for row in rows if row.get(name) is not None
        ]
        series.append({"name": name, "unit": "see World Bank workbook description sheet", "observations": points[-limit:]})
    return {
        "status": "ok" if series else "no_matching_series",
        "series": series,
        "periods_available": len(rows),
        "source": source_record(
            "world_bank_pink_sheet",
            "World Bank Commodity Markets Pink Sheet",
            "monthly_global_commodity_benchmarks",
            "public_download",
            "retrieved",
            source_url,
            [
                "Dataset is published monthly and is not an intraday quote feed.",
                "Dataset terms are CC BY 4.0; retain source attribution.",
                "Series units and benchmark definitions must be read from the workbook Description sheet.",
            ],
        ),
        "retrieved_at": utc_now(),
    }

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

DEFAULT_SERIES = (
    "GOLD",
    "SILVER",
    "CRUDE_BRENT",
    "CRUDE_WTI",
    "NATURAL_GAS",
    "COPPER",
    "ALUMINUM",
    "WHEAT_US_HRW",
    "CORN",
    "SOYBEANS",
    "COFFEE_ARABICA",
    "COCOA",
    "SUGAR",
)

def _download_url() -> str:
    configured = os.getenv("WORLD_BANK_COMMODITY_XLSX_URL", "").strip()
    if configured:
        return configured
    try:
        with httpx.Client(timeout=25, follow_redirects=True) as client:
            page = client.get(WORLD_BANK_PAGE)
            page.raise_for_status()
        matches = re.findall(
            r"(?:https://thedocs\.worldbank\.org)?/en/doc/[A-Za-z0-9-]+/related/CMO-Historical-Data-Monthly\.xlsx",
            page.text,
        )
        if matches:
            link = matches[0]
            return link if link.startswith("https://") else "https://thedocs.worldbank.org" + link
    except (httpx.HTTPError, ValueError):
        # Use the currently configured annual release URL as a fallback.
        pass
    return DEFAULT_XLSX

def _period_to_iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m")
    text = str(value).strip()
    match = re.fullmatch(r"(\d{4})M(0[1-9]|1[0-2])", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    match = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", text)
    if match:
        return text
    return None

def parse_monthly_prices_rows(rows: list[tuple]) -> tuple[list[dict], list[dict]]:
    """Parse the World Bank wide matrix: one row per month, one column per commodity."""
    if not rows:
        raise ValueError("World Bank Monthly Prices sheet is empty.")

    header_index = None
    for index, row in enumerate(rows[:15]):
        cells = {str(cell).strip().upper() for cell in row if cell is not None}
        if "GOLD" in cells or "CRUDE_BRENT" in cells or "OIL_BRENT" in cells:
            header_index = index
            break
    if header_index is None:
        # Published workbook currently uses the fifth Excel row as the series header.
        header_index = 4 if len(rows) > 5 else 0

    headers = [str(cell).strip() if cell is not None else "" for cell in rows[header_index]]
    if len(headers) < 2:
        raise ValueError("World Bank monthly series header row was not recognized.")

    unit_row = rows[header_index + 1] if header_index + 1 < len(rows) else ()
    units = {
        headers[index]: str(unit_row[index]).strip()
        for index in range(1, min(len(headers), len(unit_row)))
        if headers[index] and unit_row[index] is not None
    }

    data = []
    for row in rows[header_index + 2:]:
        if not row:
            continue
        period = _period_to_iso(row[0] if len(row) else None)
        if not period:
            continue
        record = {"period": period}
        for index, heading in enumerate(headers[1:], start=1):
            if not heading or index >= len(row):
                continue
            value = row[index]
            if value is None or str(value).strip() in {"", "...", "—", "-"}:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            record[heading] = number
        if len(record) > 1:
            data.append(record)

    metadata = [
        {"series_code": heading, "unit": units.get(heading, "see Description sheet")}
        for heading in headers[1:] if heading
    ]
    if not data:
        raise ValueError("World Bank monthly workbook contained no YYYYMMM observations.")
    return data, metadata

@lru_cache(maxsize=1)
def _monthly_data() -> tuple[list[dict], list[dict], str]:
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
        workbook.close()
        raise ValueError("World Bank monthly workbook does not contain a Monthly Prices sheet.")
    rows = list(workbook[sheet_name].iter_rows(values_only=True))
    workbook.close()
    data, metadata = parse_monthly_prices_rows(rows)
    return data, metadata, url

def fetch_commodity_history(query: str | None = None, limit: int = 60) -> dict:
    rows, metadata, source_url = _monthly_data()
    units = {item["series_code"]: item["unit"] for item in metadata}
    available_codes = list(units)
    if query:
        term = query.strip().casefold()
        selected = [code for code in available_codes if term in code.casefold()]
    else:
        selected = [
            code for code in available_codes
            if any(term in code.casefold() for term in DEFAULT_SERIES)
        ]

    series = []
    for code in selected[:30]:
        points = [
            {"period": row["period"], "price_usd": row[code]}
            for row in rows if code in row
        ]
        series.append({
            "series_code": code,
            "name": code.replace("_", " ").title(),
            "unit": units.get(code, "see Description sheet"),
            "observations": points[-limit:],
        })

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
                "Monthly nominal US-dollar benchmark data; not an intraday quote feed.",
                "The units row is preserved. Consult the workbook Description sheet for benchmark and source definitions.",
                "Dataset attribution and CC BY 4.0 terms must be retained.",
            ],
        ),
        "retrieved_at": utc_now(),
    }

from __future__ import annotations

import os
from datetime import date
from functools import lru_cache

import httpx

from .common import source_record, utc_now

BASE = "https://data.sec.gov"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_UA = os.getenv(
    "AKCA_SEC_USER_AGENT",
    "AKCA Financial Research/0.2 (https://github.com/hakanuste/AKCA)",
)

DURATION_METRICS = {
    "revenue", "net_income", "operating_cash_flow", "capex", "operating_income", "diluted_eps"
}
TAG_MAP = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues", "SalesRevenueNet",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "long_term_debt": ["LongTermDebt"],
    "long_term_debt_current": [
        "LongTermDebtCurrent", "LongTermDebtAndFinanceLeaseObligationsCurrent"
    ],
    "long_term_debt_noncurrent": [
        "LongTermDebtNoncurrent", "LongTermDebtAndFinanceLeaseObligationsNoncurrent"
    ],
    "short_term_borrowings": ["ShortTermBorrowings"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "diluted_eps": ["EarningsPerShareDiluted"],
}

@lru_cache(maxsize=1)
def _ticker_map() -> dict[str, dict]:
    headers = {"User-Agent": DEFAULT_UA, "Accept-Encoding": "gzip, deflate"}
    with httpx.Client(timeout=30, headers=headers) as client:
        response = client.get(COMPANY_TICKERS_URL)
        response.raise_for_status()
        data = response.json()
    result = {}
    for row in data.values():
        ticker = str(row.get("ticker", "")).upper()
        if ticker:
            result[ticker] = {
                "cik": str(row.get("cik_str", "")).zfill(10),
                "title": row.get("title"),
            }
    return result

def _select_entries(companyfacts: dict, metric: str) -> list[dict]:
    facts = companyfacts.get("facts", {})
    is_duration = metric in DURATION_METRICS
    for namespace in ("us-gaap", "dei"):
        tags = facts.get(namespace, {})
        for tag in TAG_MAP.get(metric, []):
            tag_data = tags.get(tag)
            if not tag_data:
                continue
            units = tag_data.get("units") or {}
            unit = next((u for u in ("USD", "USD/shares", "shares") if u in units), None)
            if unit is None and units:
                unit = next(iter(units))
            if unit is None:
                continue
            candidates = []
            for entry in units.get(unit, []):
                if entry.get("form") not in {"10-K", "20-F", "40-F"}:
                    continue
                end = entry.get("end")
                if not end:
                    continue
                if is_duration:
                    start = entry.get("start")
                    if not start:
                        continue
                    try:
                        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
                    except ValueError:
                        continue
                    if not 300 <= days <= 400:
                        continue
                candidates.append(entry)
            # One value per period end; use the latest filing for that period.
            by_end = {}
            for entry in candidates:
                end = entry["end"]
                current = by_end.get(end)
                if current is None or entry.get("filed", "") > current.get("filed", ""):
                    by_end[end] = entry
            if by_end:
                return [
                    {
                        "period_end": end,
                        "value": entry.get("val"),
                        "unit": unit,
                        "form": entry.get("form"),
                        "filed_at": entry.get("filed"),
                        "fy": entry.get("fy"),
                        "fp": entry.get("fp"),
                        "tag": tag,
                        "namespace": namespace,
                    }
                    for end, entry in sorted(by_end.items(), reverse=True)[:5]
                ]
    return []

def _debt_total(financials: dict) -> None:
    if financials.get("long_term_debt"):
        return
    components = [
        financials.get("long_term_debt_current", []),
        financials.get("long_term_debt_noncurrent", []),
        financials.get("short_term_borrowings", []),
    ]
    values: dict[str, float] = {}
    meta: dict[str, dict] = {}
    for series in components:
        for row in series:
            end = row["period_end"]
            try:
                values[end] = values.get(end, 0.0) + float(row["value"])
            except (TypeError, ValueError):
                continue
            meta[end] = row
    if values:
        financials["long_term_debt"] = [
            {**meta[end], "value": value, "tag": "sum_of_debt_components"}
            for end, value in sorted(values.items(), reverse=True)[:5]
        ]

def fetch_company(ticker: str) -> dict:
    symbol = ticker.strip().upper()
    mapping = _ticker_map()
    match = mapping.get(symbol)
    if not match:
        return {
            "available": False,
            "symbol": symbol,
            "reason": "SEC ticker directory does not list this symbol; issuer may be non-US or unsupported.",
            "provider": source_record(
                "sec_edgar", "U.S. SEC EDGAR", "filings_and_xbrl_fundamentals",
                "public_api_no_key", "not_matched",
                "https://www.sec.gov/edgar/sec-api-documentation",
                ["SEC data is limited to entities reporting through EDGAR; it is not a universal global company database."],
            ),
        }

    cik = match["cik"]
    headers = {"User-Agent": DEFAULT_UA, "Accept-Encoding": "gzip, deflate"}
    with httpx.Client(timeout=45, headers=headers) as client:
        facts_response = client.get(f"{BASE}/api/xbrl/companyfacts/CIK{cik}.json")
        facts_response.raise_for_status()
        facts = facts_response.json()
        submissions_response = client.get(f"{BASE}/submissions/CIK{cik}.json")
        submissions_response.raise_for_status()
        submissions = submissions_response.json()

    financials = {metric: _select_entries(facts, metric) for metric in TAG_MAP}
    _debt_total(financials)

    recent = submissions.get("filings", {}).get("recent", {})
    filings = []
    for form, filed, accession, document in zip(
        recent.get("form", []), recent.get("filingDate", []),
        recent.get("accessionNumber", []), recent.get("primaryDocument", []),
    ):
        if form not in {"10-K", "10-Q", "8-K", "20-F", "40-F", "6-K"}:
            continue
        accession_path = accession.replace("-", "")
        filings.append({
            "form": form, "filed_at": filed, "accession": accession,
            "document": document,
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{document}",
        })
        if len(filings) >= 30:
            break

    return {
        "available": True,
        "symbol": symbol,
        "cik": cik,
        "company_name": submissions.get("name") or match.get("title"),
        "sic": submissions.get("sic"),
        "sic_description": submissions.get("sicDescription"),
        "fiscal_year_end": submissions.get("fiscalYearEnd"),
        "financials_annual": financials,
        "recent_filings": filings,
        "provider": source_record(
            "sec_edgar", "U.S. Securities and Exchange Commission EDGAR",
            "company_filings_and_xbrl_fundamentals", "public_api_no_key",
            "retrieved", "https://www.sec.gov/edgar/sec-api-documentation",
            [
                "SEC facts are reported XBRL facts; tag selection and issuer-specific accounting require review.",
                "SEC requests require an identifying User-Agent and must stay below 10 requests per second.",
                "U.S. EDGAR coverage does not imply coverage of BIST or all foreign companies.",
            ],
        ),
        "retrieved_at": utc_now(),
    }

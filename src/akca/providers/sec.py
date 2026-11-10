from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

import httpx

from .common import source_record, utc_now

BASE = "https://data.sec.gov"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_UA = os.getenv(
    "AKCA_SEC_USER_AGENT",
    "AKCA Financial Research/0.1 (https://github.com/hakanuste/AKCA)",
)

TAG_MAP = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
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
    "long_term_debt": [
        "LongTermDebtCurrent",
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "shares_outstanding": [
        "EntityCommonStockSharesOutstanding",
        "CommonStocksIncludingAdditionalPaidInCapital",
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

def _units_for(tag_data: dict) -> tuple[str, list]:
    units = tag_data.get("units") or {}
    if "USD" in units:
        return "USD", units["USD"]
    if "shares" in units:
        return "shares", units["shares"]
    if "USD/shares" in units:
        return "USD/shares", units["USD/shares"]
    if units:
        key = next(iter(units))
        return key, units[key]
    return "", []

def _annual_facts(companyfacts: dict, metric: str) -> list[dict]:
    facts = companyfacts.get("facts", {})
    selected = []
    seen: set[str] = set()
    for namespace in ("us-gaap", "dei"):
        tags = facts.get(namespace, {})
        for tag in TAG_MAP.get(metric, []):
            if tag not in tags:
                continue
            unit, entries = _units_for(tags[tag])
            candidates = []
            for entry in entries:
                form = entry.get("form")
                if form not in {"10-K", "20-F", "40-F"}:
                    continue
                if entry.get("fp") not in {"FY", None}:
                    continue
                start = entry.get("start")
                end = entry.get("end")
                if not end:
                    continue
                if start:
                    try:
                        days = ( __import__("datetime").date.fromisoformat(end)
                               - __import__("datetime").date.fromisoformat(start)).days
                    except ValueError:
                        continue
                    if not 300 <= days <= 400:
                        continue
                candidates.append(entry)
            for entry in sorted(candidates, key=lambda x: (x.get("end", ""), x.get("filed", "")), reverse=True):
                end = entry.get("end")
                if end in seen:
                    continue
                seen.add(end)
                selected.append({
                    "period_end": end,
                    "value": entry.get("val"),
                    "unit": unit,
                    "form": entry.get("form"),
                    "filed_at": entry.get("filed"),
                    "fy": entry.get("fy"),
                    "fp": entry.get("fp"),
                    "tag": tag,
                    "namespace": namespace,
                })
                break
            if selected:
                break
        if selected:
            break
    return sorted(selected, key=lambda x: x["period_end"], reverse=True)[:5]

def fetch_company(ticker: str) -> dict:
    symbol = ticker.strip().upper()
    mapping = _ticker_map()
    match = mapping.get(symbol)
    if not match:
        return {
            "available": False,
            "symbol": symbol,
            "reason": "SEC ticker directory does not list this symbol; it may be a non-US issuer or an unsupported ticker.",
            "provider": source_record(
                "sec_edgar", "U.S. SEC EDGAR", "filings_and_xbrl_fundamentals",
                "public_api_no_key", "not_matched", "https://www.sec.gov/edgar/sec-api-documentation",
                ["SEC data covers U.S. reporting entities in EDGAR; it is not a global company master."],
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

    company_financials = {}
    for metric in TAG_MAP:
        rows = _annual_facts(facts, metric)
        if rows:
            company_financials[metric] = rows

    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    documents = recent.get("primaryDocument", [])
    filings = []
    for form, filed, accession, document in zip(forms, dates, accessions, documents):
        if form not in {"10-K", "10-Q", "8-K", "20-F", "40-F", "6-K"}:
            continue
        accession_path = accession.replace("-", "")
        filings.append({
            "form": form,
            "filed_at": filed,
            "accession": accession,
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
        "financials_annual": company_financials,
        "recent_filings": filings,
        "provider": source_record(
            "sec_edgar", "U.S. Securities and Exchange Commission EDGAR",
            "company_filings_and_xbrl_fundamentals", "public_api_no_key",
            "retrieved", "https://www.sec.gov/edgar/sec-api-documentation",
            [
                "SEC facts reflect filed XBRL data and may not map uniformly across issuers.",
                "SEC requests must identify the application in User-Agent and stay below 10 requests/second.",
                "U.S. filing coverage does not imply coverage of BIST or all foreign securities.",
            ],
        ),
        "retrieved_at": utc_now(),
    }

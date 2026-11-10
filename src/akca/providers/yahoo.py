from __future__ import annotations

from math import isfinite
from typing import Any

import yfinance as yf

from .common import source_record, utc_now

SOURCE_ID = "yahoo_finance_via_yfinance"
SOURCE_URL = "https://finance.yahoo.com/"

def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        if not isfinite(number):
            return None
        return number
    except (TypeError, ValueError):
        return None

def _frame_to_records(frame, limit: int = 8) -> list[dict]:
    if frame is None or getattr(frame, "empty", True):
        return []
    result = []
    columns = list(frame.columns)
    for idx, row in frame.iloc[:, :limit].items():
        record = {"period_end": str(idx.date() if hasattr(idx, "date") else idx)}
        for name in columns:
            value = _safe_float(row.get(name))
            if value is not None:
                record[str(name)] = value
        result.append(record)
    return result

def fetch_equity(symbol: str, history_period: str = "2y") -> dict:
    ticker_symbol = symbol.strip().upper()
    if not ticker_symbol:
        raise ValueError("Sembol boş olamaz.")
    ticker = yf.Ticker(ticker_symbol)
    retrieved_at = utc_now()
    warnings: list[str] = []
    try:
        info = ticker.get_info() or {}
    except Exception as exc:
        info = {}
        warnings.append(f"Şirket profili alınamadı: {type(exc).__name__}")

    try:
        history = ticker.history(period=history_period, auto_adjust=False, actions=True)
    except Exception as exc:
        history = None
        warnings.append(f"Fiyat geçmişi alınamadı: {type(exc).__name__}")

    bars = []
    if history is not None and not history.empty:
        for idx, row in history.iterrows():
            close = _safe_float(row.get("Close"))
            if close is None:
                continue
            bars.append({
                "date": str(idx.date()),
                "open": _safe_float(row.get("Open")),
                "high": _safe_float(row.get("High")),
                "low": _safe_float(row.get("Low")),
                "close": close,
                "adjusted_close": _safe_float(row.get("Adj Close")),
                "volume": _safe_float(row.get("Volume")),
                "dividends": _safe_float(row.get("Dividends")) or 0.0,
                "stock_splits": _safe_float(row.get("Stock Splits")) or 0.0,
            })

    latest = bars[-1] if bars else None
    profile = {
        "symbol": ticker_symbol,
        "name": info.get("longName") or info.get("shortName") or ticker_symbol,
        "exchange": info.get("fullExchangeName") or info.get("exchange"),
        "currency": info.get("currency"),
        "country": info.get("country"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "website": info.get("website"),
        "market_cap": _safe_float(info.get("marketCap")),
        "shares_outstanding": _safe_float(info.get("sharesOutstanding")),
        "trailing_pe": _safe_float(info.get("trailingPE")),
        "forward_pe": _safe_float(info.get("forwardPE")),
        "price_to_sales": _safe_float(info.get("priceToSalesTrailing12Months")),
        "price_to_book": _safe_float(info.get("priceToBook")),
        "enterprise_value": _safe_float(info.get("enterpriseValue")),
        "enterprise_to_ebitda": _safe_float(info.get("enterpriseToEbitda")),
        "profit_margin": _safe_float(info.get("profitMargins")),
        "return_on_equity": _safe_float(info.get("returnOnEquity")),
        "debt_to_equity": _safe_float(info.get("debtToEquity")),
        "beta": _safe_float(info.get("beta")),
        "dividend_yield": _safe_float(info.get("dividendYield")),
        "target_mean_price": _safe_float(info.get("targetMeanPrice")),
        "target_high_price": _safe_float(info.get("targetHighPrice")),
        "target_low_price": _safe_float(info.get("targetLowPrice")),
        "recommendation_key": info.get("recommendationKey"),
        "current_price": (
            latest["close"] if latest else _safe_float(info.get("currentPrice"))
        ),
        "price_timestamp": latest["date"] if latest else None,
        "data_source": SOURCE_ID,
        "retrieved_at": retrieved_at,
    }

    financials: dict[str, list] = {}
    for key, attr in (
        ("income_statement_annual", "income_stmt"),
        ("income_statement_quarterly", "quarterly_income_stmt"),
        ("balance_sheet_annual", "balance_sheet"),
        ("cash_flow_annual", "cashflow"),
    ):
        try:
            financials[key] = _frame_to_records(getattr(ticker, attr, None))
        except Exception as exc:
            financials[key] = []
            warnings.append(f"{key} alınamadı: {type(exc).__name__}")

    return {
        "profile": profile,
        "price_history": bars,
        "financials": financials,
        "provider": source_record(
            SOURCE_ID,
            "Yahoo Finance (yfinance community client)",
            "market_prices_and_supplementary_company_data",
            "unofficial_public_web_interface",
            "retrieved" if bars else "no_price_data",
            SOURCE_URL,
            [
                "Bu resmî Yahoo Finance API'si değildir; yfinance topluluk istemcisi kullanılır.",
                "Veri gecikmeli, eksik veya değişebilir; üretim/yeniden dağıtım lisansı varsayılmaz.",
                "Mali tablo ve analist tahminleri ikincil kanıttır; resmî dosyalardan teyit edilmelidir.",
            ],
        ),
        "warnings": warnings,
    }

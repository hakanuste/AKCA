from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from math import isfinite
from typing import Any

import yfinance as yf

from .common import source_record, utc_now

GLOBAL_INDICES = {
    "BIST 100": "XU100.IS",
    "BIST 30": "XU030.IS",
    "S&P 500": "^GSPC",
    "NASDAQ Composite": "^IXIC",
    "Dow Jones Industrial": "^DJI",
    "Euro Stoxx 50": "^STOXX50E",
    "DAX": "^GDAXI",
    "FTSE 100": "^FTSE",
    "Nikkei 225": "^N225",
    "Hang Seng": "^HSI",
    "Shanghai Composite": "000001.SS",
    "BSE Sensex": "^BSESN",
}
FX_MARKETS = {
    "USD/TRY": "USDTRY=X",
    "EUR/TRY": "EURTRY=X",
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "Dollar Index": "DX-Y.NYB",
}
COMMODITY_FUTURES = {
    "Gold futures (COMEX)": "GC=F",
    "Silver futures (COMEX)": "SI=F",
    "Copper futures (COMEX)": "HG=F",
    "WTI crude oil futures": "CL=F",
    "Brent crude oil futures": "BZ=F",
    "Natural gas futures (Henry Hub)": "NG=F",
    "Corn futures": "ZC=F",
    "Wheat futures": "ZW=F",
    "Soybean futures": "ZS=F",
    "Coffee futures": "KC=F",
    "Sugar futures": "SB=F",
    "Cocoa futures": "CC=F",
}

def fetch_quote(symbol: str, period: str = "6mo", name: str | None = None) -> dict:
    ticker_symbol = symbol.strip().upper()
    if not ticker_symbol:
        raise ValueError("Piyasa sembolü boş olamaz.")
    ticker = yf.Ticker(ticker_symbol)
    history = ticker.history(period=period, auto_adjust=False, actions=False)
    bars = []
    if history is not None and not history.empty:
        for idx, row in history.iterrows():
            try:
                close = float(row["Close"])
            except (KeyError, TypeError, ValueError):
                continue
            if close <= 0:
                continue
            bars.append({
                "date": str(idx.date() if hasattr(idx, "date") else idx),
                "open": _number(row.get("Open")),
                "high": _number(row.get("High")),
                "low": _number(row.get("Low")),
                "close": close,
                "volume": _number(row.get("Volume")),
            })
    if not bars:
        return {
            "symbol": ticker_symbol,
            "name": name or ticker_symbol,
            "status": "no_data",
            "last_price": None,
            "currency": None,
            "source": "yahoo_finance_via_yfinance",
            "retrieved_at": utc_now(),
        }
    last = bars[-1]
    previous = bars[-2] if len(bars) > 1 else None
    currency = None
    try:
        fast_info = ticker.fast_info
        currency = fast_info.get("currency")
    except Exception:
        currency = None
    return {
        "symbol": ticker_symbol,
        "name": name or ticker_symbol,
        "status": "ok",
        "last_price": last["close"],
        "previous_close": previous["close"] if previous else None,
        "change_pct": (
            (last["close"] / previous["close"] - 1) * 100
            if previous and previous["close"] else None
        ),
        "currency": currency,
        "as_of": last["date"],
        "history_observations": len(bars),
        "history": bars,
        "source": "yahoo_finance_via_yfinance",
        "retrieved_at": utc_now(),
    }

def _number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None

def fetch_market_group(group: str = "all", period: str = "6mo") -> dict:
    groups = {
        "indices": GLOBAL_INDICES,
        "fx": FX_MARKETS,
        "commodities": COMMODITY_FUTURES,
    }
    if group == "all":
        instruments = {**GLOBAL_INDICES, **FX_MARKETS, **COMMODITY_FUTURES}
    elif group in groups:
        instruments = groups[group]
    else:
        raise ValueError("group indices, fx, commodities veya all olmalı.")

    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(fetch_quote, symbol, period, name): (name, symbol)
            for name, symbol in instruments.items()
        }
        for future in as_completed(futures):
            name, symbol = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append({
                    "name": name, "symbol": symbol,
                    "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                })
    ordered = {row["symbol"]: row for row in results}
    results = [
        ordered.get(symbol, {
            "name": name, "symbol": symbol, "status": "provider_error",
            "last_price": None, "currency": None,
        })
        for name, symbol in instruments.items()
    ]
    return {
        "group": group,
        "period": period,
        "results": results,
        "errors": errors,
        "provider": source_record(
            "yahoo_finance_via_yfinance",
            "Yahoo Finance (community yfinance client)",
            "indicative_public_market_prices",
            "unofficial_public_web_interface",
            "retrieved" if results else "no_data",
            "https://finance.yahoo.com/",
            [
                "Not an official Yahoo Finance API and not a licensed Borsa İstanbul feed.",
                "Prices can be delayed, missing or unavailable; no real-time entitlement is implied.",
                "BIST exchange data redistribution and non-display usage require the appropriate Borsa İstanbul/vendor agreement.",
                "Commodity futures are continuous front-contract representations; roll yield, expiry and contract specifications must be checked.",
            ],
        ),
        "retrieved_at": utc_now(),
    }

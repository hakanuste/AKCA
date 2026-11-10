from __future__ import annotations

from datetime import date

from ..db import connect
from ..providers.yahoo import fetch_equity

def add_ipo(
    symbol: str, company_name: str, offer_date: str, offer_price: float,
    offer_currency: str, source_url: str, source_name: str,
    verified: bool = False, shares_offered: float | None = None, notes: str | None = None,
) -> None:
    date.fromisoformat(offer_date)
    if offer_price <= 0:
        raise ValueError("Halka arz fiyatı sıfırdan büyük olmalı.")
    if not source_url.startswith(("https://", "http://")):
        raise ValueError("Kaynak URL'si HTTP/HTTPS olmalı.")
    conn = connect()
    conn.execute(
        """
        INSERT OR REPLACE INTO ipo_records(
            symbol,company_name,offer_date,offer_price,offer_currency,
            shares_offered,source_url,source_name,verified,notes
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            symbol.upper(), company_name, offer_date, offer_price, offer_currency.upper(),
            shares_offered, source_url, source_name, int(verified), notes,
        ),
    )
    conn.commit()
    conn.close()

def ipo_performance(symbol: str) -> dict:
    conn = connect()
    record = conn.execute("SELECT * FROM ipo_records WHERE symbol=?", (symbol.upper(),)).fetchone()
    conn.close()
    if not record:
        raise KeyError(f"Halka arz kaydı bulunamadı: {symbol}")
    price = fetch_equity(symbol, history_period="5y")
    current = price["profile"].get("current_price")
    currency = (price["profile"].get("currency") or "").upper()
    offer_currency = record["offer_currency"].upper()
    compatible = currency == offer_currency
    nominal_return = (
        (current / record["offer_price"] - 1) * 100
        if current is not None and compatible else None
    )
    return {
        "symbol": symbol.upper(),
        "company_name": record["company_name"],
        "offer_date": record["offer_date"],
        "offer_price": record["offer_price"],
        "offer_currency": offer_currency,
        "current_price": current,
        "current_currency": currency,
        "offer_to_current_return_pct": nominal_return,
        "offer_price_source": record["source_url"],
        "offer_data_verified": bool(record["verified"]),
        "price_source": price.get("provider"),
        "warnings": (
            [] if compatible else ["Halka arz ve piyasa fiyat para birimleri eşleşmiyor; getiri hesaplanmadı."]
        ) + (
            [] if record["verified"] else ["Halka arz fiyatı kaydı doğrulanmamış; getiri yalnızca ön izleme."]
        ),
    }

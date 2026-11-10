from __future__ import annotations

from datetime import date, timedelta

from ..db import connect
from ..providers.fred import fetch_macro
from ..providers.yahoo import fetch_equity

def _nearest_value(rows: list[dict], target: date, key: str) -> float | None:
    available = []
    for row in rows:
        try:
            observed = date.fromisoformat(row["date"])
            value = row.get(key)
            if value is not None and observed <= target:
                available.append((observed, float(value)))
        except (ValueError, TypeError, KeyError):
            continue
    return max(available, default=(None, None), key=lambda x: x[0] or date.min)[1]

def _cpi_on_or_before(observations: list[dict], target: date) -> float | None:
    points = []
    for row in observations:
        try:
            observed = date.fromisoformat(row["date"])
            if observed <= target:
                points.append((observed, float(row["value"])))
        except (ValueError, TypeError, KeyError):
            continue
    return max(points, default=(None, None), key=lambda x: x[0] or date.min)[1]

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

    data = fetch_equity(symbol, history_period="5y")
    profile = data["profile"]
    bars = data.get("price_history", [])
    current = profile.get("current_price")
    current_currency = (profile.get("currency") or "").upper()
    offer_currency = record["offer_currency"].upper()
    offer_day = date.fromisoformat(record["offer_date"])
    today = date.today()

    if current is None or not bars:
        raise ValueError("Güncel piyasa fiyatı veya geçmiş fiyat serisi alınamadı.")
    if offer_day > today:
        raise ValueError("Halka arz tarihi gelecekte görünüyor.")

    split_factor = 1.0
    dividend_cash_per_original_share = 0.0
    actions_complete = True
    first_bar = date.fromisoformat(bars[0]["date"])
    if offer_day < first_bar:
        actions_complete = False

    for bar in bars:
        bar_day = date.fromisoformat(bar["date"])
        if bar_day <= offer_day:
            continue
        split = float(bar.get("stock_splits") or 0)
        if split > 0:
            split_factor *= split
        dividend = float(bar.get("dividends") or 0)
        if dividend > 0:
            dividend_cash_per_original_share += dividend * split_factor

    current_total_wealth_local = float(current) * split_factor + dividend_cash_per_original_share
    offer_price = float(record["offer_price"])
    same_currency = offer_currency == current_currency
    local_price_return = (
        (float(current) * split_factor / offer_price - 1) * 100
        if same_currency else None
    )
    local_total_return = (
        (current_total_wealth_local / offer_price - 1) * 100
        if same_currency and actions_complete else None
    )

    usd_offer = usd_current = None
    usd_price_return = usd_total_return = None
    fx_note = None
    if offer_currency == "USD" and current_currency == "USD":
        usd_offer = offer_price
        usd_current = current_total_wealth_local
        usd_price_return = local_price_return
        usd_total_return = local_total_return
        fx_note = "Halka arz ve güncel fiyat USD cinsinden."
    elif offer_currency == "TRY" and current_currency == "TRY":
        fx = fetch_equity("USDTRY=X", history_period="5y")
        fx_bars = fx.get("price_history", [])
        offer_fx = _nearest_value(fx_bars, offer_day, "close")
        current_fx = float(fx_bars[-1]["close"]) if fx_bars else None
        if offer_fx and current_fx and offer_fx > 0 and current_fx > 0:
            usd_offer = offer_price / offer_fx
            usd_current = current_total_wealth_local / current_fx
            usd_price_now = float(current) * split_factor / current_fx
            usd_price_return = (usd_price_now / usd_offer - 1) * 100
            usd_total_return = (usd_current / usd_offer - 1) * 100 if actions_complete else None
            fx_note = "Halka arz ve güncel toplam değer, ilgili tarihlerdeki USD/TRY kuru ile USD'ye çevrildi."
        else:
            fx_note = "Halka arz veya güncel tarih için USD/TRY kuru bulunamadı."
    else:
        fx_note = "USD performansı yalnızca TRY veya USD kotasyonlarında hesaplanır; para birimi eşleşmedi."

    macro = fetch_macro(["CPIAUCSL"], observation_count=180)
    cpi_rows = (
        (macro.get("series") or [{}])[0].get("observations", [])
        if macro.get("status") != "not_configured" else []
    )
    offer_cpi = _cpi_on_or_before(cpi_rows, offer_day) if cpi_rows else None
    current_cpi = float(cpi_rows[-1]["value"]) if cpi_rows else None
    real_usd_return = (
        ((1 + usd_total_return / 100) / (current_cpi / offer_cpi) - 1) * 100
        if usd_total_return is not None and offer_cpi and current_cpi and offer_cpi > 0 else None
    )

    warnings = []
    if not bool(record["verified"]):
        warnings.append("Halka arz fiyatı kaydı doğrulanmamış; performans yalnızca ön incelemedir.")
    if not actions_complete:
        warnings.append("Halka arz tarihi fiyat geçmişinin dışında; bölünme/temettü aksiyon kapsamı eksik.")
    if not same_currency:
        warnings.append("Halka arz ve güncel kotasyon para birimleri eşleşmiyor; yerel getiri hesaplanmadı.")
    if usd_total_return is None:
        warnings.append("Dolar bazlı toplam getiri hesaplanamadı.")
    if real_usd_return is None:
        warnings.append("FRED CPI anahtarı/verisi olmadığı veya seri dönemi eşleşmediği için reel USD getirisi hesaplanmadı.")

    return {
        "symbol": symbol.upper(),
        "company_name": record["company_name"],
        "offer_date": record["offer_date"],
        "offer_price": offer_price,
        "offer_currency": offer_currency,
        "current_price": current,
        "current_currency": current_currency,
        "current_as_of": profile.get("price_timestamp"),
        "offer_to_current_price_return_pct": local_price_return,
        "offer_to_current_total_return_pct": local_total_return,
        "offer_to_current_return_pct": local_total_return if local_total_return is not None else local_price_return,
        "usd_offer_price": usd_offer,
        "usd_current_total_value": usd_current,
        "usd_total_return_pct": usd_total_return,
        "real_usd_total_return_pct": real_usd_return,
        "cumulative_split_factor": split_factor,
        "dividends_per_original_share": dividend_cash_per_original_share,
        "corporate_action_coverage_complete": actions_complete,
        "offer_price_source": record["source_url"],
        "offer_source_name": record["source_name"],
        "offer_data_verified": bool(record["verified"]),
        "fx_method": fx_note,
        "inflation_source": macro.get("provider"),
        "price_source": data.get("provider"),
        "warnings": warnings,
    }

def recent_ipos(days: int = 730, max_items: int = 50) -> dict:
    days = min(max(int(days), 1), 3650)
    since = (date.today() - timedelta(days=days)).isoformat()
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM ipo_records WHERE offer_date>=? ORDER BY offer_date DESC LIMIT ?",
        (since, min(max_items, 100)),
    ).fetchall()
    conn.close()
    return {
        "window_days": days,
        "since": since,
        "count": len(rows),
        "ipos": [
            {
                "symbol": row["symbol"], "company_name": row["company_name"],
                "offer_date": row["offer_date"], "offer_price": row["offer_price"],
                "offer_currency": row["offer_currency"], "source_url": row["source_url"],
                "verified": bool(row["verified"]),
            }
            for row in rows
        ],
        "note": "Halka arz listesi AKÇA'nın doğrulanmış/kaydedilmiş kayıtlarından oluşur; eksiksiz piyasa listesi olduğu iddia edilmez.",
    }

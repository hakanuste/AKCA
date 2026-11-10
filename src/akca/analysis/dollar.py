from __future__ import annotations

from datetime import date, timedelta

from ..providers.yahoo import fetch_equity
from ..providers.fred import fetch_macro
from .technical import analyze_price_history

def _nearest_on_or_before(rows: list[dict], target: date, field: str) -> float | None:
    candidates = []
    for row in rows:
        try:
            d = date.fromisoformat(row["date"])
            value = row.get(field) or row.get("close")
            if d <= target and value is not None:
                candidates.append((d, float(value)))
        except (ValueError, TypeError, KeyError):
            continue
    return max(candidates, default=(None, None), key=lambda x: x[0] or date.min)[1]

def dollar_performance(symbol: str) -> dict:
    equity = fetch_equity(symbol, history_period="10y")
    profile = equity["profile"]
    bars = equity.get("price_history", [])
    if len(bars) < 2:
        raise ValueError("Dolar bazlı performans için yeterli fiyat geçmişi yok.")
    currency = (profile.get("currency") or "").upper()
    fx_bars = []
    fx_note = None
    if currency == "TRY":
        fx = fetch_equity("USDTRY=X", history_period="10y")
        fx_bars = fx.get("price_history", [])
        if not fx_bars:
            raise ValueError("USD/TRY geçmişi alınamadı; dolar getirisi hesaplanmadı.")
        fx_note = "TRY fiyatı, aynı tarihteki USD/TRY kapanışıyla bölünerek dolara çevrildi."
    elif currency == "USD":
        fx_note = "Fiyat zaten USD cinsinden; döviz dönüşümü uygulanmadı."
    else:
        raise ValueError(
            f"Bu ilk sürüm yalnızca USD veya TRY kotasyonlarında dolar performansını hesaplıyor; bulunan para birimi: {currency or 'bilinmiyor'}."
        )

    usd_bars = []
    for row in bars:
        local_price = row.get("adjusted_close") or row.get("close")
        if local_price is None:
            continue
        if currency == "TRY":
            try:
                fx_rate = _nearest_on_or_before(fx_bars, date.fromisoformat(row["date"]), "close")
            except ValueError:
                fx_rate = None
            if not fx_rate or fx_rate <= 0:
                continue
            usd_price = float(local_price) / fx_rate
        else:
            usd_price = float(local_price)
        usd_bars.append({
            "date": row["date"], "close": usd_price, "adjusted_close": usd_price,
            "volume": row.get("volume"),
        })
    if len(usd_bars) < 2:
        raise ValueError("FX eşlemesinden sonra yeterli ortak fiyat geçmişi kalmadı.")

    last_date = date.fromisoformat(usd_bars[-1]["date"])
    last_price = usd_bars[-1]["close"]
    horizons = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "3y": 1095, "5y": 1825}
    returns = {}
    for label, days in horizons.items():
        start = _nearest_on_or_before(usd_bars, last_date - timedelta(days=days), "close")
        returns[label] = (last_price / start - 1) * 100 if start else None
    values = [r["close"] for r in usd_bars]
    real_returns = {}
    macro = fetch_macro(["CPIAUCSL"], observation_count=180)
    cpi = (macro.get("series") or [{}])[0].get("observations", []) if macro.get("status") != "not_configured" else []
    for label, days in horizons.items():
        target_date = last_date - timedelta(days=days)
        historical_cpi = _nearest_on_or_before(
            [{"date": row["date"], "close": row["value"]} for row in cpi],
            target_date, "close",
        ) if cpi else None
        current_cpi = cpi[-1]["value"] if cpi else None
        nominal = returns[label]
        real_returns[label] = (
            ((1 + nominal / 100) / (current_cpi / historical_cpi) - 1) * 100
            if nominal is not None and current_cpi and historical_cpi else None
        )
    technical = analyze_price_history(usd_bars)
    return {
        "symbol": symbol.upper(),
        "company_name": profile.get("name"),
        "currency_original": currency,
        "last_usd_price": last_price,
        "as_of": usd_bars[-1]["date"],
        "nominal_usd_returns_pct": returns,
        "real_usd_returns_pct": real_returns,
        "historical_usd_high": max(values),
        "historical_usd_low": min(values),
        "technical_in_usd": technical,
        "fx_method": fx_note,
        "dividend_split_adjustment": "Yahoo adjusted close kullanıldıysa temettü ve bölünmeler düzeltilmiş seridir; adjusted close yoksa close kullanılır.",
        "inflation_adjustment": "FRED CPIAUCSL verisi ve API anahtarı mevcutsa; aksi halde reel USD getirisi null kalır.",
        "data_source": equity.get("provider"),
        "fx_source": "Yahoo Finance USDTRY=X" if currency == "TRY" else None,
        "macro_data_status": macro.get("status"),
        "warnings": equity.get("warnings", []) + (
            ["FRED CPI anahtarı yok veya veri dönmedi; reel USD getirisi hesaplanmadı."]
            if not cpi else []
        ),
    }

from __future__ import annotations

from ..providers.yahoo import fetch_equity

def analyze_portfolio(positions: list[dict], base_currency: str = "USD") -> dict:
    if not positions:
        raise ValueError("Portföyde en az bir pozisyon olmalı.")
    rows = []
    same_currency = False
    total_value = 0.0
    for position in positions:
        symbol = position["symbol"].upper()
        data = fetch_equity(symbol, history_period="1y")
        profile = data["profile"]
        price = profile.get("current_price")
        if price is None:
            rows.append({
                "symbol": symbol, "status": "missing_price",
                "note": "Piyasa fiyatı alınamadı; toplam portföy ağırlığına dahil edilmedi.",
            })
            continue
        quantity = float(position["quantity"])
        value = price * quantity
        total_value += value
        rows.append({
            "symbol": symbol, "status": "priced", "quantity": quantity,
            "price": price, "currency": profile.get("currency"),
            "market_value": value, "exchange": profile.get("exchange"),
            "history": data.get("price_history", []),
        })
    priced = [r for r in rows if r.get("status") == "priced"]
    currencies = {r.get("currency") for r in priced if r.get("currency")}
    same_currency = (
        len(currencies) == 1
        and all(r.get("currency") for r in priced)
        and len(priced) == len(positions)
    )
    if same_currency and total_value > 0:
        for row in rows:
            row["weight_pct"] = (
                row["market_value"] / total_value * 100
                if row.get("market_value") is not None else None
            )
    else:
        for row in rows:
            row["weight_pct"] = None
    concentration = (
        sum((r.get("weight_pct") or 0) ** 2 for r in priced)
        if same_currency and total_value > 0 else None
    )
    warnings = []
    if len(currencies) > 1:
        warnings.append("Birden fazla para birimi bulundu. FX dönüşümü yapılmadı; toplam piyasa değeri karşılaştırılabilir değildir.")
    elif priced and not same_currency:
        warnings.append("En az bir pozisyonun fiyatı veya para birimi eksik. Portföy ağırlıkları ve konsantrasyonu hesaplanmadı.")
    if currencies == {base_currency.upper()}:
        pass
    elif same_currency:
        warnings.append(
            f"Pozisyonlar {next(iter(currencies))} cinsinden hesaplandı; istenen baz para birimi {base_currency.upper()} olduğu halde FX dönüşümü yapılmadı."
        )
    if len(priced) < len(positions):
        warnings.append("Bazı pozisyonların fiyatı alınamadığından portföy kapsamı eksik.")
    if any((r.get("weight_pct") or 0) > 35 for r in priced):
        warnings.append("Tek varlıkta %35 üzerinde konsantrasyon var.")
    # Portfolio historical returns require common dates and currency conversion.
    return {
        "base_currency_requested": base_currency.upper(),
        "priced_positions": len(priced),
        "total_positions": len(positions),
        "market_value_unconverted": total_value if same_currency else None,
        "currency_set": sorted(currencies),
        "herfindahl_index": concentration / 10000 if concentration is not None else None,
        "positions": [{k: v for k, v in r.items() if k != "history"} for r in rows],
        "warnings": warnings + (
            [] if same_currency else ["Para birimleri tekilleştirilemedi. FX dönüşümü yapılmadığından portföy ağırlığı ve konsantrasyon hesaplanmadı."]
        ) + [
            "Bu ilk sürüm portföy piyasa değerlerini pozisyon para biriminde hesaplar; çoklu para birimini tek baz para birimine çevirmeden toplamaz.",
            "Korelasyon, portföy VaR ve stres testi için ortak tarihli fiyat serileri ve FX serileri gerekir; eksik seriyle hesap yapılmaz.",
        ],
    }

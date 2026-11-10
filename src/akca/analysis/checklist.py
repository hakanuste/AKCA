from __future__ import annotations

CHECKLIST = [
    "Ticker/şirket kimliğini doğrula",
    "Finansal tablo analiz yöntemini doğrula",
    "Fiyat/getiri hesaplama yöntemini doğrula",
    "Son finansal tabloları analiz et",
    "Güncel fiyat ve sektör bilgisini doğrula",
    "Güncel değerleme çarpanlarını hesapla",
    "Dönemsel hisse getirilerini hesapla",
    "Çeyreklik performans serisini incele",
    "Sektör emsal çarpanlarıyla karşılaştır",
    "Güncel aracı kurum değerlendirmelerini incele",
    "Şirkete özgü aracı kurum raporlarını incele",
    "Son KAP/EDGAR bildirimlerini incele",
    "Son yıllık faaliyet raporunu incele",
    "Revize beklenti ve tahminleri incele",
    "Dokuz aylık yatırımcı sunumunu/notunu incele",
    "Yönetim açıklamalarını incele",
    "Rehberlik ve görünümü incele",
    "Şirket yapısı ve bağlı ortaklıkları incele",
    "Önemli gelişmeleri/katalizörleri incele",
    "Kredi derecelendirme duyurularını incele",
    "Finansal özet ve ortaklık yapısını doğrula",
    "Bir yıllık tarihsel çarpan aralığını hesapla",
    "Temettü verimini hesapla",
    "Hesaplama ortamını ve birimleri doğrula",
    "Temettü verisi metodolojisini kontrol et",
    "Teknik göstergeler için fiyat serisini doğrula",
    "Temettü geçmişini incele",
    "Teknik görünümü değerlendir",
    "Analist hedef fiyat verisini doğrula",
    "Hedef fiyat geçmişini yapılandır",
    "Güncel analist hedeflerini incele",
    "Bağlı ortaklık değerini incele",
    "Endekse göre performansı karşılaştır",
]

def build_company_checklist(report: dict, broker_records_count: int = 0) -> list[dict]:
    profile = report.get("profile", {})
    fundamentals = report.get("fundamentals", {})
    metrics = fundamentals.get("metrics", {})
    technical = report.get("technical", {})
    filings = report.get("filings", [])
    completeness = report.get("completeness", {})
    price_history_ok = technical.get("observations", 0) >= 200
    sec_filings = bool(filings)
    is_bist = report.get("market_region") == "BIST"
    has_company_financials = bool(metrics.get("revenue", {}).get("latest") is not None)
    has_current_price = profile.get("current_price") is not None
    has_valuation = any(
        report.get("valuation", {}).get(key) is not None
        for key in ("trailing_pe_provider", "forward_pe_provider", "market_cap_to_revenue")
    )
    has_returns = bool(technical.get("returns_pct"))
    has_target = profile.get("target_mean_price") is not None
    has_dividend = profile.get("dividend_yield") is not None
    checks = [
        "complete", "complete", "complete",
        "complete" if has_company_financials else "missing",
        "complete" if has_current_price else "missing",
        "partial" if has_valuation else "missing",
        "complete" if has_returns else "missing",
        "partial" if price_history_ok else "missing",
        "manual_required",
        "complete" if broker_records_count else "manual_required",
        "complete" if broker_records_count else "manual_required",
        "manual_required" if is_bist else ("complete" if sec_filings else "manual_required"),
        "manual_required" if is_bist else ("partial" if sec_filings else "manual_required"),
        "manual_required",
        "manual_required",
        "manual_required" if is_bist else ("partial" if sec_filings else "manual_required"),
        "manual_required",
        "manual_required",
        "partial" if sec_filings else "manual_required",
        "manual_required",
        "partial" if profile.get("market_cap") is not None else "missing",
        "not_available",
        "partial" if has_dividend else "missing",
        "complete",
        "partial" if price_history_ok else "missing",
        "partial" if any((bar.get("dividends") or 0) > 0 for bar in report.get("price_history", [])) else "manual_required",
        "partial" if price_history_ok else "missing",
        "partial" if has_target else "manual_required",
        "manual_required",
        "partial" if has_target else "manual_required",
        "not_available",
        "manual_required",
    ]
    return [
        {"step": index + 1, "task": task, "status": checks[index]}
        for index, task in enumerate(CHECKLIST)
    ]

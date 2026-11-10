from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ..db import connect
from ..providers.sec import fetch_company
from ..providers.yahoo import fetch_equity
from .fundamentals import analyze_fundamentals
from .technical import analyze_price_history
from .checklist import build_company_checklist
from .institutional import broker_consensus

METHODOLOGY_VERSION = "akca-research-0.2.0"

def _risk_review(fundamentals: dict, technical: dict, profile: dict) -> list[dict]:
    flags = []
    risk = technical.get("risk", {})
    derived = fundamentals.get("derived", {})
    if risk.get("annualized_volatility_pct") is not None and risk["annualized_volatility_pct"] > 55:
        flags.append({"severity": "high", "code": "HIGH_VOLATILITY", "message": "Yıllıklandırılmış tarihsel oynaklık %55'in üzerinde."})
    if risk.get("max_drawdown_2y_pct") is not None and risk["max_drawdown_2y_pct"] < -40:
        flags.append({"severity": "high", "code": "DEEP_DRAWDOWN", "message": "Son iki yıllık pencerede %40'tan derin tepe-dip kaybı var."})
    if derived.get("debt_to_equity") is not None and derived["debt_to_equity"] > 3:
        flags.append({"severity": "high", "code": "HIGH_LEVERAGE", "message": "Borç/özsermaye oranı 3x üzerinde; sektör ve muhasebe kapsamıyla kontrol edilmeli."})
    if derived.get("free_cash_flow") is not None and derived["free_cash_flow"] < 0:
        flags.append({"severity": "medium", "code": "NEGATIVE_FCF", "message": "Son yıllık serbest nakit akışı negatif."})
    if fundamentals.get("status") != "ok":
        flags.append({"severity": "medium", "code": "FUNDAMENTAL_DATA_GAP", "message": "Temel finansal veri seti kısmi."})
    if technical.get("status") != "ok":
        flags.append({"severity": "medium", "code": "TECHNICAL_HISTORY_GAP", "message": "Teknik gösterge üretmek için fiyat geçmişi yetersiz."})
    if profile.get("market_cap") is None:
        flags.append({"severity": "medium", "code": "MARKET_CAP_MISSING", "message": "Piyasa değeri doğrulanamadı."})
    return flags

def _valuation(profile: dict, fundamentals: dict) -> dict:
    market_cap = profile.get("market_cap")
    metrics = fundamentals.get("metrics", {})
    revenue = (metrics.get("revenue") or {}).get("latest")
    net_income = (metrics.get("net_income") or {}).get("latest")
    fcf = fundamentals.get("derived", {}).get("free_cash_flow")
    return {
        "market_cap": market_cap,
        "trailing_pe_provider": profile.get("trailing_pe"),
        "forward_pe_provider": profile.get("forward_pe"),
        "price_to_sales_provider": profile.get("price_to_sales"),
        "price_to_book_provider": profile.get("price_to_book"),
        "enterprise_to_ebitda_provider": profile.get("enterprise_to_ebitda"),
        "market_cap_to_revenue": market_cap / revenue if market_cap is not None and revenue not in (None, 0) else None,
        "market_cap_to_net_income": market_cap / net_income if market_cap is not None and net_income not in (None, 0) else None,
        "free_cash_flow_yield_pct": fcf / market_cap * 100 if fcf is not None and market_cap not in (None, 0) else None,
        "note": "Sağlayıcı çarpanları kaynağıyla birlikte ikincil piyasa verisidir. Fiyat tarihi, para birimi, pay adedi ve finansal dönem tutarlılığı teyit edilmeden karşılaştırma yapılmamalıdır.",
    }

def _recommendation_gate(profile: dict, fundamentals: dict, technical: dict, risk_flags: list) -> dict:
    gaps = []
    if profile.get("current_price") is None:
        gaps.append("Güncel/son kapanış fiyatı yok.")
    if technical.get("observations", 0) < 200:
        gaps.append("En az 200 işlem günlük fiyat geçmişi yok.")
    metrics = fundamentals.get("metrics", {})
    if metrics.get("revenue", {}).get("latest") is None:
        gaps.append("Gelir finansalı bulunamadı.")
    if metrics.get("net_income", {}).get("latest") is None:
        gaps.append("Net kâr finansalı bulunamadı.")
    if not profile.get("currency"):
        gaps.append("Fiyat para birimi doğrulanamadı.")
    high = [flag for flag in risk_flags if flag["severity"] == "high"]
    if gaps or high:
        return {
            "action": "BEKLE",
            "status": "insufficient_or_high_risk",
            "confidence": 0.25,
            "reasons": gaps + [f"Yüksek risk: {flag['message']}" for flag in high],
            "calibration": "not_backtested",
        }
    return {
        "action": "BEKLE",
        "status": "research_ready_no_calibrated_signal",
        "confidence": 0.35,
        "reasons": [
            "Veri seti ilk değerlendirme için yeterli; ancak karar eşikleri ve ağırlıklar tarihsel, maliyet dahil geriye dönük testle kalibre edilmemiş.",
            "Kalibre edilmemiş sinyal üzerinden AL/TUT/AZALT/SAT üretmek güvenilir olmayacağından ilk sürüm korumacı BEKLE çıktısı veriyor.",
        ],
        "calibration": "not_backtested",
    }

def _cache_get(symbol: str, ttl_minutes: int = 15):
    conn = connect()
    row = conn.execute("SELECT * FROM market_cache WHERE cache_key=?", (f"research:{symbol}",)).fetchone()
    conn.close()
    if not row:
        return None
    try:
        expires = datetime.fromisoformat(row["expires_at"])
        if expires <= datetime.now(UTC):
            return None
        return json.loads(row["payload_json"])
    except (ValueError, json.JSONDecodeError):
        return None

def _cache_put(symbol: str, payload: dict, source: str = "SEC+Yahoo"):
    now = datetime.now(UTC)
    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO market_cache(cache_key,payload_json,source,retrieved_at,expires_at) VALUES(?,?,?,?,?)",
        (f"research:{symbol}", json.dumps(payload, ensure_ascii=False, default=str),
         source, now.isoformat(), (now + timedelta(minutes=15)).isoformat()),
    )
    conn.commit()
    conn.close()


def _fetch_market(symbol: str) -> dict:
    primary = fetch_equity(symbol)
    history = primary.get("price_history", [])
    if history or symbol.endswith(".IS") or any(ch in symbol for ch in "^=$"):
        return primary
    # BIST listings are commonly discoverable on public market-data clients with .IS suffix.
    # This is an indicative fallback, not a licensed exchange feed.
    fallback = fetch_equity(symbol + ".IS")
    if fallback.get("price_history"):
        fallback.setdefault("warnings", []).append(
            "Sembol .IS uzantısıyla bulundu. BIST fiyatı gösterge amaçlı ikincil sağlayıcıdan alınmıştır; lisanslı BIST veri akışı değildir."
        )
        return fallback
    return primary

def _sec_not_applicable(symbol: str) -> dict:
    return {
        "available": False,
        "symbol": symbol,
        "reason": "Bu sembol BIST/ABD dışı veya SEC ticker eşleşmesi bulunmayan bir ihraççı olarak değerlendirildi. Türkiye şirket bildirimleri için KAP/MKK veri servisi bağlantısı gerekir.",
        "provider": {
            "source_id": "kap_mkk_api",
            "source_name": "KAP / MKK API Portal",
            "status": "credentials_and_product_access_required",
            "url": "https://apiportal.mkk.com.tr/",
            "limitations": [
                "KAP veri yayın servisleri için MKK API Portal kaydı, API anahtarı ve ilgili veri ürününe erişim gerekir.",
                "Borsa İstanbul fiyat akışı için ayrıca lisanslı veri dağıtıcısı sözleşmesi gerekir.",
            ],
        },
    }

def run_company_research(symbol: str, force_refresh: bool = False) -> dict:
    symbol = symbol.strip().upper()
    if not symbol or len(symbol) > 40:
        raise ValueError("Geçerli bir şirket sembolü girilmeli.")
    if not force_refresh:
        cached = _cache_get(symbol)
        if cached:
            cached["cache"] = "hit"
            return cached

    results = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_fetch_market, symbol): "market",
            pool.submit(_sec_not_applicable, symbol) if symbol.endswith(".IS") else pool.submit(fetch_company, symbol): "sec",
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                errors[name] = f"{type(exc).__name__}: {str(exc)[:300]}"

    market = results.get("market", {})
    sec = results.get("sec", {"available": False, "reason": errors.get("sec")})
    profile = market.get("profile", {"symbol": symbol, "name": symbol})
    history = market.get("price_history", [])
    resolved_symbol = profile.get("symbol") or symbol
    if str(resolved_symbol).endswith(".IS"):
        sec = _sec_not_applicable(str(resolved_symbol))
    technical = analyze_price_history(history)
    fundamentals = analyze_fundamentals(sec, market)
    valuation = _valuation(profile, fundamentals)
    risk_flags = _risk_review(fundamentals, technical, profile)
    recommendation = _recommendation_gate(profile, fundamentals, technical, risk_flags)
    is_bist = str(resolved_symbol).endswith(".IS")
    warnings = list(market.get("warnings", []))
    if is_bist:
        warnings.append(
            "BIST şirketinde KAP finansal bildirimleri ve lisanslı BIST piyasa verisi bu ilk kurulumda henüz otomatik bağlı değil. Finansal kalemleri resmî KAP/MKK bildirimiyle doğrulayın."
        )
    if errors:
        warnings.extend(f"{key} provider error: {value}" for key, value in errors.items())
    if sec.get("available") is False:
        warnings.append(sec.get("reason", "SEC fundamentals not available for this symbol."))
    try:
        consensus = broker_consensus(symbol)
    except Exception:
        consensus = {"independent_verified_record_count": 0, "recommendation_distribution": {"buy": 0, "hold": 0, "sell": 0}, "equal_weight_target_price": {"count": 0, "mean": None, "median": None}, "accuracy_weighted_target_price": None}
    report = {
        "report_id": str(uuid4()),
        "symbol": symbol,
        "company_name": profile.get("name") or sec.get("company_name") or symbol,
        "market_region": "BIST" if is_bist else ("US" if sec.get("available") else "global_or_unclassified"),
        "as_of": datetime.now(UTC).isoformat(),
        "profile": profile,
        "fundamentals": fundamentals,
        "valuation": valuation,
        "technical": technical,
        "risk_flags": risk_flags,
        "recommendation": recommendation,
        "sources": [
            item for item in (
                market.get("provider"),
                sec.get("provider"),
            ) if item
        ],
        "filings": sec.get("recent_filings", []),
        "institutional_consensus": consensus,
        "price_history": history,
        "evidence_gaps": warnings + fundamentals.get("warnings", []),
        "completeness": {
            "market_price": profile.get("current_price") is not None,
            "price_history": technical.get("observations", 0) >= 200,
            "financial_revenue": fundamentals["metrics"]["revenue"]["latest"] is not None,
            "financial_net_income": fundamentals["metrics"]["net_income"]["latest"] is not None,
            "sec_filings": sec.get("available", False),
        },
        "methodology_version": METHODOLOGY_VERSION,
        "important_notice": (
            "İlk sürüm araştırma çıktısıdır; otomatik yatırım danışmanlığı değildir. "
            "Karar kuralları henüz geriye dönük performans testiyle kalibre edilmemiştir."
        ),
    }
    values = list(report["completeness"].values())
    report["data_completeness_pct"] = round(sum(bool(v) for v in values) / len(values) * 100, 1)
    report["company_research_checklist"] = build_company_checklist(
        report, consensus.get("independent_verified_record_count", 0)
    )
    _persist_market_data(report, market, sec)
    _persist_report(report)
    _cache_put(symbol, report)
    return report

def _persist_market_data(report: dict, market: dict, sec: dict) -> None:
    conn = connect()
    profile = report.get("profile", {})
    conn.execute(
        """
        INSERT OR REPLACE INTO company_profiles(
            symbol,company_name,exchange,currency,country,sector,industry,website,
            market_cap,shares_outstanding,last_price,price_timestamp,source,source_url,retrieved_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            report["symbol"], profile.get("name"), profile.get("exchange"),
            profile.get("currency"), profile.get("country"), profile.get("sector"),
            profile.get("industry"), profile.get("website"), profile.get("market_cap"),
            profile.get("shares_outstanding"), profile.get("current_price"),
            profile.get("price_timestamp"), "yahoo_finance_via_yfinance",
            "https://finance.yahoo.com/", report["as_of"],
        ),
    )
    for bar in market.get("price_history", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO price_history(
                symbol,trade_date,open,high,low,close,adjusted_close,volume,currency,source,retrieved_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                report["symbol"], bar["date"], bar.get("open"), bar.get("high"),
                bar.get("low"), bar["close"], bar.get("adjusted_close"),
                bar.get("volume"), profile.get("currency"),
                "yahoo_finance_via_yfinance", report["as_of"],
            ),
        )
    sec_financials = sec.get("financials_annual", {}) if sec.get("available") else {}
    for metric, entries in sec_financials.items():
        for row in entries:
            if row.get("value") is None:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO financial_snapshots(
                    symbol,metric_code,period_end,period_type,value,currency,unit,
                    source,source_url,retrieved_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    report["symbol"], metric, row["period_end"], "annual",
                    row["value"], row.get("unit"), row.get("unit"),
                    "sec_edgar", "https://www.sec.gov/edgar/sec-api-documentation",
                    report["as_of"],
                ),
            )
    conn.commit()
    conn.close()

def _persist_report(report: dict) -> None:
    conn = connect()
    conn.execute(
        """
        INSERT INTO research_reports(
            report_id,symbol,as_of,recommendation,confidence,data_completeness,
            risk_flags_json,report_json,methodology_version
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            report["report_id"], report["symbol"], report["as_of"],
            report["recommendation"]["action"], report["recommendation"]["confidence"],
            report["data_completeness_pct"],
            json.dumps(report["risk_flags"], ensure_ascii=False),
            json.dumps(report, ensure_ascii=False, default=str),
            report["methodology_version"],
        ),
    )
    conn.commit()
    conn.close()

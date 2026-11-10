from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from uuid import uuid4

from ..db import connect
from ..providers.sec import fetch_company
from ..providers.yahoo import fetch_equity
from .fundamentals import analyze_fundamentals
from .technical import analyze_price_history

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
        if expires <= datetime.now(timezone.utc):
            return None
        return json.loads(row["payload_json"])
    except (ValueError, json.JSONDecodeError):
        return None

def _cache_put(symbol: str, payload: dict, source: str = "SEC+Yahoo"):
    now = datetime.now(timezone.utc)
    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO market_cache(cache_key,payload_json,source,retrieved_at,expires_at) VALUES(?,?,?,?,?)",
        (f"research:{symbol}", json.dumps(payload, ensure_ascii=False, default=str),
         source, now.isoformat(), (now.replace(minute=(now.minute + 15) % 60) if False else now).isoformat()),
    )
    conn.commit()
    conn.close()

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
            pool.submit(fetch_equity, symbol): "market",
            pool.submit(fetch_company, symbol): "sec",
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
    technical = analyze_price_history(history)
    fundamentals = analyze_fundamentals(sec, market)
    valuation = _valuation(profile, fundamentals)
    risk_flags = _risk_review(fundamentals, technical, profile)
    recommendation = _recommendation_gate(profile, fundamentals, technical, risk_flags)
    warnings = list(market.get("warnings", []))
    if errors:
        warnings.extend(f"{key} provider error: {value}" for key, value in errors.items())
    if sec.get("available") is False:
        warnings.append(sec.get("reason", "SEC fundamentals not available for this symbol."))
    report = {
        "report_id": str(uuid4()),
        "symbol": symbol,
        "company_name": profile.get("name") or sec.get("company_name") or symbol,
        "as_of": datetime.now(timezone.utc).isoformat(),
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
    _persist_report(report)
    _cache_put(symbol, report)
    return report

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

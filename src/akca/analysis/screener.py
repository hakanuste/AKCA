from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean

from .engine import run_company_research

CANDIDATE_WEIGHTS = {
    "valuation": 0.30,
    "profitability": 0.25,
    "growth": 0.20,
    "balance_sheet": 0.15,
    "cash_flow": 0.10,
}

def _higher_better(value, bad: float, good: float):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, (number - bad) / (good - bad) * 100))

def _lower_better(value, good: float, bad: float):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return max(0.0, min(100.0, (bad - number) / (bad - good) * 100))

def _mean_available(values: list[float | None]):
    clean = [float(x) for x in values if x is not None]
    return mean(clean) if clean else None

def score_company(report: dict) -> dict:
    profile = report.get("profile", {})
    derived = report.get("fundamentals", {}).get("derived", {})
    valuation = report.get("valuation", {})
    sector = str(profile.get("sector") or "").casefold()
    is_financial = any(token in sector for token in ("financial", "bank", "insurance"))

    valuation_metrics = [
        _lower_better(valuation.get("trailing_pe_provider"), 8, 35),
        _lower_better(valuation.get("price_to_book_provider"), 0.8, 5),
    ]
    if not is_financial:
        valuation_metrics.append(
            _higher_better(valuation.get("free_cash_flow_yield_pct"), 0, 15)
        )

    categories = {
        "valuation": _mean_available(valuation_metrics),
        "profitability": _mean_available([
            _higher_better(derived.get("return_on_equity_pct"), 0, 25),
            _higher_better(derived.get("net_margin_pct"), -5, 25),
        ]),
        "growth": _higher_better(derived.get("revenue_growth_yoy_pct"), -20, 30),
        "balance_sheet": None if is_financial else _mean_available([
            _lower_better(derived.get("debt_to_equity"), 0.25, 3.0),
            _lower_better(derived.get("liabilities_to_assets"), 0.25, 0.95),
        ]),
        "cash_flow": None if is_financial else _higher_better(
            valuation.get("free_cash_flow_yield_pct"), -5, 15
        ),
    }

    available_weight = sum(
        CANDIDATE_WEIGHTS[name] for name, value in categories.items() if value is not None
    )
    score = (
        sum(categories[name] * CANDIDATE_WEIGHTS[name]
            for name in categories if categories[name] is not None) / available_weight
        if available_weight else None
    )
    coverage_pct = available_weight * 100
    rankable = score is not None and coverage_pct >= 70
    return {
        "provisional_score": round(score, 1) if score is not None else None,
        "score_coverage_pct": round(coverage_pct, 1),
        "rankable": rankable,
        "subscores": categories,
        "sector_classification": "financial" if is_financial else "non_financial_or_unknown",
        "methodology": "AKCA_VALUE_SCREEN_CANDIDATE_V1",
        "methodology_status": "unvalidated_candidate_weights",
    }

def screen_symbols(symbols: list[str], force_refresh: bool = False) -> dict:
    cleaned = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
    if not cleaned:
        raise ValueError("En az bir sembol gerekli.")
    if len(cleaned) > 20:
        raise ValueError("Tek taramada en fazla 20 sembol desteklenir.")
    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(run_company_research, symbol, force_refresh): symbol
            for symbol in cleaned
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                report = future.result()
                profile = report.get("profile", {})
                fundamentals = report.get("fundamentals", {})
                derived = fundamentals.get("derived", {})
                valuation = report.get("valuation", {})
                tech = report.get("technical", {})
                score = score_company(report)
                results.append({
                    "symbol": symbol,
                    "company_name": report.get("company_name"),
                    "price": profile.get("current_price"),
                    "currency": profile.get("currency"),
                    "market_cap": profile.get("market_cap"),
                    "trailing_pe": valuation.get("trailing_pe_provider"),
                    "forward_pe": valuation.get("forward_pe_provider"),
                    "price_to_book": valuation.get("price_to_book_provider"),
                    "revenue_growth_yoy_pct": derived.get("revenue_growth_yoy_pct"),
                    "return_on_equity_pct": derived.get("return_on_equity_pct"),
                    "debt_to_equity": derived.get("debt_to_equity"),
                    "free_cash_flow_yield_pct": valuation.get("free_cash_flow_yield_pct"),
                    "provisional_value_score": score["provisional_score"],
                    "score_coverage_pct": score["score_coverage_pct"],
                    "score_rankable": score["rankable"],
                    "score_subcategories": score["subscores"],
                    "score_methodology_status": score["methodology_status"],
                    "rsi_14": tech.get("indicators", {}).get("rsi_14"),
                    "trend": tech.get("indicators", {}).get("trend_state"),
                    "max_drawdown_2y_pct": tech.get("risk", {}).get("max_drawdown_2y_pct"),
                    "recommendation": report.get("recommendation", {}).get("action"),
                    "data_completeness_pct": report.get("data_completeness_pct"),
                    "report_id": report.get("report_id"),
                })
            except Exception as exc:
                errors.append({"symbol": symbol, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
    results.sort(
        key=lambda row: (
            row.get("score_rankable", False),
            row.get("provisional_value_score") or -1,
            row.get("score_coverage_pct") or 0,
            row.get("data_completeness_pct") or 0,
        ),
        reverse=True,
    )
    return {
        "symbols_requested": len(cleaned),
        "symbols_analyzed": len(results),
        "results": results,
        "errors": errors,
        "methodology": {
            "id": "AKCA_VALUE_SCREEN_CANDIDATE_V1",
            "weights": CANDIDATE_WEIGHTS,
            "status": "unvalidated_candidate_weights",
            "minimum_data_coverage_pct": 70,
            "note": "Bu puan bir ilk tarama önceliğidir; geriye dönük testle kalibre edilmemiştir ve AL sinyali değildir. Banka/sigorta gibi finansallarda borç ve nakit akışı çarpanları sektör nedeniyle dışarıda bırakılır.",
        },
    }

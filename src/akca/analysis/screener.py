from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from .engine import run_company_research

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
                results.append({
                    "symbol": symbol,
                    "company_name": report.get("company_name"),
                    "price": profile.get("current_price"),
                    "currency": profile.get("currency"),
                    "market_cap": profile.get("market_cap"),
                    "trailing_pe": valuation.get("trailing_pe_provider"),
                    "forward_pe": valuation.get("forward_pe_provider"),
                    "market_cap_to_revenue": valuation.get("market_cap_to_revenue"),
                    "revenue_growth_yoy_pct": derived.get("revenue_growth_yoy_pct"),
                    "return_on_equity_pct": derived.get("return_on_equity_pct"),
                    "debt_to_equity": derived.get("debt_to_equity"),
                    "free_cash_flow_yield_pct": valuation.get("free_cash_flow_yield_pct"),
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
            row.get("data_completeness_pct") or 0,
            row.get("revenue_growth_yoy_pct") or -999
        ),
        reverse=True,
    )
    return {
        "symbols_requested": len(cleaned),
        "symbols_analyzed": len(results),
        "results": results,
        "errors": errors,
        "ranking_note": "Sıralama veri bütünlüğü ve gelir büyümesine göre önceliklendirmedir; otomatik AL sıralaması değildir.",
    }

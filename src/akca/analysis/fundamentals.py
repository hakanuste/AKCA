from __future__ import annotations

from typing import Any

def _latest_value(financials: dict, metric: str) -> tuple[float | None, float | None, str | None]:
    entries = financials.get(metric) or []
    if not entries:
        return None, None, None
    first = entries[0]
    try:
        latest = float(first["value"])
    except (KeyError, TypeError, ValueError):
        latest = None
    previous = None
    if len(entries) > 1:
        try:
            previous = float(entries[1]["value"])
        except (KeyError, TypeError, ValueError):
            previous = None
    return latest, previous, first.get("period_end")

def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator

def analyze_fundamentals(
    sec_facts: dict | None,
    yahoo_data: dict | None,
    manual_facts: dict | None = None,
) -> dict:
    sec_available = bool(sec_facts and sec_facts.get("available"))
    facts = (sec_facts or {}).get("financials_annual", {}) if sec_available else {}
    manual_facts = manual_facts or {}
    income = (yahoo_data or {}).get("financials", {}).get("income_statement_annual", [])

    metrics: dict[str, Any] = {}
    for code in (
        "revenue", "net_income", "operating_cash_flow", "capex",
        "total_assets", "total_liabilities", "cash", "long_term_debt",
        "equity", "operating_income", "diluted_eps",
    ):
        latest, previous, period = _latest_value(facts, code)
        metric_source = "sec_edgar" if latest is not None else None
        source_url = None
        if latest is None and manual_facts.get(code):
            latest, previous, period = _latest_value(manual_facts, code)
            metric_source = "manual_user_verified" if latest is not None else None
            source_url = manual_facts[code][0].get("source_url")
        metrics[code] = {
            "latest": latest, "previous": previous, "period_end": period,
            "source": metric_source, "source_url": source_url,
        }

    yahoo_latest = income[0] if income else {}
    yahoo_keys = {
        "revenue": ("Total Revenue", "Operating Revenue", "Revenue"),
        "net_income": ("Net Income", "Net Income Common Stockholders"),
        "operating_income": ("Operating Income",),
    }
    yahoo_fallback_used = []
    for metric, candidates in yahoo_keys.items():
        if metrics[metric]["latest"] is not None:
            continue
        for key in candidates:
            value = yahoo_latest.get(key)
            if isinstance(value, (int, float)):
                metrics[metric] = {
                    "latest": float(value), "previous": None,
                    "period_end": yahoo_latest.get("period_end"),
                    "source": "yahoo_finance_secondary",
                }
                yahoo_fallback_used.append(metric)
                break

    revenue = metrics["revenue"]["latest"]
    prior_revenue = metrics["revenue"]["previous"]
    net_income = metrics["net_income"]["latest"]
    op_cash = metrics["operating_cash_flow"]["latest"]
    capex = metrics["capex"]["latest"]
    assets = metrics["total_assets"]["latest"]
    prior_assets = metrics["total_assets"]["previous"]
    equity = metrics["equity"]["latest"]
    prior_equity = metrics["equity"]["previous"]
    average_assets = (
        (assets + prior_assets) / 2
        if assets is not None and prior_assets is not None
        else assets
    )
    average_equity = (
        (equity + prior_equity) / 2
        if equity is not None and prior_equity is not None
        else equity
    )
    liabilities = metrics["total_liabilities"]["latest"]
    cash = metrics["cash"]["latest"]
    debt = metrics["long_term_debt"]["latest"]
    operating_income = metrics["operating_income"]["latest"]
    fcf = op_cash - abs(capex) if op_cash is not None and capex is not None else None

    revenue_growth = (
        (revenue / prior_revenue - 1) * 100
        if revenue is not None and prior_revenue not in (None, 0) else None
    )
    derived = {
        "revenue_growth_yoy_pct": revenue_growth,
        "net_margin_pct": _safe_div(net_income, revenue) * 100 if _safe_div(net_income, revenue) is not None else None,
        "return_on_assets_pct": _safe_div(net_income, average_assets) * 100 if _safe_div(net_income, average_assets) is not None else None,
        "return_on_equity_pct": _safe_div(net_income, average_equity) * 100 if _safe_div(net_income, average_equity) is not None else None,
        "return_on_assets_balance_basis": "average_opening_closing_assets" if prior_assets is not None else "closing_assets_only",
        "return_on_equity_balance_basis": "average_opening_closing_equity" if prior_equity is not None else "closing_equity_only",
        "debt_to_equity": _safe_div(debt, equity),
        "liabilities_to_assets": _safe_div(liabilities, assets),
        "cash_to_debt": _safe_div(cash, debt),
        "free_cash_flow": fcf,
        "free_cash_flow_margin_pct": _safe_div(fcf, revenue) * 100 if _safe_div(fcf, revenue) is not None else None,
        "operating_margin_pct": _safe_div(operating_income, revenue) * 100 if _safe_div(operating_income, revenue) is not None else None,
    }

    warnings = []
    has_manual_facts = any(manual_facts.get(code) for code in manual_facts)
    if not sec_available and not has_manual_facts:
        warnings.append("SEC XBRL finansalları eşleşmedi ve doğrulanmış manuel şirket finansalı yüklenmedi.")
    elif has_manual_facts and not sec_available:
        warnings.append(
            "Bazı finansal kalemler kullanıcı tarafından kaynak URL'siyle yüklenmiş ve doğrulanmış olarak işaretlenmiş manuel kayıtlardan alındı; değerler belgeye karşı ayrıca kontrol edilmelidir."
        )
    if yahoo_fallback_used:
        warnings.append(
            "Bazı metrikler ikincil Yahoo Finance şirket tablolarından alındı; SEC/şirket bildirimiyle teyit edilmelidir."
        )
    if not facts and not income:
        warnings.append("Finansal tablo verisi alınamadı; temel analiz sınırlı.")
    if metrics["revenue"]["latest"] is None:
        warnings.append("Gelir verisi bulunamadı.")
    if metrics["net_income"]["latest"] is None:
        warnings.append("Net dönem kârı verisi bulunamadı.")
    if derived["debt_to_equity"] is None:
        warnings.append("Borç/özsermaye oranı hesaplanamadı.")
    return {
        "status": "partial" if warnings else "ok",
        "statement_period": metrics["revenue"]["period_end"],
        "metrics": metrics,
        "derived": derived,
        "provider_precedence": {
            "primary": "SEC EDGAR XBRL when mapped",
            "manual_fallback": "user-uploaded source-linked facts marked verified by the operator",
            "secondary": "Yahoo Finance statements only as explicitly labeled fallback",
        },
        "warnings": warnings,
    }

import pytest

from akca.analysis.fundamentals import analyze_fundamentals

def test_roa_and_roe_use_average_opening_and_closing_balances():
    sec = {
        "available": True,
        "financials_annual": {
            "revenue": [
                {"value": 200.0, "period_end": "2025-12-31"},
                {"value": 150.0, "period_end": "2024-12-31"},
            ],
            "net_income": [
                {"value": 20.0, "period_end": "2025-12-31"},
                {"value": 15.0, "period_end": "2024-12-31"},
            ],
            "total_assets": [
                {"value": 100.0, "period_end": "2025-12-31"},
                {"value": 80.0, "period_end": "2024-12-31"},
            ],
            "equity": [
                {"value": 50.0, "period_end": "2025-12-31"},
                {"value": 40.0, "period_end": "2024-12-31"},
            ],
        },
    }
    result = analyze_fundamentals(sec, None)
    assert result["derived"]["revenue_growth_yoy_pct"] == pytest.approx(100 / 3)
    assert result["derived"]["return_on_assets_pct"] == pytest.approx(20 / 90 * 100)
    assert result["derived"]["return_on_equity_pct"] == pytest.approx(20 / 45 * 100)
    assert result["derived"]["return_on_assets_balance_basis"] == "average_opening_closing_assets"
    assert result["derived"]["return_on_equity_balance_basis"] == "average_opening_closing_equity"

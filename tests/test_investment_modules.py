from datetime import date, timedelta

import pytest

from akca.analysis import ipo as ipo_module
from akca.analysis import portfolio as portfolio_module
from akca.analysis.screener import score_company
from akca.db import connect

def test_ipo_total_return_applies_split_and_dividend_correctly(tmp_path, monkeypatch):
    db_path = tmp_path / "ipo-test.db"
    monkeypatch.setattr("akca.db.DB_PATH", db_path)

    offer_day = date.today() - timedelta(days=400)
    split_day = offer_day + timedelta(days=100)
    current_day = date.today()

    ipo_module.add_ipo(
        symbol="TEST",
        company_name="Test Issuer",
        offer_date=offer_day.isoformat(),
        offer_price=100,
        offer_currency="USD",
        source_url="https://issuer.example/ipo-prospectus",
        source_name="Official prospectus",
        verified=True,
    )

    def fake_fetch_equity(symbol, history_period="5y"):
        assert symbol == "TEST"
        return {
            "profile": {
                "symbol": "TEST",
                "name": "Test Issuer",
                "currency": "USD",
                "current_price": 50,
                "price_timestamp": current_day.isoformat(),
            },
            "price_history": [
                {
                    "date": offer_day.isoformat(), "close": 100,
                    "stock_splits": 0, "dividends": 0,
                },
                {
                    "date": split_day.isoformat(), "close": 50,
                    "stock_splits": 2, "dividends": 0.5,
                },
                {
                    "date": current_day.isoformat(), "close": 50,
                    "stock_splits": 0, "dividends": 0,
                },
            ],
            "provider": {"source_id": "test_provider"},
        }

    monkeypatch.setattr(ipo_module, "fetch_equity", fake_fetch_equity)
    monkeypatch.setattr(
        ipo_module,
        "fetch_macro",
        lambda *args, **kwargs: {"status": "not_configured", "series": []},
    )

    result = ipo_module.ipo_performance("TEST")
    assert result["corporate_action_coverage_complete"] is True
    assert result["cumulative_split_factor"] == pytest.approx(2)
    assert result["dividends_per_original_share"] == pytest.approx(1)
    assert result["offer_to_current_price_return_pct"] == pytest.approx(0)
    assert result["offer_to_current_total_return_pct"] == pytest.approx(1)
    assert result["usd_total_return_pct"] == pytest.approx(1)
    assert result["real_usd_total_return_pct"] is None

def test_recent_ipo_registry_uses_a_rolling_two_year_window(tmp_path, monkeypatch):
    db_path = tmp_path / "ipo-window.db"
    monkeypatch.setattr("akca.db.DB_PATH", db_path)
    current = date.today()
    recent = current - timedelta(days=180)
    old = current - timedelta(days=900)

    ipo_module.add_ipo(
        "NEW1", "Recent Company", recent.isoformat(), 10, "TRY",
        "https://issuer.example/recent", "Official prospectus", True,
    )
    ipo_module.add_ipo(
        "OLD1", "Old Company", old.isoformat(), 10, "TRY",
        "https://issuer.example/old", "Official prospectus", True,
    )

    result = ipo_module.recent_ipos(days=730, max_items=100)
    symbols = {item["symbol"] for item in result["ipos"]}
    assert result["count"] == 1
    assert symbols == {"NEW1"}

def test_portfolio_does_not_mix_currencies_or_publish_false_weights(monkeypatch):
    prices = {
        "AAA": {"profile": {"current_price": 10, "currency": "USD", "exchange": "NASDAQ"}, "price_history": []},
        "BBB": {"profile": {"current_price": 20, "currency": "TRY", "exchange": "BIST"}, "price_history": []},
    }
    monkeypatch.setattr(
        portfolio_module,
        "fetch_equity",
        lambda symbol, history_period="1y": prices[symbol],
    )
    result = portfolio_module.analyze_portfolio(
        [{"symbol": "AAA", "quantity": 2}, {"symbol": "BBB", "quantity": 3}],
        base_currency="TRY",
    )
    assert result["market_value_unconverted"] is None
    assert result["herfindahl_index"] is None
    assert all(position["weight_pct"] is None for position in result["positions"])
    assert any("Birden fazla para birimi" in warning for warning in result["warnings"])
    assert not any("Bazı pozisyonların fiyatı alınamadığından" in warning for warning in result["warnings"])

def test_portfolio_same_currency_weights_and_concentration(monkeypatch):
    prices = {
        "AAA": {"profile": {"current_price": 10, "currency": "USD"}, "price_history": []},
        "BBB": {"profile": {"current_price": 20, "currency": "USD"}, "price_history": []},
    }
    monkeypatch.setattr(
        portfolio_module,
        "fetch_equity",
        lambda symbol, history_period="1y": prices[symbol],
    )
    result = portfolio_module.analyze_portfolio(
        [{"symbol": "AAA", "quantity": 2}, {"symbol": "BBB", "quantity": 2}],
        base_currency="USD",
    )
    assert result["market_value_unconverted"] == pytest.approx(60)
    assert result["positions"][0]["weight_pct"] == pytest.approx(33.3333333)
    assert result["positions"][1]["weight_pct"] == pytest.approx(66.6666667)
    assert result["herfindahl_index"] == pytest.approx((1/3)**2 + (2/3)**2)

def test_value_screener_marks_provisional_weights_as_unvalidated():
    report = {
        "profile": {"sector": "Technology"},
        "fundamentals": {
            "derived": {
                "return_on_equity_pct": 20,
                "net_margin_pct": 15,
                "revenue_growth_yoy_pct": 12,
                "debt_to_equity": 0.4,
                "liabilities_to_assets": 0.5,
            }
        },
        "valuation": {
            "trailing_pe_provider": 15,
            "price_to_book_provider": 2,
            "free_cash_flow_yield_pct": 7,
        },
    }
    result = score_company(report)
    assert result["provisional_score"] is not None
    assert result["score_coverage_pct"] == pytest.approx(100)
    assert result["rankable"] is True
    assert result["methodology_status"] == "unvalidated_candidate_weights"

def test_value_screener_refuses_to_rank_insufficient_data():
    result = score_company({"profile": {}, "fundamentals": {"derived": {}}, "valuation": {}})
    assert result["provisional_score"] is None
    assert result["rankable"] is False
    assert result["score_coverage_pct"] == 0


def test_portfolio_does_not_publish_weights_when_a_holding_is_unpriced(monkeypatch):
    def fake_fetch(symbol, history_period="1y"):
        if symbol == "MISSING":
            return {"profile": {"current_price": None, "currency": None}, "price_history": []}
        return {"profile": {"current_price": 10, "currency": "USD"}, "price_history": []}

    monkeypatch.setattr(portfolio_module, "fetch_equity", fake_fetch)
    result = portfolio_module.analyze_portfolio(
        [{"symbol": "AAA", "quantity": 1}, {"symbol": "MISSING", "quantity": 5}],
        base_currency="USD",
    )
    assert result["market_value_unconverted"] is None
    assert result["herfindahl_index"] is None
    assert all(p["weight_pct"] is None for p in result["positions"])
    assert any("fiyatı veya para birimi eksik" in w for w in result["warnings"])

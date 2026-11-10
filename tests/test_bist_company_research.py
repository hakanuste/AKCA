from akca.analysis import engine

def test_bist_company_research_skips_sec_and_uses_kap_source_state(monkeypatch):
    monkeypatch.setattr(engine, "_cache_get", lambda symbol: None)
    monkeypatch.setattr(
        engine,
        "_fetch_market",
        lambda symbol: {
            "profile": {
                "symbol": "GARAN.IS",
                "name": "Türkiye Garanti Bankası",
                "exchange": "Istanbul",
                "currency": "TRY",
                "current_price": 100.0,
                "price_timestamp": "2026-11-10",
            },
            "price_history": [
                {"date": "2026-11-09", "close": 99.0, "adjusted_close": 99.0},
                {"date": "2026-11-10", "close": 100.0, "adjusted_close": 100.0},
            ],
            "financials": {},
            "provider": {
                "source_id": "yahoo_finance_via_yfinance",
                "source_name": "Yahoo Finance via yfinance",
                "status": "retrieved",
                "url": "https://finance.yahoo.com/",
                "limitations": ["Unofficial market-data interface."],
            },
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        engine,
        "fetch_company",
        lambda symbol: (_ for _ in ()).throw(AssertionError("BIST symbols must not call SEC")),
    )
    monkeypatch.setattr(engine, "load_verified_annual_facts", lambda symbol: ({}, []))
    monkeypatch.setattr(
        engine,
        "broker_consensus",
        lambda symbol: {
            "independent_verified_record_count": 0,
            "recommendation_distribution": {"buy": 0, "hold": 0, "sell": 0},
            "equal_weight_target_price": {"count": 0, "mean": None, "median": None},
            "accuracy_weighted_target_price": None,
        },
    )
    monkeypatch.setattr(engine, "_persist_market_data", lambda *args: None)
    monkeypatch.setattr(engine, "_persist_report", lambda *args: None)
    monkeypatch.setattr(engine, "_cache_put", lambda *args: None)

    result = engine.run_company_research("GARAN.IS", force_refresh=True)

    assert result["market_region"] == "BIST"
    assert result["recommendation"]["action"] == "BEKLE"
    assert any(source["source_id"] == "kap_mkk_api" for source in result["sources"])
    assert any("KAP/MKK" in warning for warning in result["evidence_gaps"])

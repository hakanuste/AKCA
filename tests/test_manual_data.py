import pytest

import akca.db as db_module
from akca.analysis.fundamentals import analyze_fundamentals
from akca.analysis.manual_data import import_financial_facts, load_verified_annual_facts

def test_only_operator_verified_source_linked_annual_facts_feed_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "manual-facts.db")
    base_facts = [
        {"metric_code": "revenue", "period_end": "2025-12-31", "period_type": "annual", "value": 1000, "currency": "TRY", "unit": "TRY"},
        {"metric_code": "revenue", "period_end": "2024-12-31", "period_type": "annual", "value": 800, "currency": "TRY", "unit": "TRY"},
        {"metric_code": "net_income", "period_end": "2025-12-31", "period_type": "annual", "value": 100, "currency": "TRY", "unit": "TRY"},
        {"metric_code": "total_assets", "period_end": "2025-12-31", "period_type": "annual", "value": 2000, "currency": "TRY", "unit": "TRY"},
        {"metric_code": "total_assets", "period_end": "2024-12-31", "period_type": "annual", "value": 1800, "currency": "TRY", "unit": "TRY"},
        {"metric_code": "equity", "period_end": "2025-12-31", "period_type": "annual", "value": 1000, "currency": "TRY", "unit": "TRY"},
        {"metric_code": "equity", "period_end": "2024-12-31", "period_type": "annual", "value": 900, "currency": "TRY", "unit": "TRY"},
    ]

    pending = import_financial_facts(
        "AEFES.IS", "KAP faaliyet raporu",
        "https://kap.org.tr/tr/Bildirim/123456", base_facts, verified=False,
    )
    assert pending["imported_rows"] == len(base_facts)
    facts, sources = load_verified_annual_facts("AEFES.IS")
    assert facts == {}
    assert sources == []

    verified = import_financial_facts(
        "AEFES.IS", "KAP faaliyet raporu",
        "https://kap.org.tr/tr/Bildirim/123456", base_facts, verified=True,
        notes="2025 yıllık finansallar; konsolide.",
    )
    assert verified["verified_by_user"] is True

    facts, sources = load_verified_annual_facts("AEFES.IS")
    assert len(sources) == 1
    assert facts["revenue"][0]["value"] == 1000
    assert facts["revenue"][1]["value"] == 800

    result = analyze_fundamentals(
        {"available": False, "financials_annual": {}},
        None,
        manual_facts=facts,
    )
    assert result["metrics"]["revenue"]["source"] == "manual_user_verified"
    assert result["derived"]["revenue_growth_yoy_pct"] == pytest.approx(25)
    assert result["derived"]["return_on_assets_pct"] == pytest.approx(100 / 1900 * 100)
    assert any("kullanıcı tarafından" in warning for warning in result["warnings"])

def test_financial_import_rejects_unsupported_metrics_and_invalid_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "invalid-manual.db")
    facts = [{"metric_code": "made_up_metric", "period_end": "2025-12-31", "value": 10}]
    with pytest.raises(ValueError, match="Desteklenmeyen"):
        import_financial_facts(
            "TEST", "Unknown", "https://example.com/filing", facts, verified=True
        )
    with pytest.raises(ValueError, match="URL"):
        import_financial_facts(
            "TEST", "Unknown", "javascript:alert(1)",
            [{"metric_code": "revenue", "period_end": "2025-12-31", "value": 10}],
            verified=True,
        )

from fastapi.testclient import TestClient

import akca.api as api_module
import akca.db as db_module

def test_api_health_reference_data_terminal_and_portfolio_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "api-test.db")
    monkeypatch.setattr(api_module, "API_KEY", "unit-test-secret")

    with TestClient(api_module.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["reference_item_count"] == 409
        assert health.json()["write_api_enabled"] is True

        items = client.get("/api/items", params={"q": "Pirinç"})
        assert items.status_code == 200
        assert items.json()["total"] >= 1
        assert items.json()["items"][0]["item_code"] == "0111101"

        terminal = client.get("/terminal.html")
        assert terminal.status_code == 200
        assert "AKÇA Research Terminal" in terminal.text

        unauthorized = client.get("/api/portfolios")
        assert unauthorized.status_code == 401

        created = client.post(
            "/api/portfolios",
            headers={"X-AKCA-API-Key": "unit-test-secret"},
            json={"name": "Test Portfolio", "base_currency": "TRY"},
        )
        assert created.status_code == 201
        portfolio_id = created.json()["portfolio_id"]

        listed = client.get(
            "/api/portfolios",
            headers={"X-AKCA-API-Key": "unit-test-secret"},
        )
        assert listed.status_code == 200
        assert any(row["portfolio_id"] == portfolio_id for row in listed.json())

        imported = client.post(
            "/api/financial-facts/AEFES.IS/import",
            headers={"X-AKCA-API-Key": "unit-test-secret"},
            json={
                "source_name": "KAP annual filing",
                "source_url": "https://kap.org.tr/tr/Bildirim/123456",
                "verified_by_operator": True,
                "facts": [
                    {
                        "metric_code": "revenue",
                        "period_end": "2025-12-31",
                        "period_type": "annual",
                        "value": 125000,
                        "currency": "TRY",
                        "unit": "TRY",
                    }
                ],
            },
        )
        assert imported.status_code == 201
        assert imported.json()["imported_rows"] == 1
        saved_facts = client.get(
            "/api/financial-facts/AEFES.IS",
            headers={"X-AKCA-API-Key": "unit-test-secret"},
        )
        assert saved_facts.status_code == 200
        assert saved_facts.json()["facts"][0]["metric_code"] == "revenue"
        assert saved_facts.json()["facts"][0]["verified"] == 1

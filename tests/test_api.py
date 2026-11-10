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

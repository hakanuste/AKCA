from datetime import date

from akca.providers import evds, fred

def test_evds_adapter_uses_server_key_header_and_documented_rest_path(monkeypatch):
    monkeypatch.setenv("TCMB_EVDS_API_KEY", "server-side-test-secret")
    monkeypatch.setattr(evds, "BASE_URL", "https://evds2.example/service/evds/")
    captured = {}

    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return [
                {
                    "Tarih": "10-11-2026",
                    "TP_DK_USD_A_YTL": "42,50",
                },
                {
                    "Tarih": "11-11-2026",
                    "TP_DK_USD_A_YTL": "42,75",
                },
            ]

    class FakeClient:
        def __init__(self, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def get(self, url, headers):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(evds.httpx, "Client", FakeClient)
    result = evds.fetch_evds(
        ["TP.DK.USD.A.YTL"],
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 11),
    )
    assert result["status"] == "ok"
    assert result["series"][0]["latest"] == {
        "date": "11-11-2026",
        "value": 42.75,
    }
    assert captured["headers"]["key"] == "server-side-test-secret"
    assert "series=TP.DK.USD.A.YTL" in captured["url"]
    assert "startDate=01-11-2026" in captured["url"]
    assert "endDate=11-11-2026" in captured["url"]
    assert "type=json" in captured["url"]

def test_evds_requires_api_key_without_leaking_credentials(monkeypatch):
    monkeypatch.delenv("TCMB_EVDS_API_KEY", raising=False)
    result = evds.fetch_evds()
    assert result["status"] == "not_configured"
    assert result["series"] == []
    assert "API key" not in str(result)

def test_fred_provider_reports_missing_key_as_unconfigured(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    result = fred.fetch_macro(["DGS10"])
    assert result["status"] == "not_configured"
    assert result["series"] == []


def test_evds_catalogue_requests_data_groups_and_series(monkeypatch):
    monkeypatch.setenv("TCMB_EVDS_API_KEY", "catalogue-test-key")
    monkeypatch.setattr(evds, "BASE_URL", "https://evds3.example/igmevdsms-dis/")
    calls = []

    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"items": [{"code": "bie_mkb", "name": "Borsa İstanbul Kıymetli Madenler"}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def get(self, url, headers):
            calls.append((url, headers))
            return FakeResponse()

    monkeypatch.setattr(evds.httpx, "Client", FakeClient)
    groups = evds.fetch_evds_catalogue("datagroups")
    series = evds.fetch_evds_catalogue("series", code="bie_mkb")
    assert groups["items"][0]["code"] == "bie_mkb"
    assert series["items"][0]["name"].startswith("Borsa İstanbul")
    assert calls[0][0].endswith("datagroups/mode=0&type=json")
    assert calls[1][0].endswith("serieList/type=json&code=bie_mkb")
    assert calls[0][1]["key"] == "catalogue-test-key"

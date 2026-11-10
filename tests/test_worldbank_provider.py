from akca.providers import worldbank

def test_world_bank_pink_sheet_wide_matrix_parsing():
    rows = [
        ("World Bank Commodity Prices", None, None),
        (None, None, None),
        ("Monthly Prices", None, None),
        (None, None, None),
        ("Period", "GOLD", "CRUDE_BRENT"),
        ("Unit", "USD/toz", "USD/bbl"),
        ("1960M01", 35.27, 1.63),
        ("1960M02", 35.27, "..."),
    ]
    data, metadata = worldbank.parse_monthly_prices_rows(rows)
    assert data == [
        {"period": "1960-01", "GOLD": 35.27, "CRUDE_BRENT": 1.63},
        {"period": "1960-02", "GOLD": 35.27},
    ]
    assert metadata == [
        {"series_code": "GOLD", "unit": "USD/toz"},
        {"series_code": "CRUDE_BRENT", "unit": "USD/bbl"},
    ]

def test_world_bank_pink_sheet_query_uses_series_codes_and_limit(monkeypatch):
    monkeypatch.setattr(
        worldbank,
        "_monthly_data",
        lambda: (
            [
                {"period": "2026-01", "GOLD": 4900.0, "CRUDE_BRENT": 70.0},
                {"period": "2026-02", "GOLD": 5000.0, "CRUDE_BRENT": 72.0},
            ],
            [
                {"series_code": "GOLD", "unit": "USD/toz"},
                {"series_code": "CRUDE_BRENT", "unit": "USD/bbl"},
            ],
            "https://example.com/world-bank.xlsx",
        ),
    )
    result = worldbank.fetch_commodity_history(query="gold", limit=1)
    assert result["status"] == "ok"
    assert len(result["series"]) == 1
    assert result["series"][0]["series_code"] == "GOLD"
    assert result["series"][0]["unit"] == "USD/toz"
    assert result["series"][0]["observations"] == [
        {"period": "2026-02", "price_usd": 5000.0}
    ]

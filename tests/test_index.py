from datetime import datetime

import pytest

from akca.index import calculate_month, check_weights
from akca.ingest import add_variant, import_items, set_item_weight
from akca.pricing import PriceObservation, add_observation, set_observation_status

def _one_item_csv(tmp_path):
    path = tmp_path / "items.csv"
    path.write_text(
        "item_code,name_tr,name_en,group_name,weight_percent,unit_definition,matching_note\n"
        "0000001,Test item,Test item,Test group,,,\n",
        encoding="utf-8",
    )
    return path

def test_reference_import_preserves_409_codes_and_blocks_missing_weights(tmp_path):
    db = tmp_path / "akca.db"
    count = import_items(db_path=db)
    assert count == 409
    from akca.db import connect
    conn = connect(db)
    rows = conn.execute("SELECT item_code FROM items ORDER BY item_code").fetchall()
    conn.close()
    assert len(rows) == 409
    assert rows[0]["item_code"] == "0111101"
    assert all(len(row["item_code"]) == 7 for row in rows)
    status = check_weights(db_path=db)
    assert status["ready"] is False
    assert status["verified_item_weight_count"] == 0

def test_monthly_index_uses_exact_previous_month_and_variant_weights(tmp_path):
    db = tmp_path / "akca.db"
    import_items(_one_item_csv(tmp_path), db_path=db)
    set_item_weight("0000001", 100, "Verified test reference", True, db_path=db)
    add_variant(
        "0000001", "test-1kg", "Test product 1 kg",
        100, "Verified representative weight", True, db_path=db
    )

    for period, month, price in [("2026-09", "09", 100), ("2026-10", "10", 110)]:
        for seller in ("Seller A", "Seller B", "Seller C"):
            observation = PriceObservation(
                period=period,
                item_code="0000001",
                variant_key="test-1kg",
                vendor=seller,
                product_description="Test product 1 kg",
                region="TR",
                channel="online",
                quantity=1,
                unit="kg",
                price_try=price,
                source_url="https://example.com/item",
                observed_at=datetime.fromisoformat(f"2026-{month}-15T10:00:00+03:00"),
            )
            obs_id = add_observation(observation, db_path=db)
            set_observation_status(obs_id, "approved", db_path=db)

    result = calculate_month("2026-10", db_path=db, min_sellers=3)
    assert result["status"] == "calculated"
    assert result["previous_period"] == "2026-09"
    assert result["monthly_inflation_pct"] == pytest.approx(10)
    assert result["coverage_weight_pct"] == pytest.approx(100)
    assert result["index_value"] == pytest.approx(110)
    assert result["index_rebased"] is True
    assert result["index_base_period"] == "2026-09"

def test_missing_current_month_data_blocks_index(tmp_path):
    db = tmp_path / "akca.db"
    import_items(_one_item_csv(tmp_path), db_path=db)
    set_item_weight("0000001", 100, "Verified", True, db_path=db)
    add_variant(
        "0000001", "test-1kg", "Test product 1 kg",
        100, "Verified", True, db_path=db
    )
    result = calculate_month("2026-10", db_path=db)
    assert result["status"] == "blocked_incomplete_coverage"
    assert result["monthly_inflation_pct"] is None

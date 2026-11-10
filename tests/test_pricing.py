from datetime import datetime

import pytest
from pydantic import ValidationError

from akca.ingest import add_variant, import_items, set_item_weight
from akca.pricing import (
    PriceObservation,
    add_observation,
    normalize_price,
    set_observation_status,
)

def test_mass_and_volume_normalization():
    price, unit = normalize_price(60, 0, 500, "g")
    assert price == pytest.approx(120)
    assert unit == "kg"
    price, unit = normalize_price(75, 5, 750, "ml")
    assert price == pytest.approx(106.6666667)
    assert unit == "l"

def test_unknown_unit_is_rejected():
    with pytest.raises(ValueError, match="Desteklenmeyen birim"):
        normalize_price(100, 0, 1, "kutu")

def test_observation_requires_same_period_as_timestamp():
    with pytest.raises(ValidationError):
        PriceObservation(
            period="2026-10",
            item_code="0111101",
            variant_key="rice-1kg",
            vendor="Satıcı A",
            product_description="Pirinç 1 kg",
            region="Türkiye",
            channel="online",
            quantity=1,
            unit="kg",
            price_try=100,
            source_url="https://shop.example/product",
            observed_at=datetime.fromisoformat("2026-09-15T10:00:00+03:00"),
        )

def test_observation_is_pending_and_unit_normalized(tmp_path):
    csv_path = tmp_path / "items.csv"
    csv_path.write_text(
        "item_code,name_tr,name_en,group_name,weight_percent,unit_definition,matching_note\n"
        "0111101,Pirinç,Rice,Gıda,,,\n",
        encoding="utf-8",
    )
    db = tmp_path / "akca.db"
    import_items(csv_path, db_path=db)
    add_variant(
        "0111101", "rice-1kg", "Pirinç 1 kg, aynı kalite/SKU",
        100, "Test temsili", True, db_path=db
    )
    payload = PriceObservation(
        period="2026-10",
        item_code="0111101",
        variant_key="rice-1kg",
        vendor="Satıcı A",
        product_description="Pirinç 1 kg",
        region="Türkiye",
        channel="online",
        quantity=1000,
        unit="g",
        price_try=120,
        shipping_try=0,
        source_url="https://shop.example/product",
        observed_at=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
    )
    observation_id = add_observation(payload, db_path=db)
    import sqlite3
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT quality_status, normalized_price_try, normalized_unit FROM observations WHERE id=?",
        (observation_id,),
    ).fetchone()
    conn.close()
    assert row == ("pending", 120.0, "kg")
    set_observation_status(observation_id, "approved", db_path=db)

def test_unverified_weights_do_not_pass(tmp_path):
    csv_path = tmp_path / "items.csv"
    csv_path.write_text(
        "item_code,name_tr,name_en,group_name,weight_percent,unit_definition,matching_note\n"
        "0111101,Pirinç,Rice,Gıda,,,\n",
        encoding="utf-8",
    )
    db = tmp_path / "akca.db"
    import_items(csv_path, db_path=db)
    set_item_weight("0111101", 100, "Kaynak teyit bekliyor", verified=False, db_path=db)
    add_variant(
        "0111101", "rice-1kg", "Pirinç 1 kg", 100,
        "Temsil kaynağı", False, db_path=db
    )
    from akca.index import check_weights
    assert check_weights(db_path=db)["ready"] is False

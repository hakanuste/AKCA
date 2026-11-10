import csv
from pathlib import Path

from .config import ITEMS_PATH
from .db import connect

def import_items(path: Path = ITEMS_PATH, db_path=None) -> int:
    conn = connect(db_path)
    count = 0
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = str(row["item_code"]).strip().zfill(7)
            conn.execute(
                """
                INSERT INTO items (
                    item_code, name_tr, name_en, group_name,
                    unit_definition, matching_note
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_code) DO UPDATE SET
                    name_tr=excluded.name_tr,
                    name_en=excluded.name_en,
                    group_name=excluded.group_name,
                    unit_definition=excluded.unit_definition,
                    matching_note=excluded.matching_note
                """,
                (
                    code,
                    row["name_tr"].strip(),
                    row.get("name_en", "").strip(),
                    row.get("group_name", "").strip(),
                    row.get("unit_definition", "").strip(),
                    row.get("matching_note", "").strip(),
                ),
            )
            count += 1
    conn.commit()
    conn.close()
    return count

def set_item_weight(
    item_code: str,
    weight_percent: float,
    source: str,
    verified: bool = False,
    db_path=None,
) -> None:
    if not 0 <= weight_percent <= 100:
        raise ValueError("Ağırlık 0-100 arasında olmalı.")
    if not source.strip():
        raise ValueError("Ağırlık kaynağı zorunludur.")
    conn = connect(db_path)
    cur = conn.execute(
        """
        UPDATE items
        SET weight_percent=?, weight_source=?, weight_verified=?
        WHERE item_code=?
        """,
        (weight_percent, source.strip(), int(verified), item_code.zfill(7)),
    )
    conn.commit()
    conn.close()
    if not cur.rowcount:
        raise KeyError(f"Madde kodu bulunamadı: {item_code}")

def add_variant(
    item_code: str,
    variant_key: str,
    label: str,
    within_item_weight_percent: float,
    weight_source: str,
    verified: bool = False,
    db_path=None,
) -> None:
    if not 0 <= within_item_weight_percent <= 100:
        raise ValueError("Madde içi varyant ağırlığı 0-100 arasında olmalı.")
    if not weight_source.strip():
        raise ValueError("Varyant ağırlığı/temsil kaynağı zorunludur.")
    if not label.strip():
        raise ValueError("Varyant tanımı zorunludur.")
    conn = connect(db_path)
    if not conn.execute("SELECT 1 FROM items WHERE item_code=?", (item_code.zfill(7),)).fetchone():
        conn.close()
        raise KeyError(f"Madde kodu bulunamadı: {item_code}")
    conn.execute(
        """
        INSERT INTO item_variants(
            item_code, variant_key, label, within_item_weight_percent,
            weight_source, weight_verified
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_code, variant_key) DO UPDATE SET
            label=excluded.label,
            within_item_weight_percent=excluded.within_item_weight_percent,
            weight_source=excluded.weight_source,
            weight_verified=excluded.weight_verified
        """,
        (
            item_code.zfill(7),
            variant_key.strip().lower(),
            label.strip(),
            within_item_weight_percent,
            weight_source.strip(),
            int(verified),
        ),
    )
    conn.commit()
    conn.close()

def set_variant_active(item_code: str, variant_key: str, active: bool, db_path=None) -> None:
    conn = connect(db_path)
    cur = conn.execute(
        "UPDATE item_variants SET is_active=? WHERE item_code=? AND variant_key=?",
        (int(active), item_code.zfill(7), variant_key.strip().lower()),
    )
    conn.commit()
    conn.close()
    if not cur.rowcount:
        raise KeyError(f"Varyant bulunamadı: {item_code}/{variant_key}")

import csv
from pathlib import Path
from .config import ITEMS_PATH
from .db import connect

def import_items(path: Path = ITEMS_PATH, db_path=None) -> int:
 conn = connect(db_path)
 count = 0
 with path.open(encoding="utf-8-sig", newline="") as f:
  for row in csv.DictReader(f):
   conn.execute("""INSERT INTO items(item_code,name_tr,name_en,group_name,weight_percent,unit_definition,matching_note)
    VALUES(?,?,?,?,?,?,?) ON CONFLICT(item_code) DO UPDATE SET name_tr=excluded.name_tr,
    name_en=excluded.name_en,group_name=excluded.group_name,unit_definition=excluded.unit_definition,
    matching_note=excluded.matching_note""",
    (row["item_code"],row["name_tr"],row["name_en"],row["group_name"],None,row.get("unit_definition",""),row.get("matching_note","")))
   count += 1
 conn.commit(); conn.close()
 return count

def set_item_weight(item_code: str, weight_percent: float, source: str, verified: bool = False, db_path=None):
 if not 0 <= weight_percent <= 100: raise ValueError("Ağırlık 0-100 arasında olmalı.")
 if not source.strip(): raise ValueError("Ağırlık kaynağı zorunludur.")
 conn=connect(db_path)
 cur=conn.execute("UPDATE items SET weight_percent=?,weight_source=?,weight_verified=? WHERE item_code=?",(weight_percent,source,int(verified),item_code))
 conn.commit(); changed=cur.rowcount; conn.close()
 if not changed: raise KeyError(f"Madde kodu bulunamadı: {item_code}")

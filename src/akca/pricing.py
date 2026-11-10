from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from .db import connect

class PriceObservation(BaseModel):
 period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
 item_code: str
 vendor: str = Field(min_length=2)
 product_description: str = Field(min_length=2)
 region: str
 channel: str
 quantity: float = Field(gt=0)
 unit: str
 price_try: float = Field(gt=0)
 in_stock: bool = True
 shipping_try: float = Field(default=0, ge=0)
 source_url: str
 observed_at: datetime
 membership_required: bool = False
 campaign_condition: str | None = None

 @field_validator("observed_at")
 @classmethod
 def require_timezone(cls, value):
  if value.tzinfo is None: raise ValueError("observed_at saat dilimi içermeli.")
  return value

def add_observation(data: PriceObservation, db_path=None) -> int:
 conn=connect(db_path)
 exists=conn.execute("SELECT 1 FROM items WHERE item_code=?",(data.item_code,)).fetchone()
 if not exists:
  conn.close(); raise KeyError(f"Bilinmeyen 2022 madde kodu: {data.item_code}")
 cur=conn.execute("""INSERT INTO observations(period,item_code,vendor,product_description,region,channel,quantity,unit,price_try,in_stock,shipping_try,source_url,observed_at,membership_required,campaign_condition,quality_status)
 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""",
 (data.period,data.item_code,data.vendor,data.product_description,data.region,data.channel,data.quantity,data.unit,data.price_try,int(data.in_stock),data.shipping_try,data.source_url,str(data.observed_at),int(data.membership_required),data.campaign_condition))
 conn.commit(); oid=cur.lastrowid; conn.close(); return oid

def set_observation_status(observation_id: int, status: str, db_path=None):
 if status not in {"approved","rejected","pending"}: raise ValueError("status approved, rejected veya pending olmalı.")
 conn=connect(db_path); cur=conn.execute("UPDATE observations SET quality_status=? WHERE id=?",(status,observation_id))
 conn.commit(); conn.close()
 if not cur.rowcount: raise KeyError(f"Gözlem bulunamadı: {observation_id}")

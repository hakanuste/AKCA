from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from .db import connect

UNIT_FACTORS = {
    "g": ("kg", 0.001), "gr": ("kg", 0.001), "gram": ("kg", 0.001),
    "kg": ("kg", 1.0), "kilogram": ("kg", 1.0),
    "ml": ("l", 0.001), "millilitre": ("l", 0.001), "milliliter": ("l", 0.001),
    "l": ("l", 1.0), "lt": ("l", 1.0), "litre": ("l", 1.0), "liter": ("l", 1.0),
    "adet": ("adet", 1.0), "ad": ("adet", 1.0), "piece": ("adet", 1.0),
    "pcs": ("adet", 1.0), "unit": ("adet", 1.0),
    "m": ("m", 1.0), "metre": ("m", 1.0),
    "m2": ("m2", 1.0), "m²": ("m2", 1.0),
    "m3": ("m3", 1.0), "m³": ("m3", 1.0),
    "saat": ("saat", 1.0), "hour": ("saat", 1.0),
    "servis": ("servis", 1.0), "service": ("servis", 1.0),
}

def normalize_price(price_try: float, shipping_try: float, quantity: float, unit: str) -> tuple[float, str]:
    key = unit.strip().lower()
    if key not in UNIT_FACTORS:
        raise ValueError(
            f"Desteklenmeyen birim: {unit}. Önce birim eşlemesini tanımlayın; ham fiyatı normalize etmeden kıyaslamayın."
        )
    canonical_unit, factor = UNIT_FACTORS[key]
    denominator = quantity * factor
    if denominator <= 0:
        raise ValueError("Normalize edilen miktar sıfırdan büyük olmalı.")
    # Delivery remains a separately reported purchase cost; it is not part of the product unit price.
    return price_try / denominator, canonical_unit

class PriceObservation(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    item_code: str = Field(pattern=r"^\d{7}$")
    variant_key: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]+$")
    vendor: str = Field(min_length=2, max_length=160)
    product_description: str = Field(min_length=2, max_length=500)
    region: str = Field(min_length=2, max_length=120)
    channel: str = Field(min_length=2, max_length=60)
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=24)
    price_try: float = Field(gt=0)
    in_stock: bool = True
    shipping_try: float = Field(default=0, ge=0)
    source_url: str = Field(min_length=8, max_length=2048)
    observed_at: datetime
    membership_required: bool = False
    campaign_condition: str | None = Field(default=None, max_length=500)

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at saat dilimi içermeli.")
        return value

    @field_validator("source_url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("source_url geçerli bir HTTP/HTTPS adresi olmalı.")
        return value

    @field_validator("vendor", "product_description", "region", "channel", "unit")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def period_matches_observation(self):
        if self.observed_at.strftime("%Y-%m") != self.period:
            raise ValueError("observed_at tarihi, period ayı ile aynı olmalı.")
        return self

def add_observation(data: PriceObservation, db_path=None) -> int:
    normalized_price, normalized_unit = normalize_price(
        data.price_try, data.shipping_try, data.quantity, data.unit
    )
    conn = connect(db_path)
    exists = conn.execute(
        "SELECT 1 FROM item_variants WHERE item_code=? AND variant_key=? AND is_active=1",
        (data.item_code, data.variant_key.lower()),
    ).fetchone()
    if not exists:
        conn.close()
        raise KeyError(
            f"Aktif varyant bulunamadı: {data.item_code}/{data.variant_key}. Önce varyant tanımlanmalı."
        )
    cur = conn.execute(
        """
        INSERT INTO observations(
            period,item_code,variant_key,vendor,product_description,region,channel,
            quantity,unit,normalized_unit,price_try,normalized_price_try,in_stock,
            shipping_try,source_url,observed_at,membership_required,campaign_condition,
            quality_status
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')
        """,
        (
            data.period, data.item_code, data.variant_key.lower(), data.vendor.strip(),
            data.product_description.strip(), data.region.strip(), data.channel.strip(),
            data.quantity, data.unit, normalized_unit, data.price_try, normalized_price,
            int(data.in_stock), data.shipping_try, data.source_url,
            data.observed_at.isoformat(), int(data.membership_required), data.campaign_condition,
        ),
    )
    conn.commit()
    observation_id = cur.lastrowid
    conn.close()
    return int(observation_id)

def set_observation_status(
    observation_id: int, status: str, review_note: str | None = None, db_path=None
) -> None:
    if status not in {"approved", "rejected", "pending"}:
        raise ValueError("status approved, rejected veya pending olmalı.")
    conn = connect(db_path)
    cur = conn.execute(
        "UPDATE observations SET quality_status=?, review_note=? WHERE id=?",
        (status, review_note, observation_id),
    )
    conn.commit()
    conn.close()
    if not cur.rowcount:
        raise KeyError(f"Gözlem bulunamadı: {observation_id}")

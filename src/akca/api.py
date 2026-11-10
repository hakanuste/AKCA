import hmac
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import API_KEY, CORS_ORIGINS
from .db import connect
from .index import calculate_month, check_weights
from .ingest import add_variant, import_items
from .pricing import PriceObservation, add_observation, set_observation_status

@asynccontextmanager
async def lifespan(_: FastAPI):
    import_items()
    yield

app = FastAPI(
    title="AKÇA API",
    version="0.1.0",
    description=(
        "AKÇA bağımsız finansal araştırma sistemi. Bu ilk sürüm fiyat gözlemleri, "
        "ürün eşleştirme ve sabit sepet endeks altyapısını içerir."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-AKCA-API-Key"],
)

class VariantCreate(BaseModel):
    variant_key: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]+$")
    label: str = Field(min_length=2, max_length=500)
    within_item_weight_percent: float = Field(ge=0, le=100)
    weight_source: str = Field(min_length=3, max_length=1000)
    weight_verified: bool = False

class ObservationReview(BaseModel):
    status: str = Field(pattern=r"^(approved|rejected|pending)$")
    review_note: str | None = Field(default=None, max_length=1000)

def require_api_key(
    x_akca_api_key: Annotated[str | None, Header()] = None,
) -> None:
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Yazma işlemleri kapalı. AKCA_API_KEY ortam değişkenini ayarlayın.",
        )
    if not x_akca_api_key or not hmac.compare_digest(x_akca_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Geçersiz veya eksik API anahtarı.")

AdminKey = Annotated[None, Depends(require_api_key)]

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "AKÇA",
        "version": app.version,
        "independent_project": True,
        "write_api_enabled": bool(API_KEY),
    }

@app.get("/reference/source")
def reference_source():
    return {
        "dataset": "TÜİK 2022 madde listesi",
        "item_count": 409,
        "source_workbook": "AKCA_TUIK_2022_Sepeti_Aylik_Fiyat_Takip_Sablonu.xlsx",
        "price_history_imported": False,
        "item_weights_imported": False,
        "weight_status": "unverified",
        "note": (
            "Bu referans dosyası 2022 madde kodları ve adlarını taşır. "
            "2022 madde ağırlıkları kaynağın içinde bulunmadığından endeks için ayrıca "
            "resmî ağırlık kaynağı ve eşleştirme doğrulaması gerekir."
        ),
    }

@app.get("/items")
def items(
    q: str | None = Query(default=None, max_length=120),
    group: str | None = Query(default=None, max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    where = []
    params: list[object] = []
    if q:
        where.append("(item_code LIKE ? OR name_tr LIKE ? OR name_en LIKE ?)")
        term = f"%{q.strip()}%"
        params.extend([term, term, term])
    if group:
        where.append("group_name=?")
        params.append(group)
    clause = " WHERE " + " AND ".join(where) if where else ""
    conn = connect()
    total = conn.execute(f"SELECT COUNT(*) FROM items{clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM items{clause} ORDER BY item_code LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    conn.close()
    return {"total": total, "offset": offset, "limit": limit, "items": [dict(row) for row in rows]}

@app.get("/items/{item_code}/variants")
def get_variants(item_code: str):
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM item_variants WHERE item_code=? ORDER BY variant_key",
        (item_code.zfill(7),),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/items/{item_code}/variants", dependencies=[Depends(require_api_key)], status_code=201)
def create_variant(item_code: str, payload: VariantCreate):
    try:
        add_variant(
            item_code, payload.variant_key, payload.label,
            payload.within_item_weight_percent, payload.weight_source,
            payload.weight_verified,
        )
        return {"item_code": item_code.zfill(7), "variant_key": payload.variant_key.lower(), "created": True}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/weights/status")
def weights_status():
    return check_weights()

@app.post("/observations", dependencies=[Depends(require_api_key)], status_code=201)
def create_observation(payload: PriceObservation):
    try:
        observation_id = add_observation(payload)
        return {"observation_id": observation_id, "quality_status": "pending"}
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if "UNIQUE constraint" in str(exc):
            raise HTTPException(status_code=409, detail="Bu fiyat gözlemi zaten kayıtlı.") from exc
        raise


@app.get("/observations", dependencies=[Depends(require_api_key)])
def observations(
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    status: str | None = Query(default=None, pattern=r"^(pending|approved|rejected)$"),
    item_code: str | None = Query(default=None, pattern=r"^\d{7}$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    filters = []
    params: list[object] = []
    if period:
        filters.append("period=?")
        params.append(period)
    if status:
        filters.append("quality_status=?")
        params.append(status)
    if item_code:
        filters.append("item_code=?")
        params.append(item_code)
    where = " WHERE " + " AND ".join(filters) if filters else ""
    conn = connect()
    total = conn.execute(f"SELECT COUNT(*) FROM observations{where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM observations{where} ORDER BY observed_at DESC, id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    conn.close()
    return {"total": total, "offset": offset, "limit": limit, "observations": [dict(row) for row in rows]}

@app.patch(
    "/observations/{observation_id}/review",
    dependencies=[Depends(require_api_key)],
)
def review_observation(observation_id: int, payload: ObservationReview):
    try:
        set_observation_status(observation_id, payload.status, payload.review_note)
        return {
            "observation_id": observation_id,
            "quality_status": payload.status,
            "review_note": payload.review_note,
        }
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/index/{period}", dependencies=[Depends(require_api_key)])
def run_index(period: str):
    try:
        return calculate_month(period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/stats/{period}")
def get_period_stats(period: str):
    conn = connect()
    run = conn.execute("SELECT * FROM index_runs WHERE period=?", (period,)).fetchone()
    rows = conn.execute(
        "SELECT * FROM item_monthly_stats WHERE period=? ORDER BY item_code",
        (period,),
    ).fetchall()
    conn.close()
    return {
        "period": period,
        "index_run": dict(run) if run else None,
        "items": [dict(row) for row in rows],
    }

@app.get("/dashboard/summary")
def dashboard_summary():
    conn = connect()
    item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    variant_count = conn.execute(
        "SELECT COUNT(*) FROM item_variants WHERE is_active=1"
    ).fetchone()[0]
    pending_count = conn.execute(
        "SELECT COUNT(*) FROM observations WHERE quality_status='pending'"
    ).fetchone()[0]
    latest_run = conn.execute(
        "SELECT * FROM index_runs ORDER BY period DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "item_count": item_count,
        "active_variant_count": variant_count,
        "pending_observation_count": pending_count,
        "weight_readiness": check_weights()["ready"],
        "latest_index_run": dict(latest_run) if latest_run else None,
    }

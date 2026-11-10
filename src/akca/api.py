from __future__ import annotations

import hmac
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analysis.dollar import dollar_performance
from .analysis.engine import run_company_research
from .analysis.institutional import (
    add_broker_research, add_forecast_outcome, broker_consensus,
)
from .analysis.ipo import add_ipo, ipo_performance
from .analysis.portfolio import analyze_portfolio
from .analysis.screener import screen_symbols
from .config import API_KEY, CORS_ORIGINS, ROOT
from .db import connect
from .index import calculate_month, check_weights
from .ingest import add_variant, import_items
from .pricing import PriceObservation, add_observation, set_observation_status
from .providers.coingecko import fetch_coin, search_coin
from .providers.fred import fetch_macro

@asynccontextmanager
async def lifespan(_: FastAPI):
    import_items()
    yield

app = FastAPI(
    title="AKÇA Financial Research API",
    version="0.2.0",
    description=(
        "Independent financial research: sourced company data, valuation, technical analysis, "
        "institutional research, macro, crypto, IPOs and portfolio risk."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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

class WatchlistCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)

class BrokerResearchCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    institution: str = Field(min_length=2, max_length=160)
    analyst: str | None = Field(default=None, max_length=160)
    recommendation: str
    target_price: float | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, max_length=8)
    published_at: str
    report_url: str = Field(min_length=8, max_length=2048)
    source_name: str = Field(min_length=2, max_length=160)
    dependency_group: str | None = Field(default=None, max_length=160)
    verified: bool = False
    reference_price_at_publication: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=2000)

class BrokerOutcomeCreate(BaseModel):
    broker_research_id: int = Field(gt=0)
    evaluation_date: str
    reference_price: float = Field(gt=0)
    actual_price: float = Field(gt=0)
    notes: str | None = None

class PortfolioCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    base_currency: str = Field(default="TRY", min_length=3, max_length=3)

class PositionCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    quantity: float = Field(gt=0)
    average_cost: float | None = Field(default=None, gt=0)
    cost_currency: str | None = Field(default=None, min_length=3, max_length=3)

class IPOCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    company_name: str = Field(min_length=2, max_length=200)
    offer_date: str
    offer_price: float = Field(gt=0)
    offer_currency: str = Field(min_length=3, max_length=3)
    source_url: str = Field(min_length=8, max_length=2048)
    source_name: str = Field(min_length=2, max_length=160)
    verified: bool = False
    shares_offered: float | None = Field(default=None, gt=0)
    notes: str | None = None

def require_api_key(x_akca_api_key: Annotated[str | None, Header()] = None) -> None:
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Yazma işlemleri kapalı. .env dosyasında AKCA_API_KEY tanımlayın.",
        )
    if not x_akca_api_key or not hmac.compare_digest(x_akca_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Geçersiz veya eksik AKÇA API anahtarı.")

AdminKey = Annotated[None, Depends(require_api_key)]

@app.get("/health")
def health():
    conn = connect()
    item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.close()
    return {
        "status": "ok",
        "service": "AKÇA",
        "version": app.version,
        "independent_project": True,
        "reference_item_count": item_count,
        "write_api_enabled": bool(API_KEY),
    }

@app.get("/api/status")
def system_status():
    return {
        "product": "AKÇA",
        "release": "0.2.0-alpha",
        "mode": "read_only_research_plus_local_authenticated_data_entry",
        "modules": {
            "company_research": True,
            "market_prices_and_technicals": True,
            "sec_edgar_filings_and_xbrl": True,
            "value_screener": True,
            "institutional_research_register": True,
            "broker_forecast_accuracy_tracking": True,
            "dollar_performance": True,
            "crypto_market_data": True,
            "macro_data": True,
            "ipo_performance_register": True,
            "portfolio_risk_summary": True,
            "independent_fixed_basket_price_index": True,
        },
        "providers": {
            "yahoo_finance": "unofficial community-accessed web interface; not a licensed real-time feed",
            "sec_edgar": "public API; U.S. filer coverage; identified User-Agent and fair-access policy apply",
            "coingecko": "public API; Demo API key is recommended for stable use",
            "fred": "API key required",
            "bist_kap": "not yet integrated; source-backed manual records and company filings are supported only where explicitly available",
        },
        "write_api_enabled": bool(API_KEY),
        "notice": "This is a research alpha. Recommendations are not calibrated by a completed transaction-cost-aware backtest.",
    }

@app.get("/api/research/{symbol}")
def research_company(
    symbol: str,
    refresh: bool = Query(default=False),
):
    try:
        return run_company_research(symbol, force_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Veri sağlayıcılarından araştırma verisi alınamadı: {type(exc).__name__}: {str(exc)[:250]}",
        ) from exc

@app.get("/api/reports/{symbol}/latest")
def latest_report(symbol: str):
    conn = connect()
    row = conn.execute(
        "SELECT report_json FROM research_reports WHERE symbol=? ORDER BY created_at DESC LIMIT 1",
        (symbol.strip().upper(),),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Bu sembol için kayıtlı araştırma raporu bulunamadı.")
    return json.loads(row["report_json"])

@app.get("/api/screener")
def value_screener(
    symbols: str = Query(min_length=1, max_length=1000),
    refresh: bool = False,
):
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    try:
        return screen_symbols(requested, force_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/analysis/dollar-performance/{symbol}")
def dollar_performance_route(symbol: str):
    try:
        return dollar_performance(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Döviz/fiyat verisi alınamadı: {type(exc).__name__}: {str(exc)[:220]}") from exc

@app.get("/api/macro")
def macro_data(
    series: str | None = Query(default=None, max_length=300),
    observations: int = Query(default=24, ge=1, le=180),
):
    ids = [item.strip().upper() for item in series.split(",")] if series else None
    return fetch_macro(ids, observations)

@app.get("/api/crypto/search")
def crypto_search(q: str = Query(min_length=1, max_length=120)):
    try:
        return search_coin(q)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"CoinGecko arama hatası: {type(exc).__name__}: {str(exc)[:200]}") from exc

@app.get("/api/crypto/{coin_id}")
def crypto_asset(coin_id: str, currency: str = Query(default="usd", min_length=3, max_length=8)):
    try:
        return fetch_coin(coin_id, currency)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"CoinGecko veri hatası: {type(exc).__name__}: {str(exc)[:200]}") from exc

@app.get("/api/reference/source")
def reference_source():
    return {
        "dataset": "TÜİK 2022 madde listesi",
        "item_count": 409,
        "price_history_imported": False,
        "item_weights_imported": False,
        "weight_status": "unverified",
        "note": "2022 ağırlıkları resmî kaynakla doğrulanmadan AKÇA endeksi yayınlanmaz.",
    }

@app.get("/api/items")
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

@app.get("/api/items/{item_code}/variants")
def get_variants(item_code: str):
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM item_variants WHERE item_code=? ORDER BY variant_key",
        (item_code.zfill(7),),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/items/{item_code}/variants", dependencies=[Depends(require_api_key)], status_code=201)
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

@app.get("/api/weights/status")
def weights_status():
    return check_weights()

@app.post("/api/observations", dependencies=[Depends(require_api_key)], status_code=201)
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

@app.get("/api/observations", dependencies=[Depends(require_api_key)])
def observations(
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    status: str | None = Query(default=None, pattern=r"^(pending|approved|rejected)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    where = []
    params: list[object] = []
    if period:
        where.append("period=?")
        params.append(period)
    if status:
        where.append("quality_status=?")
        params.append(status)
    clause = " WHERE " + " AND ".join(where) if where else ""
    conn = connect()
    total = conn.execute(f"SELECT COUNT(*) FROM observations{clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM observations{clause} ORDER BY observed_at DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    conn.close()
    return {"total": total, "offset": offset, "limit": limit, "observations": [dict(row) for row in rows]}

@app.patch("/api/observations/{observation_id}/review", dependencies=[Depends(require_api_key)])
def review_observation(observation_id: int, payload: ObservationReview):
    try:
        set_observation_status(observation_id, payload.status, payload.review_note)
        return {"observation_id": observation_id, "quality_status": payload.status}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/index/{period}", dependencies=[Depends(require_api_key)])
def run_index(period: str):
    try:
        return calculate_month(period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/stats/{period}")
def get_period_stats(period: str):
    conn = connect()
    run = conn.execute("SELECT * FROM index_runs WHERE period=?", (period,)).fetchone()
    rows = conn.execute(
        "SELECT * FROM item_monthly_stats WHERE period=? ORDER BY item_code", (period,)
    ).fetchall()
    conn.close()
    return {
        "period": period,
        "index_run": dict(run) if run else None,
        "items": [dict(row) for row in rows],
    }

@app.get("/api/dashboard/summary")
def dashboard_summary():
    conn = connect()
    item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    variant_count = conn.execute("SELECT COUNT(*) FROM item_variants WHERE is_active=1").fetchone()[0]
    pending_count = conn.execute("SELECT COUNT(*) FROM observations WHERE quality_status='pending'").fetchone()[0]
    latest_run = conn.execute("SELECT * FROM index_runs ORDER BY period DESC LIMIT 1").fetchone()
    conn.close()
    return {
        "item_count": item_count,
        "active_variant_count": variant_count,
        "pending_observation_count": pending_count,
        "weight_readiness": check_weights()["ready"],
        "latest_index_run": dict(latest_run) if latest_run else None,
    }

@app.get("/api/watchlist")
def get_watchlist():
    conn = connect()
    rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/watchlist", dependencies=[Depends(require_api_key)], status_code=201)
def add_watchlist_item(payload: WatchlistCreate):
    symbol = payload.symbol.strip().upper()
    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO watchlist(symbol,notes) VALUES(?,?)",
        (symbol, payload.notes),
    )
    conn.commit()
    conn.close()
    return {"symbol": symbol, "saved": True}

@app.delete("/api/watchlist/{symbol}", dependencies=[Depends(require_api_key)])
def remove_watchlist_item(symbol: str):
    conn = connect()
    cur = conn.execute("DELETE FROM watchlist WHERE symbol=?", (symbol.strip().upper(),))
    conn.commit()
    conn.close()
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail="Sembol izleme listesinden bulunamadı.")
    return {"symbol": symbol.upper(), "deleted": True}

@app.post("/api/institutional/research", dependencies=[Depends(require_api_key)], status_code=201)
def create_broker_research(payload: BrokerResearchCreate):
    try:
        record_id = add_broker_research(
            payload.symbol, payload.institution, payload.recommendation,
            payload.target_price, payload.currency, payload.published_at,
            payload.report_url, payload.source_name, payload.dependency_group,
            payload.verified, payload.reference_price_at_publication,
            payload.analyst, payload.notes,
        )
        return {"id": record_id, "created": True}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/institutional/consensus/{symbol}")
def get_broker_consensus(symbol: str):
    return broker_consensus(symbol)

@app.post("/api/institutional/outcomes", dependencies=[Depends(require_api_key)], status_code=201)
def record_broker_outcome(payload: BrokerOutcomeCreate):
    try:
        outcome_id = add_forecast_outcome(
            payload.broker_research_id, payload.evaluation_date,
            payload.reference_price, payload.actual_price, payload.notes,
        )
        return {"outcome_id": outcome_id, "created": True}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/ipo", dependencies=[Depends(require_api_key)], status_code=201)
def create_ipo(payload: IPOCreate):
    try:
        add_ipo(
            payload.symbol, payload.company_name, payload.offer_date,
            payload.offer_price, payload.offer_currency, payload.source_url,
            payload.source_name, payload.verified, payload.shares_offered, payload.notes,
        )
        return {"symbol": payload.symbol.upper(), "saved": True}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/ipo/{symbol}")
def ipo_result(symbol: str):
    try:
        return ipo_performance(symbol)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"IPO fiyat verisi alınamadı: {type(exc).__name__}") from exc

@app.post("/api/portfolios", dependencies=[Depends(require_api_key)], status_code=201)
def create_portfolio(payload: PortfolioCreate):
    portfolio_id = str(uuid4())
    conn = connect()
    conn.execute(
        "INSERT INTO portfolios(portfolio_id,name,base_currency) VALUES(?,?,?)",
        (portfolio_id, payload.name, payload.base_currency.upper()),
    )
    conn.commit()
    conn.close()
    return {"portfolio_id": portfolio_id, "name": payload.name, "base_currency": payload.base_currency.upper()}

@app.get("/api/portfolios")
def list_portfolios():
    conn = connect()
    rows = conn.execute("SELECT * FROM portfolios ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/portfolios/{portfolio_id}/positions", dependencies=[Depends(require_api_key)], status_code=201)
def add_portfolio_position(portfolio_id: str, payload: PositionCreate):
    conn = connect()
    exists = conn.execute("SELECT 1 FROM portfolios WHERE portfolio_id=?", (portfolio_id,)).fetchone()
    if not exists:
        conn.close()
        raise HTTPException(status_code=404, detail="Portföy bulunamadı.")
    conn.execute(
        """
        INSERT INTO portfolio_positions(portfolio_id,symbol,quantity,average_cost,cost_currency)
        VALUES(?,?,?,?,?)
        ON CONFLICT(portfolio_id,symbol) DO UPDATE SET
            quantity=excluded.quantity,average_cost=excluded.average_cost,
            cost_currency=excluded.cost_currency,updated_at=CURRENT_TIMESTAMP
        """,
        (portfolio_id, payload.symbol.upper(), payload.quantity, payload.average_cost, payload.cost_currency),
    )
    conn.commit()
    conn.close()
    return {"portfolio_id": portfolio_id, "symbol": payload.symbol.upper(), "saved": True}

@app.get("/api/portfolios/{portfolio_id}/analysis")
def portfolio_analysis(portfolio_id: str):
    conn = connect()
    portfolio = conn.execute("SELECT * FROM portfolios WHERE portfolio_id=?", (portfolio_id,)).fetchone()
    rows = conn.execute(
        "SELECT symbol,quantity,average_cost,cost_currency FROM portfolio_positions WHERE portfolio_id=?",
        (portfolio_id,),
    ).fetchall()
    conn.close()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portföy bulunamadı.")
    if not rows:
        raise HTTPException(status_code=400, detail="Portföyde henüz pozisyon yok.")
    try:
        result = analyze_portfolio([dict(row) for row in rows], portfolio["base_currency"])
        result["portfolio"] = dict(portfolio)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Portföy fiyat analizi tamamlanamadı: {type(exc).__name__}") from exc

@app.get("/api/company-research-checklist")
def research_checklist_catalog():
    from .analysis.checklist import CHECKLIST
    return [{"step": i + 1, "task": item} for i, item in enumerate(CHECKLIST)]

# The public introduction and local analysis terminal are served after API routes.
app.mount("/", StaticFiles(directory=str(Path(ROOT) / "web"), html=True), name="web")

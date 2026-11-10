from fastapi import FastAPI, HTTPException
from .db import connect
from .ingest import import_items
from .pricing import PriceObservation, add_observation, set_observation_status
from .index import calculate_month, check_weights

app=FastAPI(title="AKÇA API",version="0.1.0",description="Independent financial research and direct-market price intelligence.")
@app.on_event("startup")
def startup(): import_items()
@app.get("/health")
def health(): return {"status":"ok","service":"AKÇA","independent_project":True}
@app.get("/items")
def items():
 conn=connect(); rows=conn.execute("SELECT * FROM items ORDER BY item_code").fetchall(); conn.close(); return [dict(r) for r in rows]
@app.get("/weights/status")
def weights_status(): return check_weights()
@app.post("/observations")
def create_observation(payload: PriceObservation):
 try: return {"observation_id":add_observation(payload),"status":"recorded_pending_review"}
 except (KeyError,ValueError) as e: raise HTTPException(status_code=400,detail=str(e))
 except Exception as e:
  if "UNIQUE constraint" in str(e): raise HTTPException(status_code=409,detail="Bu gözlem zaten kayıtlı.")
  raise
@app.post("/index/{period}")
def run_index(period: str):
 try: return calculate_month(period)
 except Exception as e: raise HTTPException(status_code=400,detail=str(e))
@app.patch("/observations/{observation_id}/status")
def review_observation(observation_id: int,status: str):
 try: set_observation_status(observation_id,status); return {"observation_id":observation_id,"quality_status":status}
 except (KeyError,ValueError) as e: raise HTTPException(status_code=400,detail=str(e))

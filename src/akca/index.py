from statistics import mean, median
from .db import connect
from .config import MIN_SELLERS

def check_weights(db_path=None):
 conn=connect(db_path)
 rows=conn.execute("SELECT item_code,name_tr,weight_percent,weight_verified FROM items ORDER BY item_code").fetchall()
 missing=[dict(r) for r in rows if r["weight_percent"] is None or not r["weight_verified"]]
 total=sum(r["weight_percent"] or 0 for r in rows if r["weight_verified"])
 conn.close()
 return {"item_count":len(rows),"verified_weight_count":len(rows)-len(missing),"missing_or_unverified":missing,"verified_weight_total_pct":round(total,6),"ready":len(missing)==0 and abs(total-100)<0.01}

def calculate_month(period: str, db_path=None, min_sellers: int=MIN_SELLERS):
 conn=connect(db_path)
 items=conn.execute("SELECT * FROM items ORDER BY item_code").fetchall()
 missing_weights=[r["item_code"] for r in items if r["weight_percent"] is None or not r["weight_verified"]]
 rows=[]
 for item in items:
  obs=conn.execute("SELECT vendor,price_try,shipping_try FROM observations WHERE period=? AND item_code=? AND in_stock=1 AND quality_status='approved' AND membership_required=0",(period,item["item_code"])).fetchall()
  prices=[float(o["price_try"])+float(o["shipping_try"]) for o in obs]
  if not prices: continue
  prev=conn.execute("SELECT mean_price FROM item_monthly_stats WHERE item_code=? AND period=(SELECT MAX(period) FROM item_monthly_stats WHERE item_code=? AND period < ?)",(item["item_code"],item["item_code"],period)).fetchone()
  avg=mean(prices); change=((avg/prev["mean_price"])-1)*100 if prev and prev["mean_price"] else None
  seller_count=len(set(o["vendor"] for o in obs)); sufficient=seller_count>=min_sellers
  contribution=(change*item["weight_percent"]/100 if change is not None and item["weight_verified"] else None)
  stats=(period,item["item_code"],seller_count,min(prices),max(prices),avg,median(prices),float(prev["mean_price"]) if prev else None,change,item["weight_percent"],contribution,int(sufficient),None if sufficient else f"Satıcı sayısı {seller_count}; minimum {min_sellers}")
  conn.execute("INSERT OR REPLACE INTO item_monthly_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",stats)
  rows.append({"item_code":item["item_code"],"seller_count":seller_count,"min":stats[3],"max":stats[4],"mean":stats[5],"median":stats[6],"monthly_change_pct":change,"weight_pct":item["weight_percent"],"sufficient":sufficient})
 coverage=sum((r["weight_percent"] or 0) for r in items if r["weight_verified"] and any(x["item_code"]==r["item_code"] and x["sufficient"] for x in rows))
 if missing_weights: status="blocked_missing_weights"; inflation=None; note=f"{len(missing_weights)} maddede ağırlık eksik/doğrulanmamış."
 elif abs(sum(r["weight_percent"] for r in items)-100)>0.01: status="blocked_weight_total"; inflation=None; note="Doğrulanmış madde ağırlıkları toplamı %100 değil."
 elif any(r["monthly_change_pct"] is None or not r["sufficient"] for r in rows) or len(rows)!=len(items): status="blocked_incomplete_prices"; inflation=None; note="Bazı maddelerde önceki ay verisi veya yeterli satıcı fiyatı yok."
 else: inflation=sum(r["monthly_change_pct"]*r["weight_pct"]/100 for r in rows); status="calculated"; note="Sabit 2022 madde ağırlıklarıyla hesaplandı."
 prev_run=conn.execute("SELECT index_value FROM index_runs WHERE period < ? AND status='calculated' ORDER BY period DESC LIMIT 1",(period,)).fetchone()
 index_value=(prev_run["index_value"]*(1+inflation/100) if prev_run and inflation is not None else (100*(1+inflation/100) if inflation is not None else None))
 conn.execute("INSERT OR REPLACE INTO index_runs(period,index_value,monthly_inflation_pct,coverage_weight_pct,status,notes) VALUES(?,?,?,?,?,?)",(period,index_value,inflation,coverage,status,note))
 conn.commit(); conn.close()
 return {"period":period,"status":status,"monthly_inflation_pct":inflation,"index_value":index_value,"coverage_weight_pct":coverage,"item_rows":len(rows),"items_total":len(items),"notes":note}

from __future__ import annotations

from statistics import mean, median

from ..db import connect

VALID_RATINGS = {"BUY", "OUTPERFORM", "HOLD", "NEUTRAL", "UNDERPERFORM", "SELL"}

def add_broker_research(
    symbol: str, institution: str, recommendation: str, target_price: float | None,
    currency: str | None, published_at: str, report_url: str, source_name: str,
    dependency_group: str | None = None, verified: bool = False,
    reference_price_at_publication: float | None = None, analyst: str | None = None,
    notes: str | None = None,
) -> int:
    rating = recommendation.strip().upper()
    if rating not in VALID_RATINGS:
        raise ValueError(f"Geçersiz tavsiye. İzin verilenler: {', '.join(sorted(VALID_RATINGS))}")
    if not report_url.startswith(("https://", "http://")):
        raise ValueError("Rapor URL'si HTTP/HTTPS olmalı.")
    conn = connect()
    cur = conn.execute(
        """
        INSERT INTO broker_research(
            symbol,institution,analyst,recommendation,target_price,currency,
            published_at,report_url,source_name,dependency_group,verified,notes,
            reference_price_at_publication,horizon_days
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            symbol.strip().upper(), institution.strip(), analyst, rating, target_price,
            currency.upper() if currency else None, published_at, report_url,
            source_name, dependency_group, int(verified), notes,
            reference_price_at_publication,
            365,
        ),
    )
    research_id = cur.lastrowid
    conn.execute(
        "INSERT INTO audit_events(event_at,actor,action,object_type,object_id,detail_json) VALUES(datetime('now'),?,?,?,?,?)",
        ("local-user", "create", "broker_research", str(research_id), "{}"),
    )
    conn.commit()
    conn.close()
    return int(research_id)

def add_forecast_outcome(
    broker_research_id: int, evaluation_date: str,
    reference_price: float, actual_price: float, notes: str | None = None,
) -> int:
    if reference_price <= 0 or actual_price <= 0:
        raise ValueError("Fiyatlar sıfırdan büyük olmalı.")
    conn = connect()
    row = conn.execute(
        "SELECT target_price FROM broker_research WHERE id=?",
        (broker_research_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise KeyError("Aracı kurum araştırma kaydı bulunamadı.")
    target = row["target_price"]
    error = (actual_price / target - 1) * 100 if target else None
    realized = (actual_price / reference_price - 1) * 100
    cur = conn.execute(
        """
        INSERT OR REPLACE INTO broker_forecast_outcomes(
            broker_research_id,evaluation_date,reference_price,actual_price,
            target_price_error_pct,realized_return_pct,notes
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (broker_research_id,evaluation_date,reference_price,actual_price,error,realized,notes),
    )
    conn.commit()
    result_id = cur.lastrowid
    conn.close()
    return int(result_id)

def broker_consensus(symbol: str) -> dict:
    conn = connect()
    rows = conn.execute(
        """
        SELECT br.*,
            AVG(ABS(out.target_price_error_pct)) AS mean_abs_target_error_pct,
            COUNT(out.id) AS evaluated_forecasts
        FROM broker_research br
        LEFT JOIN broker_forecast_outcomes out ON out.broker_research_id=br.id
        WHERE br.symbol=?
        GROUP BY br.id
        ORDER BY br.published_at DESC
        """,
        (symbol.strip().upper(),),
    ).fetchall()
    conn.close()
    verified = [dict(r) for r in rows if r["verified"]]
    # A dependency group counts once; unknown dependence is not silently treated as independence.
    independent = []
    used = set()
    for row in verified:
        key = row["dependency_group"] or f"unlinked:{row['institution']}:{row['published_at']}"
        if key in used:
            continue
        used.add(key)
        independent.append(row)

    targets = [float(r["target_price"]) for r in independent if r["target_price"] is not None]
    equal_targets = {
        "count": len(targets),
        "mean": mean(targets) if targets else None,
        "median": median(targets) if targets else None,
        "min": min(targets) if targets else None,
        "max": max(targets) if targets else None,
    }
    rating_map = {
        "BUY": "buy", "OUTPERFORM": "buy",
        "HOLD": "hold", "NEUTRAL": "hold",
        "UNDERPERFORM": "sell", "SELL": "sell",
    }
    distribution = {"buy": 0, "hold": 0, "sell": 0}
    for row in independent:
        category = rating_map.get(row["recommendation"])
        if category:
            distribution[category] += 1

    weighted_targets = []
    for row in independent:
        if row["target_price"] is None:
            continue
        error = row["mean_abs_target_error_pct"]
        # Accuracy weighting only becomes active with at least 3 scored calls.
        if row["evaluated_forecasts"] >= 3 and error is not None:
            weight = 1 / (1 + float(error) / 100)
            weighting = "historical_accuracy"
        else:
            weight = 1.0
            weighting = "equal_fallback_insufficient_track_record"
        weighted_targets.append({
            "target": float(row["target_price"]), "weight": weight,
            "institution": row["institution"], "weighting": weighting,
        })
    total_weight = sum(x["weight"] for x in weighted_targets)
    weighted_mean = (
        sum(x["target"] * x["weight"] for x in weighted_targets) / total_weight
        if total_weight else None
    )
    return {
        "symbol": symbol.strip().upper(),
        "all_records_count": len(rows),
        "verified_records_count": len(verified),
        "independent_verified_record_count": len(independent),
        "equal_weight_target_price": equal_targets,
        "accuracy_weighted_target_price": weighted_mean,
        "recommendation_distribution": distribution,
        "records": independent,
        "methodology_notes": [
            "Yalnızca verified=true olan kayıtlar konsensüse alınır.",
            "Aynı dependency_group içindeki raporlar bağımsız sayılmaz; aynı grup tek rapor olarak sayılır.",
            "Üçten az gerçekleşmiş değerlendirmesi olan kurumda tarihsel doğruluk ağırlığı uygulanmaz; eşit ağırlık kullanılır.",
            "Kur, hedef fiyat ufku ve raporun yayımlandığı günün hisse fiyatı uyumlu değilse hedef fiyatlar birleştirilmemelidir.",
        ],
    }

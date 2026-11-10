from __future__ import annotations

import json
from datetime import date, datetime, timezone
from math import isfinite
from urllib.parse import urlparse

from ..db import connect

ALLOWED_METRICS = {
    "revenue",
    "net_income",
    "operating_cash_flow",
    "capex",
    "total_assets",
    "total_liabilities",
    "cash",
    "long_term_debt",
    "equity",
    "operating_income",
    "diluted_eps",
}
ALLOWED_PERIOD_TYPES = {"annual", "quarterly"}

def import_financial_facts(
    symbol: str,
    source_name: str,
    source_url: str,
    facts: list[dict],
    verified: bool = False,
    notes: str | None = None,
) -> dict:
    ticker = symbol.strip().upper()
    source = source_name.strip()
    parsed = urlparse(source_url)
    if not ticker:
        raise ValueError("Şirket sembolü boş olamaz.")
    if len(ticker) > 40:
        raise ValueError("Sembol 40 karakteri aşamaz.")
    if not source:
        raise ValueError("Kaynak adı zorunludur.")
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("Kaynak URL'si HTTP/HTTPS olmalı.")
    if not facts or len(facts) > 500:
        raise ValueError("Bir aktarımda 1-500 finansal veri satırı olmalı.")

    conn = connect()
    imported = 0
    manual_source = f"manual_import:{source}"
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for row in facts:
        metric = str(row.get("metric_code", "")).strip().lower()
        if metric not in ALLOWED_METRICS:
            conn.rollback()
            conn.close()
            raise ValueError(f"Desteklenmeyen finansal kalem: {metric}")
        period_type = str(row.get("period_type", "annual")).strip().lower()
        if period_type not in ALLOWED_PERIOD_TYPES:
            conn.rollback()
            conn.close()
            raise ValueError("period_type annual veya quarterly olmalı.")
        period_end = str(row.get("period_end", "")).strip()
        try:
            date.fromisoformat(period_end)
            value = float(row["value"])
        except (ValueError, TypeError, KeyError) as exc:
            conn.rollback()
            conn.close()
            raise ValueError("period_end YYYY-AA-GG ve value sayısal olmalı.") from exc
        if not isfinite(value):
            conn.rollback()
            conn.close()
            raise ValueError("Finansal değer sonlu sayı olmalı.")
        currency = row.get("currency")
        unit = row.get("unit")
        if currency is not None:
            currency = str(currency).strip().upper()
            if len(currency) > 12:
                conn.rollback()
                conn.close()
                raise ValueError("Para birimi en fazla 12 karakter olabilir.")
        if unit is not None:
            unit = str(unit).strip()
            if len(unit) > 40:
                conn.rollback()
                conn.close()
                raise ValueError("Birim 40 karakteri aşamaz.")

        conn.execute(
            """
            INSERT OR REPLACE INTO financial_snapshots(
                symbol,metric_code,period_end,period_type,value,currency,unit,
                source,source_url,retrieved_at,verified,notes
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ticker, metric, period_end, period_type, value, currency, unit,
                manual_source, source_url, retrieved_at, int(verified), notes,
            ),
        )
        imported += 1

    conn.execute(
        """
        INSERT INTO audit_events(event_at,actor,action,object_type,object_id,detail_json)
        VALUES(?,?,?,?,?,?)
        """,
        (
            retrieved_at, "local-user", "import", "financial_facts", ticker,
            json.dumps(
                {"source": source, "row_count": imported, "verified_by_user": bool(verified)},
                ensure_ascii=False,
            ),
        ),
    )
    conn.commit()
    conn.close()
    return {
        "symbol": ticker,
        "source_name": source,
        "source_url": source_url,
        "imported_rows": imported,
        "verified_by_user": bool(verified),
        "note": "Verified means the operator confirmed the source document; it is not independent audit assurance.",
    }

def load_verified_annual_facts(symbol: str, db_path=None) -> tuple[dict, list[dict]]:
    conn = connect(db_path)
    rows = conn.execute(
        """
        SELECT metric_code,period_end,value,currency,unit,source,source_url,retrieved_at,notes
        FROM financial_snapshots
        WHERE symbol=? AND period_type='annual' AND verified=1
        ORDER BY period_end DESC
        """,
        (symbol.strip().upper(),),
    ).fetchall()
    conn.close()

    facts: dict[str, list[dict]] = {}
    source_records: dict[tuple[str, str], dict] = {}
    seen_periods: dict[str, set[str]] = {}
    for row in rows:
        seen = seen_periods.setdefault(row["metric_code"], set())
        # Different source documents may contain the same period; use the most
        # recently imported verified fact for that metric/period, never count
        # two versions as current and prior years.
        if row["period_end"] in seen:
            continue
        seen.add(row["period_end"])
        facts.setdefault(row["metric_code"], []).append({
            "value": row["value"],
            "period_end": row["period_end"],
            "unit": row["unit"],
            "currency": row["currency"],
            "source": row["source"],
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "notes": row["notes"],
        })
        key = (row["source"], row["source_url"])
        source_records[key] = {
            "source_id": row["source"],
            "source_name": row["source"].removeprefix("manual_import:"),
            "category": "user_verified_company_financial_import",
            "status": "user_verified",
            "url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "limitations": [
                "The operator marked the source as verified. AKÇA has not independently authenticated the uploaded values.",
                "Annual figures are imported as stated; unit, consolidation scope and accounting basis should be checked against the linked filing.",
            ],
        }
    return facts, list(source_records.values())

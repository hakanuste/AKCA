from datetime import date
from statistics import mean, median

from .config import MIN_SELLERS
from .db import connect

def previous_period(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"

def check_weights(db_path=None) -> dict:
    conn = connect(db_path)
    items = conn.execute("SELECT * FROM items ORDER BY item_code").fetchall()
    missing_items = [
        {"item_code": row["item_code"], "name_tr": row["name_tr"],
         "weight_percent": row["weight_percent"], "weight_verified": bool(row["weight_verified"])}
        for row in items if row["weight_percent"] is None or not row["weight_verified"]
    ]
    item_total = sum(
        float(row["weight_percent"] or 0) for row in items if row["weight_verified"]
    )
    variant_issues = []
    for item in items:
        variants = conn.execute(
            "SELECT * FROM item_variants WHERE item_code=? AND is_active=1",
            (item["item_code"],),
        ).fetchall()
        total = sum(float(v["within_item_weight_percent"]) for v in variants if v["weight_verified"])
        all_verified = bool(variants) and all(v["weight_verified"] for v in variants)
        if not all_verified or abs(total - 100) > 0.01:
            variant_issues.append({
                "item_code": item["item_code"],
                "active_variant_count": len(variants),
                "verified_variant_weight_total_pct": round(total, 6),
            })
    conn.close()
    return {
        "item_count": len(items),
        "verified_item_weight_count": len(items) - len(missing_items),
        "verified_item_weight_total_pct": round(item_total, 6),
        "items_missing_or_unverified": missing_items,
        "items_with_incomplete_variant_weights": variant_issues,
        "ready": (
            bool(items) and not missing_items and not variant_issues
            and abs(item_total - 100) <= 0.01
        ),
    }

def _latest_vendor_prices(conn, period: str, item_code: str, variant_key: str):
    rows = conn.execute(
        """
        SELECT vendor, normalized_price_try, normalized_unit, observed_at
        FROM observations
        WHERE period=? AND item_code=? AND variant_key=?
          AND in_stock=1 AND quality_status='approved' AND membership_required=0
        ORDER BY observed_at DESC, id DESC
        """,
        (period, item_code, variant_key),
    ).fetchall()
    latest = {}
    for row in rows:
        vendor_key = " ".join(row["vendor"].casefold().split())
        if vendor_key not in latest:
            latest[vendor_key] = row
    return list(latest.values())

def calculate_month(period: str, db_path=None, min_sellers: int = MIN_SELLERS) -> dict:
    if len(period) != 7 or period[4] != "-":
        raise ValueError("Dönem YYYY-AA biçiminde olmalı.")
    try:
        date.fromisoformat(period + "-01")
    except ValueError as exc:
        raise ValueError("Geçersiz dönem.") from exc
    prev_period = previous_period(period)
    conn = connect(db_path)
    items = conn.execute("SELECT * FROM items ORDER BY item_code").fetchall()
    item_results = []
    total_verified_weight = 0.0
    coverage_weight = 0.0
    incomplete = []

    for item in items:
        item_weight = item["weight_percent"]
        if item_weight is not None and item["weight_verified"]:
            total_verified_weight += float(item_weight)
        variants = conn.execute(
            "SELECT * FROM item_variants WHERE item_code=? AND is_active=1 ORDER BY variant_key",
            (item["item_code"],),
        ).fetchall()
        variant_weight_total = sum(
            float(v["within_item_weight_percent"]) for v in variants if v["weight_verified"]
        )
        variant_ok = (
            bool(variants) and all(v["weight_verified"] for v in variants)
            and abs(variant_weight_total - 100) <= 0.01
        )
        variant_changes = []
        current_prices_all = []
        seller_names = set()
        normalized_units = set()
        if variant_ok:
            for variant in variants:
                current = _latest_vendor_prices(conn, period, item["item_code"], variant["variant_key"])
                previous = _latest_vendor_prices(conn, prev_period, item["item_code"], variant["variant_key"])
                current_prices = [float(r["normalized_price_try"]) for r in current]
                previous_prices = [float(r["normalized_price_try"]) for r in previous]
                current_units = {r["normalized_unit"] for r in current}
                previous_units = {r["normalized_unit"] for r in previous}
                unit_ok = len(current_units) == 1 and current_units == previous_units
                seller_count = len(current)
                sufficient = (
                    seller_count >= min_sellers and len(previous) >= min_sellers
                    and unit_ok and bool(current_prices) and bool(previous_prices)
                )
                avg = mean(current_prices) if current_prices else None
                prev_avg = mean(previous_prices) if previous_prices else None
                change = ((avg / prev_avg) - 1) * 100 if sufficient and prev_avg else None
                unit = next(iter(current_units)) if len(current_units) == 1 else (
                    next(iter(previous_units)) if len(previous_units) == 1 else "mixed"
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO variant_monthly_stats(
                        period,item_code,variant_key,seller_count,min_price,max_price,
                        mean_price,median_price,previous_mean_price,monthly_change_pct,
                        normalized_unit,sufficient_data,notes
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        period, item["item_code"], variant["variant_key"], seller_count,
                        min(current_prices) if current_prices else 0,
                        max(current_prices) if current_prices else 0,
                        avg if avg is not None else 0,
                        median(current_prices) if current_prices else 0,
                        prev_avg, change, unit, int(sufficient),
                        None if sufficient else "Cari/önceki ayda yeterli satıcı veya tutarlı birim yok.",
                    ),
                )
                if not sufficient:
                    incomplete.append(f"{item['item_code']}/{variant['variant_key']}")
                else:
                    variant_changes.append(
                        change * float(variant["within_item_weight_percent"]) / 100
                    )
                    current_prices_all.extend(current_prices)
                    seller_names.update(r["vendor"].casefold() for r in current)
                    normalized_units.add(unit)
        else:
            incomplete.append(f"{item['item_code']}: varyant ağırlıkları eksik/doğrulanmamış")

        item_sufficient = (
            variant_ok and len(variant_changes) == len(variants)
            and item_weight is not None and bool(item["weight_verified"])
            and len(normalized_units) <= 1
        )
        item_change = sum(variant_changes) if item_sufficient else None
        item_unit = next(iter(normalized_units)) if len(normalized_units) == 1 else None
        weighted_contribution = (
            item_change * float(item_weight) / 100 if item_sufficient else None
        )
        if item_sufficient:
            coverage_weight += float(item_weight)
        else:
            if item_weight is None or not item["weight_verified"]:
                incomplete.append(f"{item['item_code']}: TÜİK 2022 madde ağırlığı doğrulanmamış")
            if len(normalized_units) > 1:
                incomplete.append(f"{item['item_code']}: varyantların normalize birimleri farklı")
        conn.execute(
            """
            INSERT OR REPLACE INTO item_monthly_stats(
                period,item_code,variant_count,seller_count,min_price,max_price,
                mean_price,median_price,monthly_change_pct,weight_percent,
                weighted_contribution_pp,sufficient_data,normalized_unit,notes
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                period, item["item_code"], len(variants), len(seller_names),
                min(current_prices_all) if current_prices_all else None,
                max(current_prices_all) if current_prices_all else None,
                mean(current_prices_all) if current_prices_all else None,
                median(current_prices_all) if current_prices_all else None,
                item_change, item_weight, weighted_contribution, int(item_sufficient),
                item_unit, None if item_sufficient else "Madde verisi veya ağırlık doğrulaması eksik.",
            ),
        )
        item_results.append({
            "item_code": item["item_code"], "name_tr": item["name_tr"],
            "monthly_change_pct": item_change, "weight_percent": item_weight,
            "weighted_contribution_pp": weighted_contribution, "sufficient": item_sufficient,
            "variant_count": len(variants), "seller_count": len(seller_names),
            "normalized_unit": item_unit,
        })

    all_items_ready = (
        bool(items) and len(item_results) == len(items)
        and all(r["sufficient"] for r in item_results)
        and abs(total_verified_weight - 100) <= 0.01
    )
    if not all(items):
        status, inflation, note = "blocked_no_items", None, "Referans madde listesi yüklenmemiş."
    elif abs(total_verified_weight - 100) > 0.01:
        status, inflation, note = "blocked_item_weights", None, (
            f"Doğrulanmış madde ağırlıkları toplamı %{total_verified_weight:.4f}; %100 olmalı."
        )
    elif not all_items_ready:
        status, inflation, note = "blocked_incomplete_coverage", None, (
            f"{len(incomplete)} veri/temsil eksiği var; kapsam tamamlanmadan endeks hesaplanmadı."
        )
    else:
        status = "calculated"
        inflation = sum(float(r["weighted_contribution_pp"]) for r in item_results)
        note = "Doğrulanmış sabit sepet ve varyant ağırlıklarıyla hesaplandı."

    previous_run = conn.execute(
        "SELECT index_value FROM index_runs WHERE period=? AND status='calculated'",
        (prev_period,),
    ).fetchone()
    index_value = (
        float(previous_run["index_value"]) * (1 + inflation / 100)
        if status == "calculated" and previous_run and previous_run["index_value"] is not None
        else None
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO index_runs(
            period,index_value,monthly_inflation_pct,coverage_weight_pct,status,notes
        ) VALUES(?,?,?,?,?,?)
        """,
        (period, index_value, inflation, coverage_weight, status, note),
    )
    conn.commit()
    conn.close()
    return {
        "period": period, "previous_period": prev_period, "status": status,
        "monthly_inflation_pct": inflation, "index_value": index_value,
        "coverage_weight_pct": round(coverage_weight, 6),
        "item_rows": len(item_results), "items_total": len(items),
        "incomplete_count": len(incomplete), "incomplete_examples": incomplete[:25],
        "notes": note,
    }

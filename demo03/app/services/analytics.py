from datetime import date, timedelta

import pandas as pd

from app.db import get_db


def _split_csv(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def build_filters(args):
    filters = {
        "city": _split_csv(args.get("city")),
        "district": _split_csv(args.get("district")),
        "layout": _split_csv(args.get("layout")),
        "status": _split_csv(args.get("status")),
        "keyword": (args.get("keyword") or "").strip(),
        "price_min": args.get("price_min"),
        "price_max": args.get("price_max"),
        "area_min": args.get("area_min"),
        "area_max": args.get("area_max"),
        "start_date": args.get("start_date"),
        "end_date": args.get("end_date"),
    }
    return filters


def _placeholders(values):
    return ", ".join(["?"] * len(values))


def where_clause(filters):
    clauses = ["1 = 1"]
    params = []

    for key, column in (
        ("city", "city"),
        ("district", "district"),
        ("layout", "layout"),
        ("status", "status"),
    ):
        values = filters.get(key) or []
        if values:
            clauses.append(f"{column} IN ({_placeholders(values)})")
            params.extend(values)

    keyword = filters.get("keyword")
    if keyword:
        like = f"%{keyword}%"
        clauses.append("(community LIKE ? OR block LIKE ? OR district LIKE ? OR city LIKE ?)")
        params.extend([like, like, like, like])

    numeric_ranges = [
        ("price_min", "list_total_price", ">="),
        ("price_max", "list_total_price", "<="),
        ("area_min", "area", ">="),
        ("area_max", "area", "<="),
    ]
    for key, column, op in numeric_ranges:
        value = filters.get(key)
        if value not in (None, ""):
            try:
                clauses.append(f"{column} {op} ?")
                params.append(float(value))
            except ValueError:
                pass

    if filters.get("start_date"):
        clauses.append("listing_date >= ?")
        params.append(filters["start_date"])
    if filters.get("end_date"):
        clauses.append("listing_date <= ?")
        params.append(filters["end_date"])

    return " AND ".join(clauses), params


def load_filtered_frame(filters):
    where, params = where_clause(filters)
    sql = f"SELECT * FROM listings WHERE {where}"
    df = pd.read_sql_query(sql, get_db(), params=params)
    for col in ("listing_date", "deal_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _safe_float(value, digits=2):
    if pd.isna(value):
        return 0
    return round(float(value), digits)


def _trend_flag(value):
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _month_range(months=36):
    today = pd.Timestamp(date.today().replace(day=1))
    return [(today - pd.DateOffset(months=i)).strftime("%Y-%m") for i in range(months - 1, -1, -1)]


def metrics(df):
    if df.empty:
        return {
            "total_listings": 0,
            "active_listings": 0,
            "avg_list_unit_price": 0,
            "avg_deal_unit_price": 0,
            "deals_7d": 0,
            "deals_30d": 0,
            "avg_transaction_cycle": 0,
            "market_heat": 0,
            "avg_mom": 0,
            "avg_yoy": 0,
            "mom_trend": "flat",
            "yoy_trend": "flat",
        }

    today = pd.Timestamp(date.today())
    sold = df[df["status"] == "已成交"]
    active = df[df["status"] == "在售"]
    deals_7d = sold[sold["deal_date"] >= today - pd.Timedelta(days=7)]
    deals_30d = sold[sold["deal_date"] >= today - pd.Timedelta(days=30)]

    views = df["view_count"].fillna(0).sum()
    follows = df["follow_count"].fillna(0).sum()
    heat = (len(active) * 0.35 + len(deals_30d) * 5 + views / 450 + follows / 80)
    heat = min(100, heat / max(len(df), 1) * 16)
    mom = _safe_float(df["avg_mom"].mean())
    yoy = _safe_float(df["avg_yoy"].mean())

    return {
        "total_listings": int(len(df)),
        "active_listings": int(len(active)),
        "avg_list_unit_price": _safe_float(df["list_unit_price"].mean(), 0),
        "avg_deal_unit_price": _safe_float(sold["deal_unit_price"].mean(), 0),
        "deals_7d": int(len(deals_7d)),
        "deals_30d": int(len(deals_30d)),
        "avg_transaction_cycle": _safe_float(sold["transaction_cycle"].mean(), 1),
        "market_heat": _safe_float(heat, 1),
        "avg_mom": mom,
        "avg_yoy": yoy,
        "mom_trend": _trend_flag(mom),
        "yoy_trend": _trend_flag(yoy),
    }


def options():
    db = get_db()
    city_rows = db.execute("SELECT DISTINCT city FROM listings ORDER BY city").fetchall()
    district_rows = db.execute(
        "SELECT city, district FROM listings GROUP BY city, district ORDER BY city, district"
    ).fetchall()
    layout_rows = db.execute("SELECT DISTINCT layout FROM listings ORDER BY bedrooms, area").fetchall()
    status_rows = db.execute("SELECT DISTINCT status FROM listings ORDER BY status").fetchall()
    return {
        "cities": [row["city"] for row in city_rows],
        "districts": [{"city": row["city"], "district": row["district"]} for row in district_rows],
        "layouts": [row["layout"] for row in layout_rows],
        "statuses": [row["status"] for row in status_rows],
    }


def district_distribution(df):
    if df.empty:
        return []
    grouped = (
        df.groupby(["city", "district"], dropna=False)
        .agg(
            listings=("listing_id", "count"),
            active=("status", lambda x: int((x == "在售").sum())),
            deals=("status", lambda x: int((x == "已成交").sum())),
            avg_price=("list_unit_price", "mean"),
            avg_deal_price=("deal_unit_price", "mean"),
        )
        .reset_index()
        .sort_values(["listings", "avg_price"], ascending=[False, False])
    )
    return [
        {
            "city": row.city,
            "district": row.district,
            "name": f"{row.city}-{row.district}",
            "listings": int(row.listings),
            "active": int(row.active),
            "deals": int(row.deals),
            "avg_price": _safe_float(row.avg_price, 0),
            "avg_deal_price": _safe_float(row.avg_deal_price, 0),
        }
        for row in grouped.itertuples(index=False)
    ]


def category_distribution(df, column):
    if df.empty or column not in df.columns:
        return []
    grouped = (
        df.groupby(column, dropna=False)
        .agg(listings=("listing_id", "count"), deals=("status", lambda x: int((x == "已成交").sum())))
        .reset_index()
        .sort_values("listings", ascending=False)
    )
    return [
        {"name": str(getattr(row, column) or "未知"), "value": int(row.listings), "deals": int(row.deals)}
        for row in grouped.itertuples(index=False)
    ]


def range_distribution(df, column, bins, labels):
    if df.empty:
        return [{"name": label, "value": 0} for label in labels]
    series = pd.cut(df[column].fillna(0), bins=bins, labels=labels, right=False)
    counts = series.value_counts(sort=False)
    return [{"name": str(label), "value": int(counts.get(label, 0))} for label in labels]


def trend_series(df, months=36):
    months_axis = _month_range(months)
    empty = [0] * len(months_axis)
    if df.empty:
        return {
            "months": months_axis,
            "list_avg": empty,
            "deal_avg": empty,
            "supply": empty,
            "deals": empty,
            "adjust_count": empty,
            "adjust_amount": empty,
        }

    working = df.copy()
    working["listing_month"] = working["listing_date"].dt.strftime("%Y-%m")
    working["deal_month"] = working["deal_date"].dt.strftime("%Y-%m")

    list_avg = working.groupby("listing_month")["list_unit_price"].mean().reindex(months_axis)
    supply = working.groupby("listing_month")["listing_id"].count().reindex(months_axis)

    sold = working[working["status"] == "已成交"]
    deal_avg = sold.groupby("deal_month")["deal_unit_price"].mean().reindex(months_axis)
    deals = sold.groupby("deal_month")["listing_id"].count().reindex(months_axis)
    adjust_count = working.groupby("listing_month")["price_adjust_count"].sum().reindex(months_axis)
    adjust_amount = working.groupby("listing_month")["price_adjust_amount"].mean().reindex(months_axis)

    return {
        "months": months_axis,
        "list_avg": [_safe_float(v, 0) for v in list_avg],
        "deal_avg": [_safe_float(v, 0) for v in deal_avg],
        "supply": [int(v) if not pd.isna(v) else 0 for v in supply],
        "deals": [int(v) if not pd.isna(v) else 0 for v in deals],
        "adjust_count": [int(v) if not pd.isna(v) else 0 for v in adjust_count],
        "adjust_amount": [_safe_float(v, 1) for v in adjust_amount],
    }


def hot_communities(df, limit=12):
    if df.empty:
        return []
    grouped = (
        df.groupby(["city", "district", "community"], dropna=False)
        .agg(
            listings=("listing_id", "count"),
            deals=("status", lambda x: int((x == "已成交").sum())),
            avg_price=("list_unit_price", "mean"),
            avg_cycle=("transaction_cycle", "mean"),
            views=("view_count", "sum"),
            follows=("follow_count", "sum"),
        )
        .reset_index()
    )
    grouped["score"] = grouped["deals"] * 5 + grouped["listings"] * 1.2 + grouped["views"] / 900 + grouped["follows"] / 80
    grouped = grouped.sort_values("score", ascending=False).head(limit)
    return [
        {
            "city": row.city,
            "district": row.district,
            "community": row.community,
            "listings": int(row.listings),
            "deals": int(row.deals),
            "avg_price": _safe_float(row.avg_price, 0),
            "avg_cycle": _safe_float(row.avg_cycle, 1),
            "heat": _safe_float(row.score, 1),
        }
        for row in grouped.itertuples(index=False)
    ]


def support_value(df):
    if df.empty:
        return []

    groups = {
        "近地铁": df["metro_station"].fillna("").astype(str).str.len() > 0,
        "有学校": df["school"].fillna("").astype(str).str.len() > 0,
        "近商圈": df["mall"].fillna("").astype(str).str.len() > 0,
        "近医院": df["hospital"].fillna("").astype(str).str.len() > 0,
    }
    rows = []
    overall = df["list_unit_price"].mean()
    for name, mask in groups.items():
        selected = df[mask]
        other = df[~mask]
        selected_avg = selected["list_unit_price"].mean()
        other_avg = other["list_unit_price"].mean()
        rows.append(
            {
                "name": name,
                "avg_price": _safe_float(selected_avg, 0),
                "baseline": _safe_float(other_avg if not pd.isna(other_avg) else overall, 0),
                "premium": _safe_float(
                    (selected_avg - other_avg) / other_avg * 100
                    if not pd.isna(selected_avg) and not pd.isna(other_avg) and other_avg
                    else 0,
                    1,
                ),
                "count": int(len(selected)),
            }
        )
    return rows


def floor_orientation(df):
    if df.empty:
        return {"floor": [], "orientation": []}
    floor = (
        df.groupby("floor_level", dropna=False)
        .agg(avg_price=("list_unit_price", "mean"), deals=("status", lambda x: int((x == "已成交").sum())))
        .reset_index()
    )
    orientation = (
        df.groupby("orientation", dropna=False)
        .agg(avg_price=("list_unit_price", "mean"), deals=("status", lambda x: int((x == "已成交").sum())))
        .reset_index()
        .sort_values("avg_price", ascending=False)
        .head(8)
    )
    return {
        "floor": [
            {"name": str(row.floor_level or "未知"), "avg_price": _safe_float(row.avg_price, 0), "deals": int(row.deals)}
            for row in floor.itertuples(index=False)
        ],
        "orientation": [
            {"name": str(row.orientation or "未知"), "avg_price": _safe_float(row.avg_price, 0), "deals": int(row.deals)}
            for row in orientation.itertuples(index=False)
        ],
    }


def quality_report():
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS total FROM listings").fetchone()["total"]
    if total == 0:
        return {"total": 0, "missing_rate": 0, "error_rate": 0, "updated_at": None}
    missing = db.execute(
        """
        SELECT COUNT(*) AS total FROM listings
         WHERE city = '' OR district = '' OR community = ''
            OR area IS NULL OR list_unit_price IS NULL OR listing_date IS NULL
        """
    ).fetchone()["total"]
    errors = db.execute(
        """
        SELECT COUNT(*) AS total FROM listings
         WHERE area < 15 OR area > 500 OR list_unit_price < 3000 OR list_unit_price > 250000
        """
    ).fetchone()["total"]
    updated = db.execute("SELECT MAX(updated_at) AS updated_at FROM listings").fetchone()["updated_at"]
    return {
        "total": int(total),
        "missing_rate": round(missing / total * 100, 2),
        "error_rate": round(errors / total * 100, 2),
        "updated_at": updated,
    }


def dashboard_payload(filters):
    df = load_filtered_frame(filters)
    price_bins = [0, 50, 100, 200, 300, 500, 800, 100000]
    price_labels = ["50万以下", "50-100万", "100-200万", "200-300万", "300-500万", "500-800万", "800万以上"]
    area_bins = [0, 50, 70, 90, 120, 150, 200, 10000]
    area_labels = ["50㎡以下", "50-70㎡", "70-90㎡", "90-120㎡", "120-150㎡", "150-200㎡", "200㎡以上"]

    return {
        "metrics": metrics(df),
        "quality": quality_report(),
        "districts": district_distribution(df),
        "layout": category_distribution(df, "layout"),
        "price_ranges": range_distribution(df, "list_total_price", price_bins, price_labels),
        "area_ranges": range_distribution(df, "area", area_bins, area_labels),
        "decoration": category_distribution(df, "decoration"),
        "trend": trend_series(df, months=36),
        "hot_communities": hot_communities(df),
        "support_value": support_value(df),
        "floor_orientation": floor_orientation(df),
    }


def paginated_listings(filters, page=1, page_size=20):
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 20), 1), 100)
    where, params = where_clause(filters)
    offset = (page - 1) * page_size
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) AS total FROM listings WHERE {where}", params).fetchone()["total"]
    rows = db.execute(
        f"""
        SELECT id, listing_id, city, district, block, community, layout, area, floor_level,
               orientation, decoration, build_year, list_total_price, list_unit_price,
               deal_total_price, deal_unit_price, status, listing_date, deal_date,
               transaction_cycle, school, hospital, mall, metro_station
          FROM listings
         WHERE {where}
         ORDER BY COALESCE(deal_date, listing_date) DESC, id DESC
         LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()
    return {
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "items": [dict(row) for row in rows],
    }

import io
import random
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from flask import current_app

from app.db import get_db, log_operation


COLUMN_ALIASES = {
    "房源ID": "listing_id",
    "房源 ID": "listing_id",
    "所属城市": "city",
    "城市": "city",
    "所属区域": "district",
    "区域": "district",
    "区域名称": "district",
    "板块名称": "block",
    "板块": "block",
    "小区名称": "community",
    "小区": "community",
    "户型": "layout",
    "建筑面积": "area",
    "面积": "area",
    "楼层": "floor_level",
    "总楼层": "total_floors",
    "朝向": "orientation",
    "装修情况": "decoration",
    "装修": "decoration",
    "建筑年代": "build_year",
    "挂牌总价": "list_total_price",
    "挂牌单价": "list_unit_price",
    "成交总价": "deal_total_price",
    "成交单价": "deal_unit_price",
    "调价次数": "price_adjust_count",
    "调价记录": "price_adjust_count",
    "调价幅度": "price_adjust_amount",
    "均价环比": "avg_mom",
    "均价同比": "avg_yoy",
    "交易状态": "status",
    "挂牌时间": "listing_date",
    "成交时间": "deal_date",
    "交易周期": "transaction_cycle",
    "交易方式": "transaction_type",
    "周边学校": "school",
    "学校": "school",
    "医院": "hospital",
    "商场": "mall",
    "交通站点": "metro_station",
    "地铁站": "metro_station",
    "容积率": "plot_ratio",
    "绿化率": "greening_rate",
    "物业费": "property_fee",
    "浏览量": "view_count",
    "关注量": "follow_count",
    "数据来源": "source_name",
}

LISTING_COLUMNS = [
    "listing_id",
    "city",
    "district",
    "block",
    "community",
    "layout",
    "bedrooms",
    "living_rooms",
    "area",
    "floor_level",
    "total_floors",
    "orientation",
    "decoration",
    "build_year",
    "list_total_price",
    "list_unit_price",
    "deal_total_price",
    "deal_unit_price",
    "price_adjust_count",
    "price_adjust_amount",
    "avg_mom",
    "avg_yoy",
    "status",
    "listing_date",
    "deal_date",
    "transaction_cycle",
    "transaction_type",
    "school",
    "hospital",
    "mall",
    "metro_station",
    "plot_ratio",
    "greening_rate",
    "property_fee",
    "view_count",
    "follow_count",
    "source_name",
    "data_version",
]

NUMERIC_COLUMNS = [
    "area",
    "total_floors",
    "build_year",
    "list_total_price",
    "list_unit_price",
    "deal_total_price",
    "deal_unit_price",
    "price_adjust_count",
    "price_adjust_amount",
    "avg_mom",
    "avg_yoy",
    "transaction_cycle",
    "plot_ratio",
    "greening_rate",
    "property_fee",
    "view_count",
    "follow_count",
]

TEXT_DEFAULTS = {
    "block": "未知板块",
    "layout": "未知户型",
    "floor_level": "未知",
    "orientation": "未知",
    "decoration": "未知",
    "transaction_type": "普通交易",
    "school": "",
    "hospital": "",
    "mall": "",
    "metro_station": "",
    "source_name": "CSV导入",
}


def ensure_demo_data():
    db = get_db()
    count = db.execute("SELECT COUNT(*) AS total FROM listings").fetchone()["total"]
    if count == 0:
        seed_demo_data()


def read_csv(file_storage):
    content = file_storage.read()
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return pd.read_csv(io.BytesIO(content), encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.BytesIO(content))


def normalize_columns(df):
    mapped = {}
    for col in df.columns:
        clean = str(col).strip()
        mapped[col] = COLUMN_ALIASES.get(clean, clean)
    return df.rename(columns=mapped)


def parse_layout(value):
    text = str(value or "")
    bedrooms = 0
    living_rooms = 0
    if "室" in text:
        try:
            bedrooms = int(text.split("室")[0][-1])
        except (ValueError, IndexError):
            bedrooms = 0
    if "厅" in text:
        try:
            left = text.split("室")[-1] if "室" in text else text
            living_rooms = int(left.split("厅")[0][-1])
        except (ValueError, IndexError):
            living_rooms = 0
    return bedrooms, living_rooms


def parse_date_series(series):
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.strftime("%Y-%m-%d")


def clean_dataframe(df, source_name="CSV导入"):
    df = normalize_columns(df).copy()

    for col in LISTING_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ("listing_date", "deal_date"):
        df[col] = parse_date_series(df[col])

    for col, default in TEXT_DEFAULTS.items():
        df[col] = df[col].fillna(default).astype(str).str.strip()
        df.loc[df[col].isin(["", "nan", "None"]), col] = default

    df["city"] = df["city"].fillna("").astype(str).str.strip()
    df["district"] = df["district"].fillna("").astype(str).str.strip()
    df["community"] = df["community"].fillna("").astype(str).str.strip()
    df["status"] = df["status"].fillna("在售").astype(str).str.strip()

    df = df[(df["city"] != "") & (df["district"] != "") & (df["community"] != "")]

    df["area"] = df["area"].fillna(0)
    df = df[(df["area"] >= 15) & (df["area"] <= 500)]

    missing_id = df["listing_id"].isna() | (df["listing_id"].astype(str).str.strip() == "")
    df.loc[missing_id, "listing_id"] = (
        df.loc[missing_id, "city"].astype(str)
        + "-"
        + df.loc[missing_id, "district"].astype(str)
        + "-"
        + df.loc[missing_id, "community"].astype(str)
        + "-"
        + df.loc[missing_id, "area"].round(2).astype(str)
        + "-"
        + df.loc[missing_id].index.astype(str)
    )
    df["listing_id"] = df["listing_id"].astype(str).str.strip()

    no_unit = df["list_unit_price"].isna() | (df["list_unit_price"] <= 0)
    has_total = df["list_total_price"].notna() & (df["list_total_price"] > 0)
    df.loc[no_unit & has_total, "list_unit_price"] = (
        df.loc[no_unit & has_total, "list_total_price"] * 10000 / df.loc[no_unit & has_total, "area"]
    )

    no_total = df["list_total_price"].isna() | (df["list_total_price"] <= 0)
    has_unit = df["list_unit_price"].notna() & (df["list_unit_price"] > 0)
    df.loc[no_total & has_unit, "list_total_price"] = (
        df.loc[no_total & has_unit, "list_unit_price"] * df.loc[no_total & has_unit, "area"] / 10000
    )

    df = df[(df["list_unit_price"] >= 3000) & (df["list_unit_price"] <= 250000)]

    no_deal_unit = df["deal_unit_price"].isna() | (df["deal_unit_price"] <= 0)
    has_deal_total = df["deal_total_price"].notna() & (df["deal_total_price"] > 0)
    df.loc[no_deal_unit & has_deal_total, "deal_unit_price"] = (
        df.loc[no_deal_unit & has_deal_total, "deal_total_price"] * 10000 / df.loc[no_deal_unit & has_deal_total, "area"]
    )

    no_deal_total = df["deal_total_price"].isna() | (df["deal_total_price"] <= 0)
    has_deal_unit = df["deal_unit_price"].notna() & (df["deal_unit_price"] > 0)
    df.loc[no_deal_total & has_deal_unit, "deal_total_price"] = (
        df.loc[no_deal_total & has_deal_unit, "deal_unit_price"] * df.loc[no_deal_total & has_deal_unit, "area"] / 10000
    )

    today = date.today().strftime("%Y-%m-%d")
    df["listing_date"] = df["listing_date"].fillna(today)
    df["status"] = df["status"].replace({"sold": "已成交", "on_sale": "在售", "deal": "已成交"})
    df.loc[~df["status"].isin(["在售", "已成交", "下架", "暂停"]), "status"] = "在售"

    for idx, row in df.iterrows():
        bedrooms, living_rooms = parse_layout(row["layout"])
        if not row["bedrooms"] or pd.isna(row["bedrooms"]):
            df.at[idx, "bedrooms"] = bedrooms
        if not row["living_rooms"] or pd.isna(row["living_rooms"]):
            df.at[idx, "living_rooms"] = living_rooms

    df["source_name"] = df["source_name"].replace("", source_name).fillna(source_name)
    df["data_version"] = datetime.now().strftime("%Y%m%d%H%M%S")

    int_columns = [
        "bedrooms",
        "living_rooms",
        "total_floors",
        "build_year",
        "price_adjust_count",
        "transaction_cycle",
        "view_count",
        "follow_count",
    ]
    for col in int_columns:
        df[col] = df[col].fillna(0).round().astype(int)

    for col in LISTING_COLUMNS:
        if col not in int_columns:
            df[col] = df[col].where(pd.notna(df[col]), None)

    df = df.drop_duplicates(subset=["listing_id"], keep="last")
    return df[LISTING_COLUMNS]


def upsert_listings(df, source_name="CSV导入"):
    db = get_db()
    placeholders = ", ".join(["?"] * len(LISTING_COLUMNS))
    columns = ", ".join(LISTING_COLUMNS)
    update_columns = [col for col in LISTING_COLUMNS if col != "listing_id"]
    update_sql = ", ".join([f"{col} = excluded.{col}" for col in update_columns])
    sql = f"""
        INSERT INTO listings({columns})
        VALUES ({placeholders})
        ON CONFLICT(listing_id) DO UPDATE SET
            {update_sql},
            updated_at = CURRENT_TIMESTAMP
    """

    inserted = 0
    updated = 0
    for row in df.itertuples(index=False, name=None):
        listing_id = row[0]
        exists = db.execute("SELECT id FROM listings WHERE listing_id = ?", (listing_id,)).fetchone()
        db.execute(sql, row)
        if exists:
            updated += 1
        else:
            inserted += 1
    db.commit()
    log_operation("import_listings", f"{source_name}: 新增 {inserted} 条，更新 {updated} 条")
    return inserted, updated


def import_csv(file_storage, source_name="CSV导入"):
    db = get_db()
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_id = db.execute(
        "INSERT INTO import_logs(source_name, status, started_at) VALUES (?, ?, ?)",
        (source_name, "running", started_at),
    ).lastrowid
    db.commit()

    try:
        raw = read_csv(file_storage)
        cleaned = clean_dataframe(raw, source_name)
        inserted, updated = upsert_listings(cleaned, source_name)
        errors = max(len(raw) - len(cleaned), 0)
        status = "success"
        message = "导入完成"
    except Exception as exc:
        inserted = updated = 0
        errors = 1
        raw = []
        status = "failed"
        message = str(exc)

    db.execute(
        """
        UPDATE import_logs
           SET status = ?, rows_total = ?, rows_inserted = ?, rows_updated = ?,
               rows_error = ?, message = ?, finished_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (status, len(raw), inserted, updated, errors, message, log_id),
    )
    db.commit()

    if status == "failed":
        raise ValueError(message)
    return {
        "rows_total": len(raw),
        "rows_inserted": inserted,
        "rows_updated": updated,
        "rows_error": errors,
        "message": message,
    }


def seed_demo_data(total=1600):
    random.seed(20260428)
    np.random.seed(20260428)

    city_profile = {
        "北京": {"base": 69000, "districts": ["朝阳", "海淀", "丰台", "西城", "通州", "昌平"]},
        "上海": {"base": 72000, "districts": ["浦东", "徐汇", "闵行", "静安", "宝山", "松江"]},
        "广州": {"base": 39000, "districts": ["天河", "越秀", "海珠", "番禺", "白云", "黄埔"]},
        "深圳": {"base": 76000, "districts": ["南山", "福田", "宝安", "龙岗", "罗湖", "龙华"]},
        "杭州": {"base": 42000, "districts": ["西湖", "滨江", "萧山", "余杭", "拱墅", "上城"]},
        "成都": {"base": 21000, "districts": ["锦江", "高新", "青羊", "武侯", "成华", "天府新区"]},
    }
    layouts = ["1室1厅", "2室1厅", "2室2厅", "3室1厅", "3室2厅", "4室2厅", "5室2厅"]
    orientations = ["南", "南北", "东南", "西南", "东", "北"]
    decorations = ["毛坯", "简装", "精装", "豪装"]
    floor_levels = ["低楼层", "中楼层", "高楼层"]
    blocks = ["核心板块", "改善板块", "刚需板块", "产业园板块", "地铁沿线", "学府板块"]
    schools = ["实验小学", "外国语学校", "第一中学", "", ""]
    hospitals = ["中心医院", "人民医院", "社区卫生中心", "", ""]
    malls = ["万象城", "吾悦广场", "银泰中心", "社区商业", ""]
    metros = ["1号线", "2号线", "3号线", "5号线", "", ""]

    rows = []
    end_date = date.today()
    start_date = end_date - timedelta(days=365 * 3)

    for idx in range(total):
        city = random.choice(list(city_profile.keys()))
        profile = city_profile[city]
        district = random.choice(profile["districts"])
        district_factor = 1 + (profile["districts"].index(district) - 2.5) * 0.045
        block = random.choice(blocks)
        layout = random.choices(layouts, weights=[8, 18, 20, 14, 25, 11, 4])[0]
        bedrooms, living_rooms = parse_layout(layout)
        area_base = {
            1: 48,
            2: 78,
            3: 112,
            4: 145,
            5: 190,
        }.get(bedrooms, 90)
        area = max(25, random.gauss(area_base, area_base * 0.16))
        build_year = random.randint(1995, 2024)
        age_factor = 1 + (build_year - 2010) * 0.004
        decoration = random.choices(decorations, weights=[10, 25, 55, 10])[0]
        deco_factor = {"毛坯": 0.92, "简装": 0.97, "精装": 1.05, "豪装": 1.13}[decoration]
        metro_station = random.choice(metros)
        metro_factor = 1.08 if metro_station else 0.96
        trend_days = (start_date + timedelta(days=random.randint(0, (end_date - start_date).days)) - start_date).days
        trend_factor = 0.95 + trend_days / ((end_date - start_date).days) * 0.08
        noise = random.uniform(0.86, 1.18)
        list_unit = round(profile["base"] * district_factor * age_factor * deco_factor * metro_factor * trend_factor * noise, 0)
        list_total = round(list_unit * area / 10000, 2)

        listing_date = start_date + timedelta(days=random.randint(0, (end_date - start_date).days))
        sold = random.random() < 0.42 and listing_date < end_date - timedelta(days=20)
        transaction_cycle = random.randint(12, 180)
        deal_date = listing_date + timedelta(days=transaction_cycle) if sold else None
        if deal_date and deal_date > end_date:
            sold = False
            deal_date = None

        discount = random.uniform(0.93, 1.02)
        deal_unit = round(list_unit * discount, 0) if sold else None
        deal_total = round(deal_unit * area / 10000, 2) if sold else None
        price_adjust_count = random.choices([0, 1, 2, 3, 4], weights=[45, 30, 15, 7, 3])[0]
        price_adjust_amount = round(random.uniform(-18, 8) * price_adjust_count, 2)

        community = f"{district}{random.choice(['花园', '公馆', '家园', '名邸', '雅苑', '中心'])}{random.randint(1, 18)}期"
        rows.append(
            {
                "listing_id": f"DEMO-{idx + 1:05d}",
                "city": city,
                "district": district,
                "block": block,
                "community": community,
                "layout": layout,
                "bedrooms": bedrooms,
                "living_rooms": living_rooms,
                "area": round(area, 2),
                "floor_level": random.choice(floor_levels),
                "total_floors": random.randint(6, 35),
                "orientation": random.choice(orientations),
                "decoration": decoration,
                "build_year": build_year,
                "list_total_price": list_total,
                "list_unit_price": list_unit,
                "deal_total_price": deal_total,
                "deal_unit_price": deal_unit,
                "price_adjust_count": price_adjust_count,
                "price_adjust_amount": price_adjust_amount,
                "avg_mom": round(random.uniform(-3.6, 3.8), 2),
                "avg_yoy": round(random.uniform(-9.0, 8.0), 2),
                "status": "已成交" if sold else random.choices(["在售", "下架"], weights=[88, 12])[0],
                "listing_date": listing_date.strftime("%Y-%m-%d"),
                "deal_date": deal_date.strftime("%Y-%m-%d") if deal_date else None,
                "transaction_cycle": transaction_cycle if sold else None,
                "transaction_type": random.choice(["普通交易", "满五唯一", "满二", "委托交易"]),
                "school": random.choice(schools),
                "hospital": random.choice(hospitals),
                "mall": random.choice(malls),
                "metro_station": metro_station,
                "plot_ratio": round(random.uniform(1.2, 4.8), 2),
                "greening_rate": round(random.uniform(18, 48), 1),
                "property_fee": round(random.uniform(1.2, 8.5), 2),
                "view_count": random.randint(40, 5600),
                "follow_count": random.randint(0, 620),
                "source_name": "系统演示数据",
                "data_version": "demo",
            }
        )

    df = pd.DataFrame(rows)
    cleaned = clean_dataframe(df, "系统演示数据")
    inserted, updated = upsert_listings(cleaned, "系统演示数据")

    db = get_db()
    db.execute(
        """
        INSERT INTO import_logs(source_name, status, rows_total, rows_inserted, rows_updated,
                                rows_error, message, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        ("系统演示数据", "success", len(rows), inserted, updated, 0, "自动生成演示数据"),
    )
    db.commit()
    current_app.logger.info("Seeded demo housing data: %s inserted, %s updated", inserted, updated)

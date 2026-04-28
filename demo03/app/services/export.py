import io

import pandas as pd

from app.services.analytics import load_filtered_frame


EXPORT_COLUMNS = {
    "listing_id": "房源ID",
    "city": "城市",
    "district": "区域",
    "block": "板块",
    "community": "小区",
    "layout": "户型",
    "area": "建筑面积",
    "floor_level": "楼层",
    "orientation": "朝向",
    "decoration": "装修",
    "build_year": "建筑年代",
    "list_total_price": "挂牌总价",
    "list_unit_price": "挂牌单价",
    "deal_total_price": "成交总价",
    "deal_unit_price": "成交单价",
    "status": "交易状态",
    "listing_date": "挂牌时间",
    "deal_date": "成交时间",
    "transaction_cycle": "交易周期",
    "school": "周边学校",
    "hospital": "医院",
    "mall": "商场",
    "metro_station": "交通站点",
}


def listing_export_frame(filters):
    df = load_filtered_frame(filters)
    if df.empty:
        return pd.DataFrame(columns=list(EXPORT_COLUMNS.values()))
    columns = [col for col in EXPORT_COLUMNS if col in df.columns]
    return df[columns].rename(columns=EXPORT_COLUMNS)


def to_csv_bytes(df):
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def to_excel_bytes(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="二手房明细")
    buffer.seek(0)
    return buffer.getvalue()

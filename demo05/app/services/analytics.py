from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from app.models import Listing


plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False


def listings_dataframe():
    rows = [listing.to_dict() for listing in Listing.query.all()]
    columns = [
        "id",
        "source",
        "district",
        "community",
        "rent_price",
        "area",
        "house_type",
        "orientation",
        "floor",
        "tags",
        "publish_time",
        "unit_price",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


def get_analytics_payload():
    df = listings_dataframe()
    if df.empty:
        return {
            "summary": empty_summary(),
            "district_avg": [],
            "house_type_avg": [],
            "area_unit_price": [],
            "orientation_avg": [],
        }

    summary = {
        "total": int(len(df)),
        "district_count": int(df["district"].nunique()),
        "avg_rent": round(float(df["rent_price"].mean()), 2),
        "median_rent": round(float(df["rent_price"].median()), 2),
        "avg_area": round(float(df["area"].mean()), 2),
        "avg_unit_price": round(float(df["unit_price"].mean()), 2),
        "max_rent": round(float(df["rent_price"].max()), 2),
        "min_rent": round(float(df["rent_price"].min()), 2),
    }

    district_avg = (
        df.groupby("district", as_index=False)
        .agg(avg_rent=("rent_price", "mean"), count=("id", "count"), avg_unit_price=("unit_price", "mean"))
        .sort_values("avg_rent", ascending=False)
    )

    house_type_avg = (
        df.groupby("house_type", as_index=False)
        .agg(avg_rent=("rent_price", "mean"), count=("id", "count"))
        .sort_values("avg_rent", ascending=False)
    )

    area_bins = [0, 40, 60, 80, 100, 120, 150, 999]
    area_labels = ["40㎡以下", "40-60㎡", "60-80㎡", "80-100㎡", "100-120㎡", "120-150㎡", "150㎡以上"]
    df = df.copy()
    df["area_bin"] = pd.cut(df["area"], bins=area_bins, labels=area_labels, right=False)
    area_unit_price = (
        df.dropna(subset=["area_bin"])
        .groupby("area_bin", observed=False, as_index=False)
        .agg(avg_unit_price=("unit_price", "mean"), avg_rent=("rent_price", "mean"), count=("id", "count"))
    )

    orientation_avg = (
        df[df["orientation"] != ""]
        .groupby("orientation", as_index=False)
        .agg(avg_rent=("rent_price", "mean"), count=("id", "count"))
        .sort_values("avg_rent", ascending=False)
    )

    return {
        "summary": summary,
        "district_avg": round_records(district_avg),
        "house_type_avg": round_records(house_type_avg),
        "area_unit_price": round_records(area_unit_price),
        "orientation_avg": round_records(orientation_avg),
    }


def empty_summary():
    return {
        "total": 0,
        "district_count": 0,
        "avg_rent": 0,
        "median_rent": 0,
        "avg_area": 0,
        "avg_unit_price": 0,
        "max_rent": 0,
        "min_rent": 0,
    }


def round_records(frame):
    records = frame.to_dict(orient="records")
    for record in records:
        for key, value in list(record.items()):
            if isinstance(value, float):
                record[key] = round(value, 2)
    return records


def generate_all_charts(output_dir, url_prefix="/static/generated"):
    df = listings_dataframe()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    chart_files = {
        "district_bar": "district_avg_rent.png",
        "house_type_bar": "house_type_avg_rent.png",
        "area_line": "area_unit_price.png",
        "orientation_bar": "orientation_avg_rent.png",
        "rent_hist": "rent_distribution.png",
    }

    if df.empty:
        for filename in chart_files.values():
            render_empty_chart(output_path / filename)
    else:
        render_district_chart(df, output_path / chart_files["district_bar"])
        render_house_type_chart(df, output_path / chart_files["house_type_bar"])
        render_area_chart(df, output_path / chart_files["area_line"])
        render_orientation_chart(df, output_path / chart_files["orientation_bar"])
        render_rent_histogram(df, output_path / chart_files["rent_hist"])

    return {key: f"{url_prefix}/{filename}" for key, filename in chart_files.items()}


def render_empty_chart(path):
    fig, ax = plt.subplots(figsize=(7, 4), dpi=140)
    ax.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=18)
    ax.axis("off")
    save_figure(fig, path)


def render_district_chart(df, path):
    data = (
        df.groupby("district")["rent_price"]
        .mean()
        .sort_values(ascending=False)
        .head(12)
    )
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=140)
    ax.bar(data.index, data.values, color="#2f8f83")
    ax.set_title("各区域平均租金")
    ax.set_ylabel("元/月")
    ax.tick_params(axis="x", rotation=35)
    ax.grid(axis="y", alpha=0.25)
    save_figure(fig, path)


def render_house_type_chart(df, path):
    data = (
        df.groupby("house_type")["rent_price"]
        .mean()
        .sort_values(ascending=False)
    )
    fig, ax = plt.subplots(figsize=(7, 4.6), dpi=140)
    ax.bar(data.index, data.values, color="#d86f45")
    ax.set_title("不同户型平均租金")
    ax.set_ylabel("元/月")
    ax.grid(axis="y", alpha=0.25)
    save_figure(fig, path)


def render_area_chart(df, path):
    bins = [0, 40, 60, 80, 100, 120, 150, 999]
    labels = ["40以下", "40-60", "60-80", "80-100", "100-120", "120-150", "150以上"]
    frame = df.copy()
    frame["area_bin"] = pd.cut(frame["area"], bins=bins, labels=labels, right=False)
    data = frame.groupby("area_bin", observed=False)["unit_price"].mean().dropna()

    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=140)
    ax.plot(data.index.astype(str), data.values, marker="o", color="#5d6cc5", linewidth=2.5)
    ax.set_title("面积分段单位租金")
    ax.set_xlabel("面积段（㎡）")
    ax.set_ylabel("元/㎡/月")
    ax.grid(alpha=0.25)
    save_figure(fig, path)


def render_orientation_chart(df, path):
    data = (
        df[df["orientation"] != ""]
        .groupby("orientation")["rent_price"]
        .mean()
        .sort_values(ascending=False)
        .head(10)
    )
    fig, ax = plt.subplots(figsize=(7, 4.6), dpi=140)
    ax.bar(data.index, data.values, color="#7a9a3a")
    ax.set_title("不同朝向平均租金")
    ax.set_ylabel("元/月")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.25)
    save_figure(fig, path)


def render_rent_histogram(df, path):
    fig, ax = plt.subplots(figsize=(7, 4.6), dpi=140)
    ax.hist(df["rent_price"], bins=10, color="#b85c7a", edgecolor="white")
    ax.set_title("租金分布")
    ax.set_xlabel("元/月")
    ax.set_ylabel("房源数量")
    ax.grid(axis="y", alpha=0.25)
    save_figure(fig, path)


def save_figure(fig, path):
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)

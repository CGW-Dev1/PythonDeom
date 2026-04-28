from datetime import datetime

from flask import Blueprint, Response, jsonify, request, send_file

from app.auth import admin_required, current_user, login_required
from app.db import get_db, log_operation
from app.services.analytics import (
    build_filters,
    dashboard_payload,
    options,
    paginated_listings,
    quality_report,
)
from app.services.export import listing_export_frame, to_csv_bytes, to_excel_bytes
from app.services.ingestion import import_csv, seed_demo_data

api_bp = Blueprint("api", __name__)


def _json_error(message, status=400):
    return jsonify({"ok": False, "message": message}), status


@api_bp.route("/me")
@login_required
def me():
    user = current_user()
    return jsonify({"id": user["id"], "username": user["username"], "role": user["role"]})


@api_bp.route("/options")
@login_required
def api_options():
    return jsonify(options())


@api_bp.route("/dashboard")
@login_required
def api_dashboard():
    filters = build_filters(request.args)
    return jsonify(dashboard_payload(filters))


@api_bp.route("/listings")
@login_required
def api_listings():
    filters = build_filters(request.args)
    page = request.args.get("page", 1)
    page_size = request.args.get("page_size", 20)
    return jsonify(paginated_listings(filters, page, page_size))


@api_bp.route("/listings/<int:item_id>", methods=["PATCH"])
@admin_required
def update_listing(item_id):
    data = request.get_json(silent=True) or {}
    allowed = {
        "city",
        "district",
        "block",
        "community",
        "layout",
        "area",
        "floor_level",
        "orientation",
        "decoration",
        "build_year",
        "list_total_price",
        "list_unit_price",
        "deal_total_price",
        "deal_unit_price",
        "status",
        "listing_date",
        "deal_date",
        "transaction_cycle",
        "school",
        "hospital",
        "mall",
        "metro_station",
    }
    updates = {key: value for key, value in data.items() if key in allowed}
    if not updates:
        return _json_error("没有可更新字段。")

    assignments = ", ".join([f"{key} = ?" for key in updates])
    params = [*updates.values(), item_id]
    db = get_db()
    db.execute(
        f"UPDATE listings SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        params,
    )
    db.commit()
    log_operation("update_listing", f"更新房源 ID={item_id}")
    return jsonify({"ok": True, "message": "房源已更新"})


@api_bp.route("/listings/<int:item_id>", methods=["DELETE"])
@admin_required
def delete_listing(item_id):
    db = get_db()
    db.execute("DELETE FROM listings WHERE id = ?", (item_id,))
    db.commit()
    log_operation("delete_listing", f"删除房源 ID={item_id}")
    return jsonify({"ok": True, "message": "房源已删除"})


@api_bp.route("/import", methods=["POST"])
@admin_required
def api_import():
    upload = request.files.get("file")
    source_name = request.form.get("source_name") or "CSV导入"
    if not upload:
        return _json_error("请上传 CSV 文件。")
    if not upload.filename.lower().endswith(".csv"):
        return _json_error("当前仅支持 CSV 文件导入。")
    try:
        result = import_csv(upload, source_name)
    except ValueError as exc:
        return _json_error(str(exc), 422)
    return jsonify({"ok": True, **result})


@api_bp.route("/seed-demo", methods=["POST"])
@admin_required
def api_seed_demo():
    total = int(request.form.get("total") or 1600)
    total = min(max(total, 100), 10000)
    seed_demo_data(total)
    return jsonify({"ok": True, "message": f"已生成或更新 {total} 条演示数据。"})


@api_bp.route("/export/listings")
@login_required
def export_listings():
    filters = build_filters(request.args)
    export_format = (request.args.get("format") or "csv").lower()
    df = listing_export_frame(filters)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    if export_format in ("xlsx", "excel"):
        payload = to_excel_bytes(df)
        return send_file(
            __import__("io").BytesIO(payload),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"second_hand_listings_{stamp}.xlsx",
        )
    payload = to_csv_bytes(df)
    return Response(
        payload,
        mimetype="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename=second_hand_listings_{stamp}.csv"},
    )


@api_bp.route("/export/statistics")
@login_required
def export_statistics():
    filters = build_filters(request.args)
    payload = dashboard_payload(filters)
    lines = ["指标,数值"]
    for key, value in payload["metrics"].items():
        lines.append(f"{key},{value}")
    lines.append("")
    lines.append("区域,房源量,在售量,成交量,挂牌均价")
    for row in payload["districts"]:
        lines.append(f"{row['name']},{row['listings']},{row['active']},{row['deals']},{row['avg_price']}")
    data = "\ufeff" + "\n".join(lines)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=statistics_{stamp}.csv"},
    )


@api_bp.route("/quality")
@login_required
def api_quality():
    return jsonify(quality_report())


@api_bp.route("/logs")
@admin_required
def api_logs():
    db = get_db()
    import_logs = db.execute(
        """
        SELECT id, source_name, status, rows_total, rows_inserted, rows_updated,
               rows_error, message, started_at, finished_at
          FROM import_logs
         ORDER BY id DESC
         LIMIT 50
        """
    ).fetchall()
    operation_logs = db.execute(
        """
        SELECT id, username, action, detail, created_at
          FROM operation_logs
         ORDER BY id DESC
         LIMIT 80
        """
    ).fetchall()
    return jsonify(
        {
            "import_logs": [dict(row) for row in import_logs],
            "operation_logs": [dict(row) for row in operation_logs],
        }
    )


@api_bp.route("/data-sources", methods=["GET", "POST"])
@admin_required
def api_data_sources():
    db = get_db()
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        name = (data.get("name") or "").strip()
        if not name:
            return _json_error("数据源名称不能为空。")
        db.execute(
            """
            INSERT INTO data_sources(name, source_type, url, compliance_note, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                data.get("source_type") or "csv",
                data.get("url") or "",
                data.get("compliance_note") or "",
                1 if str(data.get("enabled", "1")) in ("1", "true", "True", "on") else 0,
            ),
        )
        db.commit()
        log_operation("create_data_source", name)
        return jsonify({"ok": True, "message": "数据源已保存"})

    rows = db.execute(
        """
        SELECT id, name, source_type, url, compliance_note, enabled, created_at, updated_at
          FROM data_sources
         ORDER BY id DESC
        """
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@api_bp.route("/data-sources/<int:source_id>", methods=["DELETE"])
@admin_required
def delete_data_source(source_id):
    db = get_db()
    db.execute("DELETE FROM data_sources WHERE id = ?", (source_id,))
    db.commit()
    log_operation("delete_data_source", f"删除数据源 ID={source_id}")
    return jsonify({"ok": True, "message": "数据源已删除"})


@api_bp.route("/configs", methods=["GET", "POST"])
@admin_required
def api_configs():
    db = get_db()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        for key, value in data.items():
            db.execute(
                """
                INSERT INTO system_configs(key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (key, str(value)),
            )
        db.commit()
        log_operation("update_config", ",".join(data.keys()))
        return jsonify({"ok": True, "message": "配置已保存"})

    rows = db.execute("SELECT key, value, updated_at FROM system_configs ORDER BY key").fetchall()
    return jsonify([dict(row) for row in rows])

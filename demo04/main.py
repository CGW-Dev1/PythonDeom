from __future__ import annotations

import os
from datetime import date, timedelta

from flask import Flask, jsonify, render_template, request

from services.route_planner import RoutePlanner
from services.station_service import StationService
from services.train_client import TrainClient, TrainClientError


app = Flask(__name__)

station_service = StationService()
train_client = TrainClient(station_service)
route_planner = RoutePlanner(station_service, train_client)


@app.get("/")
def index():
    default_date = (date.today() + timedelta(days=1)).isoformat()
    return render_template("index.html", default_date=default_date)


@app.get("/api/stations")
def station_suggestions():
    keyword = request.args.get("q", "").strip()
    stations = station_service.search(keyword, limit=10)
    return jsonify([station.to_dict() for station in stations])


@app.get("/api/search")
def api_search():
    from_place = request.args.get("from", "").strip()
    to_place = request.args.get("to", "").strip()
    travel_date = request.args.get("date", "").strip()
    preference = request.args.get("preference", "balanced").strip()
    max_transfer_cities = int(request.args.get("max_transfer_cities", "6"))

    if not from_place or not to_place or not travel_date:
        return jsonify({"error": "请填写出发地、目的地和出发日期。"}), 400

    try:
        result = route_planner.plan(
            from_place=from_place,
            to_place=to_place,
            travel_date=travel_date,
            preference=preference,
            max_transfer_cities=max_transfer_cities,
        )
    except TrainClientError as exc:
        return jsonify({"error": str(exc)}), 502
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result)


@app.post("/search")
def search_page():
    from_place = request.form.get("from", "").strip()
    to_place = request.form.get("to", "").strip()
    travel_date = request.form.get("date", "").strip()
    preference = request.form.get("preference", "balanced").strip()
    max_transfer_cities = int(request.form.get("max_transfer_cities", "6"))

    try:
        result = route_planner.plan(
            from_place=from_place,
            to_place=to_place,
            travel_date=travel_date,
            preference=preference,
            max_transfer_cities=max_transfer_cities,
        )
        error = None
    except (TrainClientError, ValueError) as exc:
        result = None
        error = str(exc)

    return render_template(
        "index.html",
        default_date=travel_date or (date.today() + timedelta(days=1)).isoformat(),
        form={
            "from": from_place,
            "to": to_place,
            "date": travel_date,
            "preference": preference,
            "max_transfer_cities": max_transfer_cities,
        },
        result=result,
        error=error,
    )


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)

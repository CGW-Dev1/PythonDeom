from __future__ import annotations

import re
import time
import json
from datetime import datetime, timedelta
from typing import Any

import requests

from services.models import Station, Ticket
from services.station_service import StationService


LEFT_TICKET_ENDPOINTS = (
    "https://kyfw.12306.cn/otn/leftTicket/query",
    "https://kyfw.12306.cn/otn/leftTicket/queryG",
    "https://kyfw.12306.cn/otn/leftTicket/queryZ",
)
PRICE_ENDPOINT = "https://kyfw.12306.cn/otn/leftTicket/queryTicketPrice"
INIT_URL = "https://kyfw.12306.cn/otn/leftTicket/init"

SEAT_STOCK_FIELDS = {
    "商务座": 32,
    "特等座": 25,
    "一等座": 31,
    "二等座": 30,
    "高级软卧": 21,
    "软卧": 23,
    "硬卧": 28,
    "软座": 24,
    "硬座": 29,
    "无座": 26,
}

PRICE_FIELDS = {
    "A9": "商务座",
    "P": "特等座",
    "M": "一等座",
    "O": "二等座",
    "A6": "高级软卧",
    "A4": "软卧",
    "A3": "硬卧",
    "A2": "软座",
    "A1": "硬座",
    "WZ": "无座",
}


class TrainClientError(RuntimeError):
    pass


class TrainClient:
    def __init__(self, station_service: StationService) -> None:
        self.station_service = station_service
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                ),
                "Referer": INIT_URL,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        self._initialized = False
        self._ticket_cache: dict[tuple[str, str, str, str], tuple[float, list[Ticket]]] = {}
        self._price_cache: dict[tuple[str, str, str, str, str], dict[str, float]] = {}
        self.cache_seconds = 75
        self.request_interval = 0.12
        self._last_request_at = 0.0

    def query_tickets(
        self,
        travel_date: str,
        from_station: Station,
        to_station: Station,
        purpose: str = "ADULT",
    ) -> list[Ticket]:
        if from_station.code == to_station.code:
            return []

        cache_key = (travel_date, from_station.code, to_station.code, purpose)
        cached = self._ticket_cache.get(cache_key)
        if cached and time.time() - cached[0] < self.cache_seconds:
            return [self._copy_ticket(ticket) for ticket in cached[1]]

        self._ensure_initialized()
        params = {
            "leftTicketDTO.train_date": travel_date,
            "leftTicketDTO.from_station": from_station.code,
            "leftTicketDTO.to_station": to_station.code,
            "purpose_codes": purpose,
        }

        last_error = None
        for endpoint in LEFT_TICKET_ENDPOINTS:
            try:
                self._throttle()
                response = self.session.get(endpoint, params=params, timeout=14)
                response.encoding = "utf-8"
                payload = self._decode_json(response)
            except (requests.RequestException, ValueError, TrainClientError) as exc:
                last_error = exc
                continue

            if payload.get("status") is False and payload.get("messages"):
                last_error = TrainClientError("；".join(payload["messages"]))
                continue

            result = payload.get("data", {}).get("result", [])
            station_map = payload.get("data", {}).get("map", {})
            tickets = [
                ticket
                for item in result
                if (ticket := self._parse_ticket(item, travel_date, station_map)) is not None
            ]
            tickets.sort(key=lambda ticket: (not ticket.available, ticket.depart_at, ticket.duration_minutes))
            self._ticket_cache[cache_key] = (time.time(), [self._copy_ticket(ticket) for ticket in tickets])
            return tickets

        raise TrainClientError(f"12306 查询失败：{last_error}")

    def attach_price(self, ticket: Ticket) -> None:
        key = (
            ticket.train_internal_no,
            ticket.from_station_no,
            ticket.to_station_no,
            ticket.raw_seat_types,
            ticket.train_date,
        )
        if key in self._price_cache:
            ticket.price_map = self._price_cache[key].copy()
            return

        self._ensure_initialized()
        params = {
            "train_no": ticket.train_internal_no,
            "from_station_no": ticket.from_station_no,
            "to_station_no": ticket.to_station_no,
            "seat_types": ticket.raw_seat_types,
            "train_date": ticket.train_date,
        }
        try:
            self._throttle()
            response = self.session.get(PRICE_ENDPOINT, params=params, timeout=12)
            response.encoding = "utf-8"
            payload = self._decode_json(response)
        except (requests.RequestException, ValueError, TrainClientError):
            ticket.price_map = {}
            return

        data = payload.get("data") or {}
        price_map: dict[str, float] = {}
        for api_key, seat_name in PRICE_FIELDS.items():
            raw = data.get(api_key)
            if not raw:
                continue
            price = self._parse_price(raw)
            if price is not None:
                price_map[seat_name] = price

        self._price_cache[key] = price_map.copy()
        ticket.price_map = price_map

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self.session.get(INIT_URL, timeout=10)
        self._initialized = True

    def _parse_ticket(
        self,
        row: str,
        query_date: str,
        station_map: dict[str, str],
    ) -> Ticket | None:
        fields = row.split("|")
        if len(fields) < 36:
            return None

        train_code = fields[3]
        from_code = fields[6]
        to_code = fields[7]
        from_station = self.station_service.by_code(from_code)
        to_station = self.station_service.by_code(to_code)
        if station_map:
            from_station = Station(
                name=station_map.get(from_code, from_station.name),
                code=from_code,
                city=self.station_service.city_of(from_station),
            )
            to_station = Station(
                name=station_map.get(to_code, to_station.name),
                code=to_code,
                city=self.station_service.city_of(to_station),
            )

        duration_minutes = self._parse_duration(fields[10])
        depart_at = datetime.strptime(f"{query_date} {fields[8]}", "%Y-%m-%d %H:%M")
        arrive_at = depart_at + timedelta(minutes=duration_minutes)

        button_text = fields[1] or ""
        can_buy = fields[11] == "Y" or "预订" in button_text
        seat_stock = {
            seat: self._clean_stock(fields[index] if len(fields) > index else "")
            for seat, index in SEAT_STOCK_FIELDS.items()
        }

        return Ticket(
            train_no=fields[2],
            train_code=train_code,
            from_station=from_station,
            to_station=to_station,
            depart_at=depart_at,
            arrive_at=arrive_at,
            duration_minutes=duration_minutes,
            duration_text=fields[10],
            can_buy=can_buy,
            button_text=button_text,
            seat_stock=seat_stock,
            raw_seat_types=fields[35],
            train_internal_no=fields[2],
            from_station_no=fields[16],
            to_station_no=fields[17],
            train_date=query_date,
        )

    def _decode_json(self, response: requests.Response) -> dict[str, Any]:
        text = response.text.lstrip("\ufeff")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise TrainClientError(f"12306 返回内容无法解析：{exc}") from exc

    def _parse_duration(self, text: str) -> int:
        day_match = re.search(r"(\d+)天", text)
        days = int(day_match.group(1)) if day_match else 0
        hm_match = re.search(r"(\d{1,2}):(\d{2})", text)
        if not hm_match:
            return days * 24 * 60
        hours = int(hm_match.group(1))
        minutes = int(hm_match.group(2))
        return days * 24 * 60 + hours * 60 + minutes

    def _parse_price(self, raw: Any) -> float | None:
        text = str(raw).replace("¥", "").strip()
        try:
            return float(text)
        except ValueError:
            return None

    def _clean_stock(self, value: str) -> str:
        value = value.strip()
        return value or "--"

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        self._last_request_at = time.time()

    def _copy_ticket(self, ticket: Ticket) -> Ticket:
        return Ticket(
            train_no=ticket.train_no,
            train_code=ticket.train_code,
            from_station=ticket.from_station,
            to_station=ticket.to_station,
            depart_at=ticket.depart_at,
            arrive_at=ticket.arrive_at,
            duration_minutes=ticket.duration_minutes,
            duration_text=ticket.duration_text,
            can_buy=ticket.can_buy,
            button_text=ticket.button_text,
            seat_stock=ticket.seat_stock.copy(),
            raw_seat_types=ticket.raw_seat_types,
            train_internal_no=ticket.train_internal_no,
            from_station_no=ticket.from_station_no,
            to_station_no=ticket.to_station_no,
            train_date=ticket.train_date,
            price_map=ticket.price_map.copy(),
        )

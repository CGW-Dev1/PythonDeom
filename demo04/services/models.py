from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Station:
    name: str
    code: str
    pinyin: str = ""
    short: str = ""
    city: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "code": self.code,
            "pinyin": self.pinyin,
            "short": self.short,
            "city": self.city or self.name,
        }


@dataclass
class Ticket:
    train_no: str
    train_code: str
    from_station: Station
    to_station: Station
    depart_at: datetime
    arrive_at: datetime
    duration_minutes: int
    duration_text: str
    can_buy: bool
    button_text: str
    seat_stock: dict[str, str]
    raw_seat_types: str
    train_internal_no: str
    from_station_no: str
    to_station_no: str
    train_date: str
    price_map: dict[str, float] = field(default_factory=dict)

    @property
    def train_type(self) -> str:
        return self.train_code[:1].upper() if self.train_code else ""

    @property
    def available(self) -> bool:
        if not self.can_buy:
            return False
        return any(is_real_stock(value) for value in self.seat_stock.values())

    @property
    def min_price(self) -> float | None:
        prices = [price for price in self.price_map.values() if price > 0]
        return min(prices) if prices else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_no": self.train_no,
            "train_code": self.train_code,
            "train_type": self.train_type,
            "from_station": self.from_station.to_dict(),
            "to_station": self.to_station.to_dict(),
            "depart_at": self.depart_at.strftime("%Y-%m-%d %H:%M"),
            "arrive_at": self.arrive_at.strftime("%Y-%m-%d %H:%M"),
            "duration_minutes": self.duration_minutes,
            "duration_text": self.duration_text,
            "can_buy": self.can_buy,
            "button_text": self.button_text,
            "available": self.available,
            "seat_stock": self.seat_stock,
            "price_map": self.price_map,
            "min_price": self.min_price,
        }


@dataclass
class RouteOption:
    legs: list[Ticket]
    distance_km: float
    wait_minutes: int = 0
    station_change_minutes: int = 0
    total_price: float | None = None
    score: float = 0
    recommendation: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def transfer_count(self) -> int:
        return max(len(self.legs) - 1, 0)

    @property
    def depart_at(self) -> datetime:
        return self.legs[0].depart_at

    @property
    def arrive_at(self) -> datetime:
        return self.legs[-1].arrive_at

    @property
    def total_minutes(self) -> int:
        return int((self.arrive_at - self.depart_at).total_seconds() // 60)

    @property
    def available(self) -> bool:
        return all(leg.available for leg in self.legs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "legs": [leg.to_dict() for leg in self.legs],
            "transfer_count": self.transfer_count,
            "distance_km": round(self.distance_km, 1),
            "wait_minutes": self.wait_minutes,
            "station_change_minutes": self.station_change_minutes,
            "total_price": round(self.total_price, 1) if self.total_price else None,
            "score": round(self.score, 4),
            "recommendation": self.recommendation,
            "reasons": self.reasons,
            "total_minutes": self.total_minutes,
            "depart_at": self.depart_at.strftime("%Y-%m-%d %H:%M"),
            "arrive_at": self.arrive_at.strftime("%Y-%m-%d %H:%M"),
            "available": self.available,
        }


def is_real_stock(value: str) -> bool:
    if not value:
        return False
    clean = value.strip()
    if clean in {"--", "无", "候补", "*"}:
        return False
    return True

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

from services.geo_data import PREFERRED_STATIONS
from services.models import Station


STATION_URL = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"


class StationService:
    def __init__(self, cache_path: str | Path = "data/station_name.js") -> None:
        self.cache_path = Path(cache_path)
        self._stations: list[Station] | None = None
        self._by_name: dict[str, Station] = {}
        self._by_code: dict[str, Station] = {}

    def all(self) -> list[Station]:
        if self._stations is None:
            self._stations = self._load_stations()
            self._by_name = {station.name: station for station in self._stations}
            self._by_code = {station.code: station for station in self._stations}
        return self._stations

    def by_code(self, code: str) -> Station:
        self.all()
        return self._by_code.get(code, Station(name=code, code=code))

    def by_name(self, name: str) -> Station | None:
        self.all()
        return self._by_name.get(name)

    def search(self, keyword: str, limit: int = 10) -> list[Station]:
        keyword = keyword.strip().lower()
        if not keyword:
            return []
        stations = self.all()
        exact = [
            station
            for station in stations
            if station.name == keyword or station.name.lower() == keyword
        ]
        prefix = [
            station
            for station in stations
            if station.name.startswith(keyword)
            or station.pinyin.startswith(keyword)
            or station.short.startswith(keyword)
        ]
        city = [station for station in stations if station.city == keyword]
        fuzzy = [
            station
            for station in stations
            if keyword in station.name.lower() or keyword in station.pinyin
        ]
        return self._unique(exact + self._sort_preferred(city, keyword) + prefix + fuzzy)[:limit]

    def resolve(self, text: str, max_count: int = 3) -> list[Station]:
        text = text.strip()
        if not text:
            return []
        stations = self.all()
        preferred_names = PREFERRED_STATIONS.get(text, [])
        preferred = [self.by_name(name) for name in preferred_names]
        preferred = [station for station in preferred if station is not None]

        exact = [station for station in stations if station.name == text]
        same_city = [station for station in stations if station.city == text]
        starts = [station for station in stations if station.name.startswith(text)]
        pinyin = [
            station
            for station in stations
            if station.pinyin.startswith(text.lower()) or station.short.startswith(text.lower())
        ]
        resolved = self._unique(preferred + exact + same_city + starts + pinyin)
        return resolved[:max_count]

    def city_of(self, station: Station) -> str:
        return station.city or self._guess_city(station.name)

    def _load_stations(self) -> list[Station]:
        text = self._read_or_fetch_station_text()
        match = re.search(r"var\s+station_names\s*=\s*'(.*)'", text)
        raw = match.group(1) if match else text
        stations: list[Station] = []

        for item in raw.split("@"):
            parts = item.split("|")
            if len(parts) < 4:
                continue
            name = parts[1]
            code = parts[2]
            city = parts[7] if len(parts) > 7 and parts[7] else self._guess_city(name)
            stations.append(
                Station(
                    name=name,
                    code=code,
                    pinyin=parts[3].lower(),
                    short=parts[4].lower() if len(parts) > 4 else "",
                    city=city,
                )
            )
        return stations

    def _read_or_fetch_station_text(self) -> str:
        should_fetch = True
        if self.cache_path.exists():
            modified = datetime.fromtimestamp(self.cache_path.stat().st_mtime)
            should_fetch = datetime.now() - modified > timedelta(days=7)

        if should_fetch:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            response = requests.get(
                STATION_URL,
                timeout=12,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            self.cache_path.write_text(response.text, encoding="utf-8")

        return self.cache_path.read_text(encoding="utf-8")

    def _sort_preferred(self, stations: list[Station], city: str) -> list[Station]:
        preferred_names = PREFERRED_STATIONS.get(city, [])
        order = {name: index for index, name in enumerate(preferred_names)}
        return sorted(stations, key=lambda station: order.get(station.name, 99))

    def _unique(self, stations: list[Station]) -> list[Station]:
        seen: set[str] = set()
        result: list[Station] = []
        for station in stations:
            if station.code in seen:
                continue
            seen.add(station.code)
            result.append(station)
        return result

    def _guess_city(self, station_name: str) -> str:
        suffixes = [
            "东",
            "西",
            "南",
            "北",
            "站",
            "新区",
            "机场",
        ]
        for suffix in suffixes:
            if station_name.endswith(suffix) and len(station_name) > len(suffix) + 1:
                return station_name[: -len(suffix)]
        return station_name

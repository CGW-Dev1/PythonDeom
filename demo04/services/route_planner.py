from __future__ import annotations

import math
from datetime import date, timedelta

from services.geo_data import CITY_COORDS, MAJOR_TRANSFER_CITIES
from services.models import RouteOption, Station, Ticket
from services.station_service import StationService
from services.train_client import TrainClient


PREFERENCE_WEIGHTS = {
    "balanced": {"distance": 0.35, "price": 0.30, "time": 0.25, "transfer": 0.10},
    "distance": {"distance": 0.55, "price": 0.20, "time": 0.15, "transfer": 0.10},
    "price": {"distance": 0.20, "price": 0.55, "time": 0.15, "transfer": 0.10},
    "time": {"distance": 0.20, "price": 0.20, "time": 0.50, "transfer": 0.10},
    "transfer": {"distance": 0.25, "price": 0.20, "time": 0.15, "transfer": 0.40},
}

TRAIN_PRICE_RATE = {
    "G": 0.47,
    "D": 0.32,
    "C": 0.30,
    "Z": 0.14,
    "T": 0.13,
    "K": 0.11,
}


class RoutePlanner:
    def __init__(self, station_service: StationService, train_client: TrainClient) -> None:
        self.station_service = station_service
        self.train_client = train_client
        self.min_transfer_minutes = 35
        self.max_wait_minutes = 12 * 60
        self.max_trains_per_leg = 6
        self.max_candidate_routes_before_price = 45

    def plan(
        self,
        from_place: str,
        to_place: str,
        travel_date: str,
        preference: str = "balanced",
        max_transfer_cities: int = 6,
    ) -> dict:
        trip_date = date.fromisoformat(travel_date)
        if trip_date < date.today():
            raise ValueError("出发日期不能早于今天。")

        origin_stations = self.station_service.resolve(from_place, max_count=2)
        destination_stations = self.station_service.resolve(to_place, max_count=2)
        if not origin_stations:
            raise ValueError(f"没有找到出发地：{from_place}")
        if not destination_stations:
            raise ValueError(f"没有找到目的地：{to_place}")

        direct_routes = self._find_direct_routes(travel_date, origin_stations, destination_stations)
        transfer_cities = self._select_transfer_cities(
            origin_stations[0],
            destination_stations[0],
            max_transfer_cities,
        )
        transfer_routes = self._find_one_transfer_routes(
            trip_date,
            origin_stations,
            destination_stations,
            transfer_cities,
        )

        routes = self._dedupe_routes(direct_routes + transfer_routes)
        routes = self._rough_rank(routes)[: self.max_candidate_routes_before_price]
        self._attach_prices(routes)
        self._score_routes(routes, preference)
        routes.sort(key=lambda route: (route.score, not route.available, route.total_minutes))

        top_routes = routes[:20]
        return {
            "query": {
                "from": from_place,
                "to": to_place,
                "date": travel_date,
                "preference": preference,
                "origin_candidates": [station.to_dict() for station in origin_stations],
                "destination_candidates": [station.to_dict() for station in destination_stations],
                "transfer_cities": transfer_cities,
            },
            "summary": {
                "direct_count": len(direct_routes),
                "transfer_count": len(transfer_routes),
                "returned_count": len(top_routes),
                "data_source": "12306 real-time query",
            },
            "routes": [route.to_dict() for route in top_routes],
        }

    def _find_direct_routes(
        self,
        travel_date: str,
        origins: list[Station],
        destinations: list[Station],
    ) -> list[RouteOption]:
        routes: list[RouteOption] = []
        for origin in origins:
            for destination in destinations:
                tickets = self.train_client.query_tickets(travel_date, origin, destination)
                for ticket in tickets[: self.max_trains_per_leg * 2]:
                    routes.append(
                        RouteOption(
                            legs=[ticket],
                            distance_km=self._leg_distance(ticket),
                            recommendation="直达",
                            reasons=["真实直达车次", "无需换乘"],
                        )
                    )
        return routes

    def _find_one_transfer_routes(
        self,
        trip_date: date,
        origins: list[Station],
        destinations: list[Station],
        transfer_cities: list[str],
    ) -> list[RouteOption]:
        routes: list[RouteOption] = []
        for city in transfer_cities:
            transfer_stations = self.station_service.resolve(city, max_count=3)
            if not transfer_stations:
                continue

            leg1_tickets = self._query_leg_set(
                trip_date.isoformat(),
                origins,
                transfer_stations,
            )
            leg2_tickets = self._query_leg_set(
                trip_date.isoformat(),
                transfer_stations,
                destinations,
            ) + self._query_leg_set(
                (trip_date + timedelta(days=1)).isoformat(),
                transfer_stations,
                destinations,
            )

            city_routes = self._pair_transfer_legs(leg1_tickets, leg2_tickets)
            routes.extend(city_routes[:18])
        return routes

    def _query_leg_set(
        self,
        travel_date: str,
        origins: list[Station],
        destinations: list[Station],
    ) -> list[Ticket]:
        result: list[Ticket] = []
        for origin in origins:
            for destination in destinations:
                if origin.code == destination.code:
                    continue
                tickets = self.train_client.query_tickets(travel_date, origin, destination)
                result.extend(tickets[: self.max_trains_per_leg])

        result.sort(key=lambda ticket: (not ticket.available, ticket.duration_minutes, ticket.depart_at))
        return self._dedupe_tickets(result)[: self.max_trains_per_leg * 3]

    def _pair_transfer_legs(self, leg1_tickets: list[Ticket], leg2_tickets: list[Ticket]) -> list[RouteOption]:
        routes: list[RouteOption] = []
        for leg1 in leg1_tickets:
            for leg2 in leg2_tickets:
                if self.station_service.city_of(leg1.to_station) != self.station_service.city_of(leg2.from_station):
                    continue
                station_change_minutes = 0 if leg1.to_station.code == leg2.from_station.code else 60
                min_wait = self.min_transfer_minutes + station_change_minutes
                wait_minutes = int((leg2.depart_at - leg1.arrive_at).total_seconds() // 60)
                if wait_minutes < min_wait or wait_minutes > self.max_wait_minutes:
                    continue

                distance = self._leg_distance(leg1) + self._leg_distance(leg2)
                reason = "同站换乘" if station_change_minutes == 0 else "同城跨站换乘"
                routes.append(
                    RouteOption(
                        legs=[leg1, leg2],
                        distance_km=distance,
                        wait_minutes=wait_minutes,
                        station_change_minutes=station_change_minutes,
                        recommendation="中转",
                        reasons=["12306 真实车次组合", reason],
                    )
                )

        routes.sort(key=lambda route: (not route.available, route.total_minutes, route.distance_km))
        return routes

    def _select_transfer_cities(
        self,
        origin: Station,
        destination: Station,
        limit: int,
    ) -> list[str]:
        origin_city = self.station_service.city_of(origin)
        dest_city = self.station_service.city_of(destination)
        direct_distance = self._city_distance(origin_city, dest_city) or 1
        scored: list[tuple[float, str]] = []

        for city in MAJOR_TRANSFER_CITIES:
            if city in {origin_city, dest_city}:
                continue
            d1 = self._city_distance(origin_city, city)
            d2 = self._city_distance(city, dest_city)
            if not d1 or not d2:
                continue
            route_distance = d1 + d2
            detour_ratio = route_distance / direct_distance
            if detour_ratio > 1.65:
                continue
            hub_bonus = 0 if city in {"北京", "沈阳", "郑州", "武汉", "济南", "天津"} else 120
            scored.append((route_distance + hub_bonus, city))

        scored.sort(key=lambda item: item[0])
        selected = [city for _, city in scored[: max(limit, 1)]]
        selected = self._merge_strategic_cities(origin_city, dest_city, selected, limit)
        if not selected:
            selected = [city for city in MAJOR_TRANSFER_CITIES if city not in {origin_city, dest_city}][:limit]
        return selected

    def _merge_strategic_cities(
        self,
        origin_city: str,
        dest_city: str,
        selected: list[str],
        limit: int,
    ) -> list[str]:
        northeast = {"沈阳", "铁岭", "长春", "哈尔滨", "大连", "锦州", "四平"}
        south = {"广州", "深圳", "长沙", "武汉", "南昌", "福州", "厦门"}
        strategic: list[str] = []
        if (origin_city in south and dest_city in northeast) or (
            origin_city in northeast and dest_city in south
        ):
            strategic = ["沈阳", "北京", "天津", "济南", "郑州", "武汉"]

        result: list[str] = []
        for city in strategic + selected:
            if city in {origin_city, dest_city} or city in result:
                continue
            result.append(city)
        return result[:limit]

    def _attach_prices(self, routes: list[RouteOption]) -> None:
        for route in routes:
            for leg in route.legs:
                if not leg.price_map:
                    self.train_client.attach_price(leg)
            prices = [leg.min_price for leg in route.legs]
            if all(price is not None for price in prices):
                route.total_price = sum(price for price in prices if price is not None)
            else:
                route.total_price = self._estimate_route_price(route)

    def _score_routes(self, routes: list[RouteOption], preference: str) -> None:
        if not routes:
            return
        weights = PREFERENCE_WEIGHTS.get(preference, PREFERENCE_WEIGHTS["balanced"])
        distances = [route.distance_km for route in routes]
        prices = [route.total_price or self._estimate_route_price(route) for route in routes]
        times = [route.total_minutes for route in routes]
        transfers = [route.transfer_count for route in routes]

        for route in routes:
            distance_score = self._normalize(route.distance_km, distances)
            price_score = self._normalize(route.total_price or self._estimate_route_price(route), prices)
            time_score = self._normalize(route.total_minutes, times)
            transfer_score = self._normalize(route.transfer_count, transfers)
            stock_penalty = 0 if route.available else 0.12
            wait_penalty = min(route.wait_minutes / 7200, 0.08)
            route.score = (
                distance_score * weights["distance"]
                + price_score * weights["price"]
                + time_score * weights["time"]
                + transfer_score * weights["transfer"]
                + stock_penalty
                + wait_penalty
            )
            route.recommendation = self._recommendation_label(route, routes)
            route.reasons = self._build_reasons(route, routes)

    def _recommendation_label(self, route: RouteOption, routes: list[RouteOption]) -> str:
        min_distance = min(item.distance_km for item in routes)
        min_price = min((item.total_price or self._estimate_route_price(item)) for item in routes)
        min_time = min(item.total_minutes for item in routes)
        if route.distance_km <= min_distance * 1.03:
            return "距离较短"
        if (route.total_price or 0) <= min_price * 1.03:
            return "价格较低"
        if route.total_minutes <= min_time * 1.03:
            return "时间较短"
        if route.transfer_count == 0:
            return "直达优先"
        return "综合推荐"

    def _build_reasons(self, route: RouteOption, routes: list[RouteOption]) -> list[str]:
        reasons = list(route.reasons)
        if route.transfer_count == 0:
            reasons.append("没有中转等待")
        else:
            reasons.append(f"换乘等待约 {route.wait_minutes // 60}小时{route.wait_minutes % 60}分钟")
        if route.available:
            reasons.append("各段均显示可购或有余票")
        else:
            reasons.append("存在候补或暂不可购席别")
        if route.total_price:
            reasons.append(f"最低票价约 {route.total_price:.1f} 元")
        return reasons[:5]

    def _rough_rank(self, routes: list[RouteOption]) -> list[RouteOption]:
        return sorted(routes, key=lambda route: (not route.available, route.transfer_count, route.distance_km, route.total_minutes))

    def _dedupe_routes(self, routes: list[RouteOption]) -> list[RouteOption]:
        seen: set[tuple[str, ...]] = set()
        result: list[RouteOption] = []
        for route in routes:
            key = tuple(
                f"{leg.train_code}:{leg.from_station.code}:{leg.to_station.code}:{leg.depart_at.isoformat()}"
                for leg in route.legs
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(route)
        return result

    def _dedupe_tickets(self, tickets: list[Ticket]) -> list[Ticket]:
        seen: set[tuple[str, str, str, str]] = set()
        result: list[Ticket] = []
        for ticket in tickets:
            key = (
                ticket.train_code,
                ticket.from_station.code,
                ticket.to_station.code,
                ticket.depart_at.isoformat(),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(ticket)
        return result

    def _leg_distance(self, ticket: Ticket) -> float:
        distance = self._city_distance(
            self.station_service.city_of(ticket.from_station),
            self.station_service.city_of(ticket.to_station),
        )
        if distance:
            return distance
        return max(ticket.duration_minutes / 60 * 110, 80)

    def _estimate_route_price(self, route: RouteOption) -> float:
        total = 0.0
        for leg in route.legs:
            rate = TRAIN_PRICE_RATE.get(leg.train_type, 0.12)
            total += self._leg_distance(leg) * rate
        return total

    def _city_distance(self, city_a: str, city_b: str) -> float | None:
        coord_a = CITY_COORDS.get(city_a)
        coord_b = CITY_COORDS.get(city_b)
        if not coord_a or not coord_b:
            return None
        return haversine_km(coord_a, coord_b) * 1.12

    def _normalize(self, value: float, values: list[float]) -> float:
        minimum = min(values)
        maximum = max(values)
        if math.isclose(minimum, maximum):
            return 0.0
        return (value - minimum) / (maximum - minimum)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(value), math.sqrt(1 - value))

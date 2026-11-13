"""Optional SerpApi Google Flights provider (requires SERPAPI_API_KEY)."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

import httpx

from beach_flights.core.destinations import get_airport_timezone
from beach_flights.models import FlightLeg, RoundTripOffer
from beach_flights.providers.fli_provider import build_google_flights_url
from beach_flights.providers.http_utils import create_http_client

SERPAPI_URL = "https://serpapi.com/search.json"


class SerpApiProvider:
    """FlightProvider backed by SerpApi's `google_flights` engine."""

    name = "serpapi"

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("SERPAPI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "SERPAPI_API_KEY is required when using --provider serpapi."
            )
        self._owns_client = client is None
        self._client = client or create_http_client(timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search_one_way(
        self,
        origins: list[str],
        destinations: list[str],
        travel_date: date,
        sort_mode: Literal["cheapest", "departure_time"] = "cheapest",
    ) -> list[FlightLeg]:
        params = {
            "engine": "google_flights",
            "api_key": self._api_key,
            "departure_id": ",".join(o.upper() for o in origins),
            "arrival_id": ",".join(d.upper() for d in destinations),
            "outbound_date": travel_date.isoformat(),
            "type": "2",  # One way
            "stops": "1",  # Non-stop only
            "currency": "GBP",
            "hl": "en",
            "gl": "uk",
            "sort_by": "3" if sort_mode == "departure_time" else "2",
        }
        resp = self._client.get(SERPAPI_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        groups = (data.get("best_flights") or []) + (data.get("other_flights") or [])
        legs: list[FlightLeg] = []
        for group in groups:
            flight_segs = group.get("flights") or []
            if len(flight_segs) != 1:
                continue
            seg = flight_segs[0]
            price = group.get("price")
            if price is None:
                continue
            dep_ap = (seg.get("departure_airport") or {}).get("id", "")
            arr_ap = (seg.get("arrival_airport") or {}).get("id", "")
            dep_str = (seg.get("departure_airport") or {}).get("time", "")
            arr_str = (seg.get("arrival_airport") or {}).get("time", "")
            if not (dep_ap and arr_ap and dep_str and arr_str):
                continue

            dep_dt = datetime.strptime(dep_str, "%Y-%m-%d %H:%M").replace(
                tzinfo=ZoneInfo(get_airport_timezone(dep_ap))
            )
            arr_dt = datetime.strptime(arr_str, "%Y-%m-%d %H:%M").replace(
                tzinfo=ZoneInfo(get_airport_timezone(arr_ap))
            )
            legs.append(
                FlightLeg(
                    origin=dep_ap,
                    destination=arr_ap,
                    airline=seg.get("airline", "Unknown"),
                    flight_number=seg.get("flight_number", ""),
                    departure_dt=dep_dt,
                    arrival_dt=arr_dt,
                    duration_minutes=int(seg.get("duration") or group.get("total_duration") or 0),
                    stops=0,
                    price_gbp=round(float(price), 2),
                    booking_url=build_google_flights_url(dep_ap, arr_ap, travel_date),
                )
            )
        return legs

    def search_round_trip(
        self,
        origin: str,
        destination: str,
        outbound_date: date,
        return_date: date,
        top_n: int = 8,
    ) -> list[RoundTripOffer]:
        # SerpApi requires per-departure_token follow-up calls for round trips;
        # one-way pairing already covers open-jaw and LCC fares cleanly.
        return []

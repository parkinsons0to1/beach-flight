"""Google Flights provider powered by `fli` (`flights` PyPI package)."""

from __future__ import annotations

import random
import threading
import time
from datetime import date, datetime
from typing import Literal
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from fli.models import (
    Airport,
    FlightResult,
    FlightSearchFilters,
    FlightSegment,
    MaxStops,
    PassengerInfo,
    SeatType,
    SortBy,
    TripType,
)
from fli.search import SearchFlights

from beach_flights.core.destinations import get_airport_timezone
from beach_flights.models import FlightLeg, RoundTripOffer


def build_google_flights_url(
    origin: str,
    destination: str,
    outbound_date: date,
    return_date: date | None = None,
) -> str:
    """Construct a deep-link query URL to Google Flights in GBP."""
    if return_date is not None:
        query = (
            f"Flights to {destination} from {origin} "
            f"on {outbound_date.isoformat()} through {return_date.isoformat()}"
        )
    else:
        query = f"One way flights to {destination} from {origin} on {outbound_date.isoformat()}"
    return f"https://www.google.com/travel/flights?q={quote_plus(query)}&curr=GBP&hl=en-GB"


def _attach_tz(dt: datetime, airport_iata: str) -> datetime:
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=ZoneInfo(get_airport_timezone(airport_iata)))


def _map_result_to_leg(
    result: FlightResult,
    override_price: float | None = None,
    return_date: date | None = None,
) -> FlightLeg | None:
    if not result.legs:
        return None
    # Non-stop journeys have 1 leg; guard against unexpected multi-leg rows.
    if len(result.legs) != 1:
        return None

    leg = result.legs[0]
    dep_iata = leg.departure_airport.name
    arr_iata = leg.arrival_airport.name
    dep_dt = _attach_tz(leg.departure_datetime, dep_iata)
    arr_dt = _attach_tz(leg.arrival_datetime, arr_iata)
    airline_name = leg.airline.value if hasattr(leg.airline, "value") else str(leg.airline)
    price = float(override_price if override_price is not None else result.price)

    return FlightLeg(
        origin=dep_iata,
        destination=arr_iata,
        airline=airline_name,
        flight_number=leg.flight_number,
        departure_dt=dep_dt,
        arrival_dt=arr_dt,
        duration_minutes=int(leg.duration),
        stops=int(result.stops),
        price_gbp=round(price, 2),
        booking_url=build_google_flights_url(
            origin=dep_iata,
            destination=arr_iata,
            outbound_date=dep_dt.date(),
            return_date=return_date,
        ),
    )


class FliProvider:
    """FlightProvider implementation using `fli` against Google Flights."""

    name = "fli"

    def __init__(
        self,
        search_client: SearchFlights | None = None,
        min_delay_s: float = 0.25,
        max_delay_s: float = 0.7,
        max_retries: int = 2,
    ) -> None:
        self._client = search_client or SearchFlights()
        self._min_delay_s = min_delay_s
        self._max_delay_s = max_delay_s
        self._max_retries = max_retries
        self._lock = threading.Lock()
        self._last_request_ts = 0.0

    def _pace(self) -> None:
        if self._max_delay_s <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delay = random.uniform(self._min_delay_s, self._max_delay_s)
            wait = (self._last_request_ts + delay) - now
            if wait > 0:
                time.sleep(wait)
            self._last_request_ts = time.monotonic()

    def _run_with_retry(
        self,
        filters: FlightSearchFilters,
        top_n: int = 5,
    ):
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._pace()
            try:
                return self._client.search(
                    filters,
                    top_n=top_n,
                    currency="GBP",
                    language="en-GB",
                    country="GB",
                )
            except Exception as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    time.sleep(0.8 * (attempt + 1))
        if last_exc is not None:
            raise last_exc
        return None

    def search_one_way(
        self,
        origins: list[str],
        destinations: list[str],
        travel_date: date,
        sort_mode: Literal["cheapest", "departure_time"] = "cheapest",
    ) -> list[FlightLeg]:
        dep_airports = [[Airport[o.upper()], 0] for o in origins]
        arr_airports = [[Airport[d.upper()], 0] for d in destinations]
        sort_by = SortBy.DEPARTURE_TIME if sort_mode == "departure_time" else SortBy.CHEAPEST

        filters = FlightSearchFilters(
            trip_type=TripType.ONE_WAY,
            passenger_info=PassengerInfo(adults=1),
            flight_segments=[
                FlightSegment(
                    departure_airport=dep_airports,
                    arrival_airport=arr_airports,
                    travel_date=travel_date.isoformat(),
                )
            ],
            seat_type=SeatType.ECONOMY,
            stops=MaxStops.NON_STOP,
            sort_by=sort_by,
        )

        raw_results = self._run_with_retry(filters)
        if not raw_results:
            return []

        legs: list[FlightLeg] = []
        for res in raw_results:
            if isinstance(res, FlightResult):
                mapped = _map_result_to_leg(res)
                if mapped is not None and mapped.price_gbp > 0:
                    legs.append(mapped)
        return legs

    def search_round_trip(
        self,
        origin: str,
        destination: str,
        outbound_date: date,
        return_date: date,
        top_n: int = 8,
    ) -> list[RoundTripOffer]:
        dep_ap = Airport[origin.upper()]
        arr_ap = Airport[destination.upper()]

        filters = FlightSearchFilters(
            trip_type=TripType.ROUND_TRIP,
            passenger_info=PassengerInfo(adults=1),
            flight_segments=[
                FlightSegment(
                    departure_airport=[[dep_ap, 0]],
                    arrival_airport=[[arr_ap, 0]],
                    travel_date=outbound_date.isoformat(),
                ),
                FlightSegment(
                    departure_airport=[[arr_ap, 0]],
                    arrival_airport=[[dep_ap, 0]],
                    travel_date=return_date.isoformat(),
                ),
            ],
            seat_type=SeatType.ECONOMY,
            stops=MaxStops.NON_STOP,
            sort_by=SortBy.DEPARTURE_TIME,
        )

        raw_results = self._run_with_retry(filters, top_n=min(max(top_n, 1), 10))
        if not raw_results:
            return []

        offers: list[RoundTripOffer] = []
        for item in raw_results:
            if not isinstance(item, tuple) or len(item) != 2:
                continue
            out_res, in_res = item
            # On Google Flights round-trip expansion, the final leg carries the full RT price.
            total_price = float(in_res.price if in_res.price > 0 else out_res.price)
            if total_price <= 0:
                continue
            out_leg = _map_result_to_leg(out_res, override_price=total_price / 2.0)
            in_leg = _map_result_to_leg(
                in_res, override_price=total_price / 2.0, return_date=return_date
            )
            if out_leg is None or in_leg is None:
                continue
            offers.append(
                RoundTripOffer(
                    outbound=out_leg,
                    inbound=in_leg,
                    total_price_gbp=round(total_price, 2),
                    booking_url=build_google_flights_url(
                        origin=origin.upper(),
                        destination=destination.upper(),
                        outbound_date=outbound_date,
                        return_date=return_date,
                    ),
                )
            )
        return offers

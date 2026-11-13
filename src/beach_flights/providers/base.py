"""Abstract provider interface for flight searches."""

from __future__ import annotations

from datetime import date
from typing import Literal, Protocol

from beach_flights.models import FlightLeg, RoundTripOffer


class FlightProvider(Protocol):
    """Protocol implemented by flight search backends (fli, SerpApi, etc.)."""

    name: str

    def search_one_way(
        self,
        origins: list[str],
        destinations: list[str],
        travel_date: date,
        sort_mode: Literal["cheapest", "departure_time"] = "cheapest",
    ) -> list[FlightLeg]:
        """Fetch non-stop one-way flight legs on a specific date."""
        ...

    def search_round_trip(
        self,
        origin: str,
        destination: str,
        outbound_date: date,
        return_date: date,
        top_n: int = 8,
    ) -> list[RoundTripOffer]:
        """Fetch non-stop bundled round-trip offers for a same-airport pair."""
        ...

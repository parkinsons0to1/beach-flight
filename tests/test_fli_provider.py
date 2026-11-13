"""Tests for FliProvider mapping (mocked) and optional live smoke test."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from fli.models import Airline, Airport, FlightResult
from fli.models import FlightLeg as FliLeg

from beach_flights.providers.fli_provider import FliProvider


class FakeSearchClient:
    def search(self, filters, top_n=5, currency=None, language=None, country=None):
        ba = next(a for a in Airline if a.name == "BA")
        leg = FliLeg(
            airline=ba,
            flight_number="BA452",
            departure_airport=Airport.LHR,
            arrival_airport=Airport.AGP,
            departure_datetime=datetime(2026, 11, 21, 7, 15),
            arrival_datetime=datetime(2026, 11, 21, 11, 5),
            duration=170,
        )
        return [
            FlightResult(
                legs=[leg],
                price=54.0,
                duration=170,
                stops=0,
            )
        ]


def test_fli_provider_maps_and_attaches_timezones() -> None:
    provider = FliProvider(search_client=FakeSearchClient(), min_delay_s=0.0, max_delay_s=0.0)
    legs = provider.search_one_way(["LGW", "LHR"], ["AGP"], date(2026, 11, 21))
    assert len(legs) == 1
    leg = legs[0]
    assert leg.origin == "LHR"
    assert leg.destination == "AGP"
    assert leg.airline == "British Airways"
    assert leg.price_gbp == 54.0
    assert leg.departure_dt.tzinfo is not None
    assert leg.arrival_dt.tzinfo is not None
    assert "google.com/travel/flights" in (leg.booking_url or "")


@pytest.mark.live
def test_fli_provider_live_smoke() -> None:
    provider = FliProvider()
    legs = provider.search_one_way(["LGW", "LHR"], ["AGP"], date(2026, 11, 21))
    assert isinstance(legs, list)

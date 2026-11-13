"""Tests for FastAPI dashboard and API endpoints."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from beach_flights.models import FlightLeg, ScoredTrip
from beach_flights.storage.db import FlightDatabase
from beach_flights.web.app import create_app


def _seed_db(db_path: Path) -> None:
    db = FlightDatabase(db_path)
    scan_id = db.create_scan(
        provider="fli",
        date_from=date(2026, 11, 21),
        date_to=date(2026, 11, 22),
        params={},
        status="completed",
    )
    lon = ZoneInfo("Europe/London")
    can = ZoneInfo("Atlantic/Canary")
    out_leg = FlightLeg(
        origin="LGW",
        destination="TFS",
        airline="easyJet",
        flight_number="EZY8701",
        departure_dt=datetime(2026, 11, 21, 6, 45, tzinfo=lon),
        arrival_dt=datetime(2026, 11, 21, 11, 15, tzinfo=can),
        duration_minutes=270,
        stops=0,
        price_gbp=55.0,
    )
    in_leg = FlightLeg(
        origin="TFS",
        destination="LHR",
        airline="British Airways",
        flight_number="BA2703",
        departure_dt=datetime(2026, 11, 22, 20, 0, tzinfo=can),
        arrival_dt=datetime(2026, 11, 23, 0, 20, tzinfo=lon),
        duration_minutes=260,
        stops=0,
        price_gbp=65.0,
    )
    trip = ScoredTrip(
        weekend_date=date(2026, 11, 21),
        return_date=date(2026, 11, 22),
        destination="TFS",
        destination_name="Tenerife South",
        country="Spain",
        outbound=out_leg,
        inbound=in_leg,
        is_open_jaw=True,
        pricing_mode="one_way_pair",
        total_price_gbp=120.0,
        beach_hours=32.75,
        gbp_per_beach_hour=3.66,
        sea_temp_c=21.8,
        sea_temp_source="forecast",
        is_swimmable=True,
        booking_url="https://www.google.com/travel/flights",
    )
    db.save_offers(scan_id, [trip])


def test_web_endpoints(tmp_path: Path) -> None:
    db_path = tmp_path / "web.db"
    _seed_db(db_path)
    app = create_app(db_path=db_path)
    client = TestClient(app)

    home = client.get("/")
    assert home.status_code == 200
    assert "Beach Flights" in home.text

    dests = client.get("/api/destinations")
    assert dests.status_code == 200
    assert len(dests.json()) >= 20

    deals = client.get("/api/deals?min_sea_temp_c=17.0")
    assert deals.status_code == 200
    payload = deals.json()
    assert payload["count"] == 1
    assert payload["deals"][0]["best"]["destination"] == "TFS"
    assert payload["deals"][0]["best"]["sea_temp_c"] == 21.8

    # High sea-temp filter excludes 21.8°C
    strict = client.get("/api/deals?min_sea_temp_c=25.0")
    assert strict.status_code == 200
    assert strict.json()["count"] == 0

    hist = client.get("/api/history?destination=TFS&weekend_date=2026-11-21")
    assert hist.status_code == 200
    assert len(hist.json()["history"]) == 1

"""Tests for SQLite persistence, grouping, price deltas, and history queries."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from beach_flights.models import FlightLeg, ScoredTrip
from beach_flights.storage.db import FlightDatabase

LON = ZoneInfo("Europe/London")
MAD = ZoneInfo("Europe/Madrid")


def _trip(
    *,
    dest: str = "AGP",
    dest_name: str = "Malaga",
    wk: date = date(2026, 11, 21),
    out_origin: str = "LGW",
    in_dest: str = "LHR",
    out_flight: str = "EZY801",
    in_flight: str = "BA455",
    price: float = 90.0,
    beach_hours: float = 35.0,
    sea_temp_c: float = 18.5,
) -> ScoredTrip:
    out_leg = FlightLeg(
        origin=out_origin,
        destination=dest,
        airline="easyJet",
        flight_number=out_flight,
        departure_dt=datetime(wk.year, wk.month, wk.day, 6, 30, tzinfo=LON),
        arrival_dt=datetime(wk.year, wk.month, wk.day, 10, 15, tzinfo=MAD),
        duration_minutes=165,
        stops=0,
        price_gbp=price / 2,
    )
    ret = date(wk.year, wk.month, wk.day + 1)
    in_leg = FlightLeg(
        origin=dest,
        destination=in_dest,
        airline="British Airways",
        flight_number=in_flight,
        departure_dt=datetime(ret.year, ret.month, ret.day, 21, 15, tzinfo=MAD),
        arrival_dt=datetime(ret.year, ret.month, ret.day, 23, 0, tzinfo=LON),
        duration_minutes=165,
        stops=0,
        price_gbp=price / 2,
    )
    return ScoredTrip(
        weekend_date=wk,
        return_date=ret,
        destination=dest,
        destination_name=dest_name,
        country="Spain",
        outbound=out_leg,
        inbound=in_leg,
        is_open_jaw=(out_origin != in_dest),
        pricing_mode="one_way_pair",
        total_price_gbp=price,
        beach_hours=beach_hours,
        gbp_per_beach_hour=round(price / beach_hours, 2),
        sea_temp_c=sea_temp_c,
        sea_temp_source="live",
        is_swimmable=(sea_temp_c >= 17.0),
    )


def test_db_groups_alternatives_and_tracks_price_drops(tmp_path: Path) -> None:
    db = FlightDatabase(tmp_path / "test.db")

    s1 = db.create_scan(
        provider="fli",
        date_from=date(2026, 11, 21),
        date_to=date(2026, 11, 22),
        params={},
        status="completed",
    )
    db.save_offers(
        s1,
        [
            _trip(price=110.0, out_flight="EZY1", in_flight="BA1"),
            _trip(price=125.0, out_flight="EZY2", in_flight="BA2"),
        ],
    )

    s2 = db.create_scan(
        provider="fli",
        date_from=date(2026, 11, 21),
        date_to=date(2026, 11, 22),
        params={},
        status="completed",
    )
    db.save_offers(
        s2,
        [
            _trip(price=88.0, out_flight="EZY1", in_flight="BA1"),
            _trip(price=96.0, out_flight="EZY2", in_flight="BA2"),
            _trip(dest="NCE", dest_name="Nice", price=68.0, beach_hours=38.0, sea_temp_c=13.5),
        ],
    )

    deals = db.get_grouped_deals(min_sea_temp_c=17.0, include_cold=False)
    assert len(deals) == 1
    assert deals[0].best.destination == "AGP"
    assert deals[0].best.total_price_gbp == 88.0
    assert len(deals[0].alternatives) == 1
    assert deals[0].previous_best_gbp == 110.0
    assert deals[0].price_delta_gbp == -22.0
    assert deals[0].is_all_time_low is True

    # Including cold puts NCE AFTER AGP
    all_deals = db.get_grouped_deals(min_sea_temp_c=17.0, include_cold=True)
    assert [d.best.destination for d in all_deals] == ["AGP", "NCE"]

    hist = db.get_price_history("AGP", date(2026, 11, 21))
    assert len(hist) == 2
    assert hist[0]["best_price_gbp"] == 110.0
    assert hist[1]["best_price_gbp"] == 88.0

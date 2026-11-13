"""Tests for core optimizer: time windows, timezone beach_hours, open-jaw, and 17C sea-temp gate."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from beach_flights.core.destinations import DESTINATIONS
from beach_flights.core.optimizer import (
    compute_beach_hours,
    pair_and_score_trips,
    sort_scored_trips,
)
from beach_flights.models import FlightLeg, RoundTripOffer, ScanConfig, SeaCondition

LONDON_TZ = ZoneInfo("Europe/London")
MADRID_TZ = ZoneInfo("Europe/Madrid")
CANARY_TZ = ZoneInfo("Atlantic/Canary")


def _leg(
    origin: str,
    dest: str,
    dep: datetime,
    arr: datetime,
    price: float,
    flight_no: str = "EZY101",
    airline: str = "easyJet",
    stops: int = 0,
) -> FlightLeg:
    return FlightLeg(
        origin=origin,
        destination=dest,
        airline=airline,
        flight_number=flight_no,
        departure_dt=dep,
        arrival_dt=arr,
        duration_minutes=int((arr - dep).total_seconds() // 60),
        stops=stops,
        price_gbp=price,
    )


def test_cross_timezone_beach_hours_computation() -> None:
    # London (GMT+0) 06:00 -> Malaga (CET+1) 09:50 (2h50m flight)
    # Return Malaga (CET+1) 21:30 next day -> exactly 35.67h on the ground!
    out_leg = _leg(
        "LGW",
        "AGP",
        datetime(2026, 11, 21, 6, 0, tzinfo=LONDON_TZ),
        datetime(2026, 11, 21, 9, 50, tzinfo=MADRID_TZ),
        40.0,
    )
    in_leg = _leg(
        "AGP",
        "LHR",
        datetime(2026, 11, 22, 21, 30, tzinfo=MADRID_TZ),
        datetime(2026, 11, 22, 23, 20, tzinfo=LONDON_TZ),
        45.0,
    )
    assert compute_beach_hours(out_leg, in_leg) == 35.67


def test_filters_useless_night_outbounds_and_morning_returns() -> None:
    cfg = ScanConfig(min_sea_temp_c=17.0, min_beach_hours=28.0)
    out_good = _leg(
        "LGW",
        "AGP",
        datetime(2026, 11, 21, 6, 30, tzinfo=LONDON_TZ),
        datetime(2026, 11, 21, 10, 15, tzinfo=MADRID_TZ),
        40.0,
        flight_no="EZY801",
    )
    out_useless_night = _leg(
        "LGW",
        "AGP",
        datetime(2026, 11, 21, 22, 50, tzinfo=LONDON_TZ),
        datetime(2026, 11, 22, 2, 30, tzinfo=MADRID_TZ),
        20.0,
        flight_no="EZY899",
    )
    in_good = _leg(
        "AGP",
        "LHR",
        datetime(2026, 11, 22, 20, 45, tzinfo=MADRID_TZ),
        datetime(2026, 11, 22, 22, 35, tzinfo=LONDON_TZ),
        42.0,
        flight_no="BA455",
        airline="British Airways",
    )
    in_useless_morning = _leg(
        "AGP",
        "LGW",
        datetime(2026, 11, 22, 8, 15, tzinfo=MADRID_TZ),
        datetime(2026, 11, 22, 10, 5, tzinfo=LONDON_TZ),
        19.0,
        flight_no="EZY802",
    )

    trips = pair_and_score_trips(
        weekend_date=date(2026, 11, 21),
        return_date=date(2026, 11, 22),
        dest_info=DESTINATIONS["AGP"],
        outbound_legs=[out_good, out_useless_night],
        inbound_legs=[in_good, in_useless_morning],
        round_trip_offers=None,
        sea_condition=SeaCondition(
            destination="AGP", target_date=date(2026, 11, 21), sea_temp_c=18.5, source="live"
        ),
        config=cfg,
    )
    assert len(trips) == 1
    assert trips[0].outbound.flight_number == "EZY801"
    assert trips[0].inbound.flight_number == "BA455"
    assert trips[0].is_open_jaw is True
    assert trips[0].total_price_gbp == 82.0


def test_round_trip_offer_overrides_more_expensive_one_way_pair() -> None:
    cfg = ScanConfig(allow_open_jaw=False, min_sea_temp_c=17.0)
    out_leg = _leg(
        "LHR",
        "TFS",
        datetime(2026, 11, 21, 7, 10, tzinfo=LONDON_TZ),
        datetime(2026, 11, 21, 11, 40, tzinfo=CANARY_TZ),
        110.0,
        flight_no="BA2700",
        airline="British Airways",
    )
    in_leg = _leg(
        "TFS",
        "LHR",
        datetime(2026, 11, 22, 19, 30, tzinfo=CANARY_TZ),
        datetime(2026, 11, 22, 23, 55, tzinfo=LONDON_TZ),
        115.0,
        flight_no="BA2701",
        airline="British Airways",
    )
    rt = RoundTripOffer(outbound=out_leg, inbound=in_leg, total_price_gbp=165.0)

    trips = pair_and_score_trips(
        weekend_date=date(2026, 11, 21),
        return_date=date(2026, 11, 22),
        dest_info=DESTINATIONS["TFS"],
        outbound_legs=[out_leg],
        inbound_legs=[in_leg],
        round_trip_offers=[rt],
        sea_condition=SeaCondition(
            destination="TFS", target_date=date(2026, 11, 21), sea_temp_c=21.2, source="forecast"
        ),
        config=cfg,
    )
    assert len(trips) == 1
    assert trips[0].pricing_mode == "round_trip"
    assert trips[0].total_price_gbp == 165.0


def test_cold_13c_70gbp_38h_never_beats_warm_18c_80gbp_36h() -> None:
    # Exact user scenario:
    # Cold beach: 38h, £70, 13°C sea temp (< 17°C Brighton baseline)
    # Warm beach: 36h, £80, 18°C sea temp (>= 17°C Brighton baseline)
    cfg_default = ScanConfig(min_sea_temp_c=17.0, include_cold=False)
    cfg_with_cold = ScanConfig(min_sea_temp_c=17.0, include_cold=True)

    cold_out = _leg(
        "LGW",
        "NCE",
        datetime(2026, 11, 21, 6, 0, tzinfo=LONDON_TZ),
        datetime(2026, 11, 21, 9, 0, tzinfo=MADRID_TZ),
        35.0,
        flight_no="EZY1",
    )
    cold_in = _leg(
        "NCE",
        "LGW",
        datetime(2026, 11, 22, 23, 0, tzinfo=MADRID_TZ),
        datetime(2026, 11, 23, 0, 10, tzinfo=LONDON_TZ),
        35.0,
        flight_no="EZY2",
    )
    warm_out = _leg(
        "LGW",
        "AGP",
        datetime(2026, 11, 21, 6, 30, tzinfo=LONDON_TZ),
        datetime(2026, 11, 21, 10, 0, tzinfo=MADRID_TZ),
        40.0,
        flight_no="EZY3",
    )
    warm_in = _leg(
        "AGP",
        "LGW",
        datetime(2026, 11, 22, 22, 0, tzinfo=MADRID_TZ),
        datetime(2026, 11, 22, 23, 50, tzinfo=LONDON_TZ),
        40.0,
        flight_no="EZY4",
    )

    cold_sea = SeaCondition(
        destination="NCE", target_date=date(2026, 11, 21), sea_temp_c=13.0, source="live"
    )
    warm_sea = SeaCondition(
        destination="AGP", target_date=date(2026, 11, 21), sea_temp_c=18.0, source="live"
    )

    # Default mode excludes < 17°C completely
    assert (
        pair_and_score_trips(
            weekend_date=date(2026, 11, 21),
            return_date=date(2026, 11, 22),
            dest_info=DESTINATIONS["NCE"],
            outbound_legs=[cold_out],
            inbound_legs=[cold_in],
            round_trip_offers=None,
            sea_condition=cold_sea,
            config=cfg_default,
        )
        == []
    )

    # Even when include_cold=True, swimmable 18°C (£80/36h) MUST rank above 13°C (£70/38h)
    cold_trips = pair_and_score_trips(
        weekend_date=date(2026, 11, 21),
        return_date=date(2026, 11, 22),
        dest_info=DESTINATIONS["NCE"],
        outbound_legs=[cold_out],
        inbound_legs=[cold_in],
        round_trip_offers=None,
        sea_condition=cold_sea,
        config=cfg_with_cold,
    )
    warm_trips = pair_and_score_trips(
        weekend_date=date(2026, 11, 21),
        return_date=date(2026, 11, 22),
        dest_info=DESTINATIONS["AGP"],
        outbound_legs=[warm_out],
        inbound_legs=[warm_in],
        round_trip_offers=None,
        sea_condition=warm_sea,
        config=cfg_with_cold,
    )

    combined = sort_scored_trips(cold_trips + warm_trips, sort_by="value")
    assert len(combined) == 2
    assert combined[0].destination == "AGP"
    assert combined[0].is_swimmable is True
    assert combined[1].destination == "NCE"
    assert combined[1].is_swimmable is False

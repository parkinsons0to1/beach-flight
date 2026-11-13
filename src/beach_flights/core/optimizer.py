"""Core pairing, timezone-exact beach hours, sea-temp gating, and ranking logic."""

from __future__ import annotations

from datetime import UTC, date, time

from beach_flights.models import (
    DestinationInfo,
    FlightLeg,
    RoundTripOffer,
    ScanConfig,
    ScoredTrip,
    SeaCondition,
)


def _in_time_window(t: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= t <= end
    # Wrap-around midnight window if ever configured (e.g. 22:00 - 02:00)
    return t >= start or t <= end


def compute_beach_hours(outbound_arrival: FlightLeg, inbound_departure: FlightLeg) -> float:
    """Compute exact ground hours at destination in UTC to handle cross-timezone & DST shifts."""
    arr_utc = outbound_arrival.arrival_dt.astimezone(UTC)
    dep_utc = inbound_departure.departure_dt.astimezone(UTC)
    return round((dep_utc - arr_utc).total_seconds() / 3600.0, 2)


def is_valid_outbound(leg: FlightLeg, config: ScanConfig) -> bool:
    if leg.stops != 0:
        return False
    dep_t = leg.departure_dt.time()
    if not _in_time_window(dep_t, config.outbound_dep_start, config.outbound_dep_end):
        return False
    latest = config.outbound_arr_latest
    return not (latest is not None and leg.arrival_dt.time() > latest)


def is_valid_inbound(leg: FlightLeg, config: ScanConfig) -> bool:
    if leg.stops != 0:
        return False
    dep_t = leg.departure_dt.time()
    return _in_time_window(dep_t, config.inbound_dep_start, config.inbound_dep_end)


def sort_scored_trips(
    trips: list[ScoredTrip],
    sort_by: str = "value",
) -> list[ScoredTrip]:
    """Sort trips, always placing swimmable (>= min_sea_temp_c) deals before cold ones."""
    if sort_by == "price":
        return sorted(
            trips,
            key=lambda t: (
                not t.is_swimmable,
                t.total_price_gbp,
                t.gbp_per_beach_hour,
                -t.beach_hours,
            ),
        )
    if sort_by == "hours":
        return sorted(
            trips,
            key=lambda t: (
                not t.is_swimmable,
                -t.beach_hours,
                t.total_price_gbp,
                t.gbp_per_beach_hour,
            ),
        )
    if sort_by == "temp":
        return sorted(
            trips,
            key=lambda t: (
                not t.is_swimmable,
                -(t.sea_temp_c if t.sea_temp_c is not None else -999.0),
                t.gbp_per_beach_hour,
                t.total_price_gbp,
            ),
        )
    # Default: "value" (lowest £ per beach hour)
    return sorted(
        trips,
        key=lambda t: (
            not t.is_swimmable,
            t.gbp_per_beach_hour,
            t.total_price_gbp,
            -t.beach_hours,
        ),
    )


def pair_and_score_trips(
    *,
    weekend_date: date,
    return_date: date,
    dest_info: DestinationInfo,
    outbound_legs: list[FlightLeg],
    inbound_legs: list[FlightLeg],
    round_trip_offers: list[RoundTripOffer] | None,
    sea_condition: SeaCondition | None,
    config: ScanConfig,
) -> list[ScoredTrip]:
    """Pair valid outbound + inbound legs (plus optional RT offers) and score each 1-night trip."""
    valid_out = [
        leg
        for leg in outbound_legs
        if leg.origin in config.origins
        and leg.destination == dest_info.iata
        and leg.departure_dt.date() == weekend_date
        and is_valid_outbound(leg, config)
    ]
    valid_in = [
        leg
        for leg in inbound_legs
        if leg.origin == dest_info.iata
        and leg.destination in config.origins
        and leg.departure_dt.date() == return_date
        and is_valid_inbound(leg, config)
    ]

    sea_temp_c = sea_condition.sea_temp_c if sea_condition else None
    sea_temp_source = sea_condition.source if sea_condition else "unavailable"
    is_swimmable = True if sea_temp_c is None else (sea_temp_c >= config.min_sea_temp_c)

    if not config.include_cold and not is_swimmable:
        return []

    best_by_pair: dict[tuple[str, str, str, str], ScoredTrip] = {}

    def _consider(
        out_leg: FlightLeg,
        in_leg: FlightLeg,
        total_price: float,
        pricing_mode: str,
        booking_url: str | None,
    ) -> None:
        if not config.allow_open_jaw and out_leg.origin != in_leg.destination:
            return
        if total_price <= 0 or total_price > config.max_price_gbp:
            return
        beach_hours = compute_beach_hours(out_leg, in_leg)
        if beach_hours < config.min_beach_hours:
            return

        gbp_per_hr = round(total_price / beach_hours, 2)
        pair_key = (
            out_leg.flight_number,
            out_leg.departure_dt.isoformat(),
            in_leg.flight_number,
            in_leg.departure_dt.isoformat(),
        )
        candidate = ScoredTrip(
            weekend_date=weekend_date,
            return_date=return_date,
            destination=dest_info.iata,
            destination_name=dest_info.name,
            country=dest_info.country,
            outbound=out_leg,
            inbound=in_leg,
            is_open_jaw=(out_leg.origin != in_leg.destination),
            pricing_mode=pricing_mode,  # type: ignore[arg-type]
            total_price_gbp=round(total_price, 2),
            beach_hours=beach_hours,
            gbp_per_beach_hour=gbp_per_hr,
            sea_temp_c=sea_temp_c,
            sea_temp_source=sea_temp_source,  # type: ignore[arg-type]
            is_swimmable=is_swimmable,
            booking_url=booking_url or out_leg.booking_url,
        )

        existing = best_by_pair.get(pair_key)
        if existing is None or candidate.total_price_gbp < existing.total_price_gbp:
            best_by_pair[pair_key] = candidate

    # 1. One-way pairs (supports LGW/LHR open-jaw & cross-carrier mixing)
    for out_leg in valid_out:
        for in_leg in valid_in:
            combined_price = round(out_leg.price_gbp + in_leg.price_gbp, 2)
            _consider(
                out_leg=out_leg,
                in_leg=in_leg,
                total_price=combined_price,
                pricing_mode="one_way_pair",
                booking_url=out_leg.booking_url,
            )

    # 2. Bundled same-airport round-trip offers (can undercut legacy one-way fares)
    for rt in round_trip_offers or []:
        if (
            rt.outbound.origin in config.origins
            and rt.outbound.destination == dest_info.iata
            and rt.inbound.origin == dest_info.iata
            and rt.inbound.destination in config.origins
            and rt.outbound.departure_dt.date() == weekend_date
            and rt.inbound.departure_dt.date() == return_date
            and is_valid_outbound(rt.outbound, config)
            and is_valid_inbound(rt.inbound, config)
        ):
            _consider(
                out_leg=rt.outbound,
                in_leg=rt.inbound,
                total_price=rt.total_price_gbp,
                pricing_mode="round_trip",
                booking_url=rt.booking_url,
            )

    return sort_scored_trips(list(best_by_pair.values()), sort_by=config.sort_by)

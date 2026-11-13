"""Normalized domain models for beach-flights."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field


class DestinationInfo(BaseModel):
    """Metadata for a beach destination airport."""

    iata: str
    name: str
    country: str
    timezone: str
    sea_lat: float
    sea_lon: float
    presets: list[str] = Field(default_factory=list)


class SeaCondition(BaseModel):
    """Live or forecasted sea surface temperature for a destination."""

    destination: str
    target_date: date
    sea_temp_c: float | None = None
    source: Literal["forecast", "live", "unavailable"] = "unavailable"


class FlightLeg(BaseModel):
    """A single directional flight option (outbound or inbound)."""

    origin: str
    destination: str
    airline: str
    flight_number: str
    departure_dt: datetime
    arrival_dt: datetime
    duration_minutes: int
    stops: int
    price_gbp: float
    booking_url: str | None = None


class RoundTripOffer(BaseModel):
    """A bundled round-trip flight offer returned by a provider."""

    outbound: FlightLeg
    inbound: FlightLeg
    total_price_gbp: float
    booking_url: str | None = None


class ScoredTrip(BaseModel):
    """A fully scored 1-night weekend beach itinerary."""

    weekend_date: date
    return_date: date
    destination: str
    destination_name: str
    country: str
    outbound: FlightLeg
    inbound: FlightLeg
    is_open_jaw: bool
    pricing_mode: Literal["one_way_pair", "round_trip"]
    total_price_gbp: float
    beach_hours: float
    gbp_per_beach_hour: float
    sea_temp_c: float | None = None
    sea_temp_source: Literal["forecast", "live", "unavailable"] = "unavailable"
    is_swimmable: bool = True
    booking_url: str | None = None


class GroupedDeal(BaseModel):
    """Best deal for a (destination, weekend_date) pair plus alternatives and history."""

    best: ScoredTrip
    alternatives: list[ScoredTrip] = Field(default_factory=list)
    previous_best_gbp: float | None = None
    price_delta_gbp: float | None = None
    all_time_low_gbp: float | None = None
    is_all_time_low: bool = False


class ScanConfig(BaseModel):
    """Configuration controlling a single scan sweep."""

    origins: list[str] = Field(default_factory=lambda: ["LGW", "LHR"])
    destinations: list[str] = Field(default_factory=list)
    allow_open_jaw: bool = True
    weekend_days: list[Literal["sat-sun", "fri-sat", "sun-mon"]] = Field(
        default_factory=lambda: ["sat-sun"]
    )
    outbound_dep_start: time = Field(default_factory=lambda: time(5, 0))
    outbound_dep_end: time = Field(default_factory=lambda: time(10, 30))
    outbound_arr_latest: time | None = Field(default_factory=lambda: time(14, 0))
    inbound_dep_start: time = Field(default_factory=lambda: time(18, 0))
    inbound_dep_end: time = Field(default_factory=lambda: time(23, 30))
    min_beach_hours: float = 28.0
    min_sea_temp_c: float = 17.0
    max_price_gbp: float = 250.0
    include_cold: bool = False
    skip_cold: bool = False
    check_round_trips: bool = True
    provider: Literal["fli", "serpapi"] = "fli"
    sort_by: Literal["value", "price", "hours", "temp"] = "value"


class ScanSummary(BaseModel):
    """Summary returned after running a scan."""

    scan_id: int
    created_at: datetime
    provider: str
    date_from: date
    date_to: date
    total_offers_saved: int
    swimmable_deals_count: int
    cold_deals_count: int
    grouped_deals: list[GroupedDeal] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

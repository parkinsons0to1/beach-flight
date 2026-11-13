"""End-to-end scan orchestrator combining marine SST, flight search, optimization, and SQLite."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime

from beach_flights.alerts import send_deal_alerts
from beach_flights.core.dates import default_date_window, generate_weekend_pairs
from beach_flights.core.destinations import resolve_destinations
from beach_flights.core.optimizer import pair_and_score_trips
from beach_flights.models import (
    DestinationInfo,
    RoundTripOffer,
    ScanConfig,
    ScanSummary,
    ScoredTrip,
    SeaCondition,
)
from beach_flights.providers.base import FlightProvider
from beach_flights.providers.fli_provider import FliProvider
from beach_flights.providers.marine_temp import MarineTempProvider
from beach_flights.providers.serpapi_provider import SerpApiProvider
from beach_flights.storage.db import FlightDatabase


def build_provider(provider_name: str) -> FlightProvider:
    if provider_name == "serpapi":
        return SerpApiProvider()
    return FliProvider()


class BeachScanner:
    """Runs weekend flight + sea-temperature scans and persists results to SQLite."""

    def __init__(
        self,
        db: FlightDatabase,
        provider: FlightProvider | None = None,
        marine_provider: MarineTempProvider | None = None,
        max_workers: int = 2,
    ) -> None:
        self.db = db
        self.provider = provider
        self.marine_provider = marine_provider or MarineTempProvider()
        self.max_workers = max(1, max_workers)

    def run_scan(
        self,
        config: ScanConfig,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        weeks: int = 4,
        preset: str = "winter-sun",
        notify: bool = False,
        alert_under_gbp: float | None = None,
        progress_cb: Callable[[str], None] | None = None,
    ) -> ScanSummary:
        if date_from is None or date_to is None:
            default_from, default_to = default_date_window(weeks=weeks)
            date_from = date_from or default_from
            date_to = date_to or default_to

        dest_infos = resolve_destinations(config.destinations or None, preset=preset)
        weekend_pairs = generate_weekend_pairs(
            date_from=date_from,
            date_to=date_to,
            patterns=list(config.weekend_days),
        )
        if not weekend_pairs:
            raise ValueError(
                f"No matching 1-night weekend pairs found between {date_from} and {date_to}."
            )

        active_provider = self.provider or build_provider(config.provider)
        scan_id = self.db.create_scan(
            provider=active_provider.name,
            date_from=date_from,
            date_to=date_to,
            params=config.model_dump(mode="json"),
            status="running",
        )

        errors: list[str] = []
        try:
            if progress_cb:
                progress_cb(
                    f"Fetching live/forecast sea temperatures for {len(dest_infos)} beaches..."
                )
            outbound_dates = sorted({out_d for out_d, _ in weekend_pairs})
            sea_map = self.marine_provider.fetch_sea_conditions(dest_infos, outbound_dates)

            tasks: list[tuple[DestinationInfo, date, date, SeaCondition | None]] = []
            for dest in dest_infos:
                for out_d, ret_d in weekend_pairs:
                    sea_cond = sea_map.get((dest.iata, out_d))
                    if (
                        not config.include_cold
                        and sea_cond is not None
                        and sea_cond.sea_temp_c is not None
                        and sea_cond.sea_temp_c < config.min_sea_temp_c
                    ):
                        # Skip flight queries for destinations already colder than Brighton (17C)
                        continue
                    tasks.append((dest, out_d, ret_d, sea_cond))

            all_scored: list[ScoredTrip] = []
            if progress_cb:
                origins_str = ",".join(config.origins)
                progress_cb(
                    f"Scanning {len(tasks)} (destination, weekend) pairs across {origins_str}..."
                )

            def _scan_one(
                dest: DestinationInfo,
                out_d: date,
                ret_d: date,
                sea_cond: SeaCondition | None,
            ) -> list[ScoredTrip]:
                out_legs = active_provider.search_one_way(
                    config.origins,
                    [dest.iata],
                    out_d,
                    sort_mode="departure_time",
                )
                in_legs = active_provider.search_one_way(
                    [dest.iata],
                    config.origins,
                    ret_d,
                    sort_mode="cheapest",
                )

                rt_offers: list[RoundTripOffer] = []
                if config.check_round_trips and "LHR" in config.origins:
                    # Legacy carriers at LHR (e.g. BA) sometimes price RT below two one-ways.
                    has_lhr_candidate = any(leg.origin == "LHR" for leg in out_legs) and any(
                        leg.destination == "LHR" for leg in in_legs
                    )
                    if has_lhr_candidate:
                        try:
                            rt_offers = active_provider.search_round_trip(
                                "LHR", dest.iata, out_d, ret_d, top_n=5
                            )
                        except Exception:
                            rt_offers = []

                return pair_and_score_trips(
                    weekend_date=out_d,
                    return_date=ret_d,
                    dest_info=dest,
                    outbound_legs=out_legs,
                    inbound_legs=in_legs,
                    round_trip_offers=rt_offers,
                    sea_condition=sea_cond,
                    config=config,
                )

            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                future_map = {
                    pool.submit(_scan_one, dest, out_d, ret_d, sea_cond): (dest.iata, out_d)
                    for dest, out_d, ret_d, sea_cond in tasks
                }
                for fut in as_completed(future_map):
                    iata, out_d = future_map[fut]
                    try:
                        scored = fut.result()
                        all_scored.extend(scored)
                        if progress_cb:
                            progress_cb(
                                f"  {iata} {out_d.isoformat()}: {len(scored)} qualifying trips"
                            )
                    except Exception as exc:
                        errors.append(f"{iata} {out_d.isoformat()}: {exc}")

            saved_count = self.db.save_offers(scan_id, all_scored)
            self.db.update_scan_status(scan_id, "completed")
        except Exception:
            self.db.update_scan_status(scan_id, "failed")
            raise

        grouped = self.db.get_grouped_deals(
            scan_id=scan_id,
            min_sea_temp_c=config.min_sea_temp_c,
            include_cold=config.include_cold,
            min_beach_hours=config.min_beach_hours,
            max_price_gbp=config.max_price_gbp,
            allow_open_jaw=config.allow_open_jaw,
            sort_by=config.sort_by,
        )

        if notify and grouped:
            send_deal_alerts(grouped, alert_under_gbp=alert_under_gbp)

        swimmable_count = sum(1 for d in grouped if d.best.is_swimmable)
        cold_count = len(grouped) - swimmable_count
        return ScanSummary(
            scan_id=scan_id,
            created_at=datetime.now(UTC),
            provider=active_provider.name,
            date_from=date_from,
            date_to=date_to,
            total_offers_saved=saved_count,
            swimmable_deals_count=swimmable_count,
            cold_deals_count=cold_count,
            grouped_deals=grouped,
            errors=errors,
        )

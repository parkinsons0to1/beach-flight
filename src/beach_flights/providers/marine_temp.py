"""Open-Meteo Marine API client for live & forecasted sea surface temperatures (SST)."""

from __future__ import annotations

from datetime import date, datetime

import httpx

from beach_flights.models import DestinationInfo, SeaCondition
from beach_flights.providers.http_utils import create_http_client

OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"


class MarineTempProvider:
    """Fetches sea surface temperature (°C) using Open-Meteo's free Marine API."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or create_http_client(timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_sea_conditions(
        self,
        destinations: list[DestinationInfo],
        target_dates: list[date],
    ) -> dict[tuple[str, date], SeaCondition]:
        """Batch-fetch sea surface temperatures for all (destination, target_date) pairs.

        Uses forecasted midday SST when `target_date` falls within Open-Meteo's marine forecast
        window (~10 days), and falls back to live current SST for further-out dates.
        """
        if not destinations or not target_dates:
            return {}

        lats = ",".join(f"{d.sea_lat:.4f}" for d in destinations)
        lons = ",".join(f"{d.sea_lon:.4f}" for d in destinations)

        params = {
            "latitude": lats,
            "longitude": lons,
            "current": "sea_surface_temperature",
            "hourly": "sea_surface_temperature",
            "forecast_days": 10,
            "timezone": "UTC",
        }

        try:
            resp = self._client.get(OPEN_METEO_MARINE_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            return {
                (d.iata, dt): SeaCondition(
                    destination=d.iata, target_date=dt, sea_temp_c=None, source="unavailable"
                )
                for d in destinations
                for dt in target_dates
            }

        # Open-Meteo returns a dict for 1 coordinate, or a list of dicts for multiple coordinates.
        entries = payload if isinstance(payload, list) else [payload]

        results: dict[tuple[str, date], SeaCondition] = {}
        for dest, entry in zip(destinations, entries, strict=False):
            live_temp = _extract_current_temp(entry)
            hourly_by_date = _extract_daily_midday_forecast(entry)

            for dt in target_dates:
                if dt in hourly_by_date and hourly_by_date[dt] is not None:
                    results[(dest.iata, dt)] = SeaCondition(
                        destination=dest.iata,
                        target_date=dt,
                        sea_temp_c=round(hourly_by_date[dt], 1),
                        source="forecast",
                    )
                elif live_temp is not None:
                    results[(dest.iata, dt)] = SeaCondition(
                        destination=dest.iata,
                        target_date=dt,
                        sea_temp_c=round(live_temp, 1),
                        source="live",
                    )
                else:
                    results[(dest.iata, dt)] = SeaCondition(
                        destination=dest.iata,
                        target_date=dt,
                        sea_temp_c=None,
                        source="unavailable",
                    )
        return results


def _extract_current_temp(entry: dict) -> float | None:
    current = entry.get("current") or {}
    val = current.get("sea_surface_temperature")
    return float(val) if val is not None else None


def _extract_daily_midday_forecast(entry: dict) -> dict[date, float]:
    hourly = entry.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("sea_surface_temperature") or []

    grouped: dict[date, list[tuple[int, float]]] = {}
    for ts_str, temp in zip(times, temps, strict=False):
        if temp is None:
            continue
        try:
            dt = datetime.fromisoformat(ts_str)
        except ValueError:
            continue
        grouped.setdefault(dt.date(), []).append((dt.hour, float(temp)))

    out: dict[date, float] = {}
    for day, samples in grouped.items():
        # Prefer daytime hours (10:00-16:00 UTC) if present, else average all hours.
        daytime = [t for hr, t in samples if 10 <= hr <= 16]
        chosen = daytime if daytime else [t for _, t in samples]
        if chosen:
            out[day] = sum(chosen) / len(chosen)
    return out

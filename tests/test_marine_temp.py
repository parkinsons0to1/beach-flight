"""Tests for Open-Meteo Marine sea temperature provider."""

from __future__ import annotations

from datetime import date

import httpx

from beach_flights.core.destinations import DESTINATIONS
from beach_flights.providers.marine_temp import MarineTempProvider


def test_marine_temp_batches_destinations_with_forecast_and_live_fallback() -> None:
    sample_payload = [
        {
            "current": {"sea_surface_temperature": 18.4},
            "hourly": {
                "time": ["2026-11-14T12:00", "2026-11-14T15:00"],
                "sea_surface_temperature": [18.6, 18.8],
            },
        },
        {
            "current": {"sea_surface_temperature": 21.9},
            "hourly": {
                "time": ["2026-11-14T12:00"],
                "sea_surface_temperature": [22.1],
            },
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert "marine-api.open-meteo.com" in str(request.url)
        return httpx.Response(200, json=sample_payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = MarineTempProvider(client=client)

    near_date = date(2026, 11, 14)
    far_date = date(2026, 12, 19)
    res = provider.fetch_sea_conditions(
        [DESTINATIONS["AGP"], DESTINATIONS["TFS"]],
        [near_date, far_date],
    )

    assert res[("AGP", near_date)].sea_temp_c == 18.7
    assert res[("AGP", near_date)].source == "forecast"
    assert res[("AGP", far_date)].sea_temp_c == 18.4
    assert res[("AGP", far_date)].source == "live"
    assert res[("TFS", near_date)].sea_temp_c == 22.1
    assert res[("TFS", far_date)].sea_temp_c == 21.9


def test_marine_temp_handles_network_error_gracefully() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = MarineTempProvider(client=client)
    dt = date(2026, 11, 14)
    res = provider.fetch_sea_conditions([DESTINATIONS["AGP"]], [dt])
    assert res[("AGP", dt)].sea_temp_c is None
    assert res[("AGP", dt)].source == "unavailable"

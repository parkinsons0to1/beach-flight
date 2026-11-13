"""FastAPI backend for the local beach-flights dashboard."""

from __future__ import annotations

import threading
from datetime import date, time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from beach_flights.core.destinations import DESTINATIONS
from beach_flights.core.scanner import BeachScanner
from beach_flights.models import ScanConfig
from beach_flights.storage.db import FlightDatabase

STATIC_DIR = Path(__file__).parent / "static"


class TriggerScanRequest(BaseModel):
    preset: str = "winter-sun"
    destinations: list[str] = Field(default_factory=list)
    weeks: int = Field(default=3, ge=1, le=12)
    weekend_days: list[Literal["sat-sun", "fri-sat", "sun-mon"]] = Field(
        default_factory=lambda: ["sat-sun"]
    )
    allow_open_jaw: bool = True
    min_beach_hours: float = 28.0
    min_sea_temp_c: float = 17.0
    include_cold: bool = False
    max_price_gbp: float = 250.0
    outbound_dep_start: str = "05:00"
    outbound_dep_end: str = "10:30"
    outbound_arr_latest: str = "14:00"
    inbound_dep_start: str = "18:00"
    inbound_dep_end: str = "23:30"
    check_round_trips: bool = True


def _parse_time(hhmm: str) -> time:
    h, m = hhmm.strip().split(":")
    return time(int(h), int(m))


def create_app(
    db_path: str | Path = "data/flights.db",
    scanner_factory=None,
) -> FastAPI:
    app = FastAPI(title="Beach Flights Tracker", version="0.1.0")
    db = FlightDatabase(db_path)

    scan_state: dict[str, object] = {
        "running": False,
        "last_scan_id": None,
        "last_error": None,
        "last_message": None,
    }
    scan_lock = threading.Lock()

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        html_path = STATIC_DIR / "index.html"
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/api/destinations")
    def api_destinations() -> list[dict]:
        return [d.model_dump() for d in DESTINATIONS.values()]

    @app.get("/api/scans")
    def api_scans(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
        return db.list_scans(limit=limit)

    @app.get("/api/deals")
    def api_deals(
        scan_id: int | None = None,
        min_sea_temp_c: float = 17.0,
        include_cold: bool = False,
        min_beach_hours: float = 28.0,
        max_price_gbp: float | None = None,
        allow_open_jaw: bool = True,
        origin: str | None = None,
        destination: str | None = None,
        weekend_date: str | None = None,
        sort_by: Literal["value", "price", "hours", "temp"] = "value",
    ) -> dict:
        wk = date.fromisoformat(weekend_date) if weekend_date else None
        deals = db.get_grouped_deals(
            scan_id=scan_id,
            min_sea_temp_c=min_sea_temp_c,
            include_cold=include_cold,
            min_beach_hours=min_beach_hours,
            max_price_gbp=max_price_gbp,
            allow_open_jaw=allow_open_jaw,
            origin=origin,
            destination=destination,
            weekend_date=wk,
            sort_by=sort_by,
        )
        return {
            "scan_id": scan_id or db.get_latest_scan_id(),
            "count": len(deals),
            "deals": [d.model_dump(mode="json") for d in deals],
        }

    @app.get("/api/history")
    def api_history(destination: str, weekend_date: str) -> dict:
        try:
            wk = date.fromisoformat(weekend_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid weekend_date") from exc
        rows = db.get_price_history(destination, wk)
        return {"destination": destination.upper(), "weekend_date": weekend_date, "history": rows}

    @app.get("/api/scan/status")
    def api_scan_status() -> dict:
        with scan_lock:
            return dict(scan_state)

    @app.post("/api/scan")
    def api_trigger_scan(req: TriggerScanRequest) -> dict:
        with scan_lock:
            if scan_state["running"]:
                raise HTTPException(status_code=409, detail="A scan is already running.")
            scan_state["running"] = True
            scan_state["last_error"] = None
            scan_state["last_message"] = "Starting scan..."

        def _worker() -> None:
            try:
                cfg = ScanConfig(
                    destinations=req.destinations,
                    allow_open_jaw=req.allow_open_jaw,
                    weekend_days=req.weekend_days,
                    outbound_dep_start=_parse_time(req.outbound_dep_start),
                    outbound_dep_end=_parse_time(req.outbound_dep_end),
                    outbound_arr_latest=_parse_time(req.outbound_arr_latest),
                    inbound_dep_start=_parse_time(req.inbound_dep_start),
                    inbound_dep_end=_parse_time(req.inbound_dep_end),
                    min_beach_hours=req.min_beach_hours,
                    min_sea_temp_c=req.min_sea_temp_c,
                    include_cold=req.include_cold,
                    max_price_gbp=req.max_price_gbp,
                    check_round_trips=req.check_round_trips,
                )
                scanner = scanner_factory(db) if scanner_factory else BeachScanner(db=db)
                summary = scanner.run_scan(
                    cfg,
                    weeks=req.weeks,
                    preset=req.preset,
                    progress_cb=lambda msg: scan_state.__setitem__("last_message", msg),
                )
                with scan_lock:
                    scan_state["last_scan_id"] = summary.scan_id
                    scan_state["last_message"] = (
                        f"Scan #{summary.scan_id} complete: "
                        f"{summary.swimmable_deals_count} swimmable deals."
                    )
            except Exception as exc:
                with scan_lock:
                    scan_state["last_error"] = str(exc)
                    scan_state["last_message"] = f"Failed: {exc}"
            finally:
                with scan_lock:
                    scan_state["running"] = False

        threading.Thread(target=_worker, daemon=True).start()
        return {"started": True}

    return app

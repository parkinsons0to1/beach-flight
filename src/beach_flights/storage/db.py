"""SQLite storage for scans, flight offers, grouped deals, and price history."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from beach_flights.core.optimizer import sort_scored_trips
from beach_flights.models import FlightLeg, GroupedDeal, ScoredTrip

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    provider TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    params_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed'
);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    weekend_date TEXT NOT NULL,
    return_date TEXT NOT NULL,
    destination TEXT NOT NULL,
    destination_name TEXT NOT NULL,
    country TEXT NOT NULL,
    out_origin TEXT NOT NULL,
    in_dest TEXT NOT NULL,
    out_airline TEXT NOT NULL,
    in_airline TEXT NOT NULL,
    out_flight TEXT NOT NULL,
    in_flight TEXT NOT NULL,
    out_dep TEXT NOT NULL,
    out_arr TEXT NOT NULL,
    in_dep TEXT NOT NULL,
    in_arr TEXT NOT NULL,
    out_duration_min INTEGER NOT NULL,
    in_duration_min INTEGER NOT NULL,
    out_price_gbp REAL NOT NULL,
    in_price_gbp REAL NOT NULL,
    is_open_jaw INTEGER NOT NULL,
    pricing_mode TEXT NOT NULL,
    total_price_gbp REAL NOT NULL,
    beach_hours REAL NOT NULL,
    gbp_per_beach_hour REAL NOT NULL,
    sea_temp_c REAL,
    sea_temp_source TEXT NOT NULL DEFAULT 'unavailable',
    booking_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_offers_scan ON offers(scan_id);
CREATE INDEX IF NOT EXISTS idx_offers_dest_weekend ON offers(destination, weekend_date);
"""


class FlightDatabase:
    """Thin SQLite wrapper managing flight scans and historical price tracking."""

    def __init__(self, db_path: str | Path = "data/flights.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def create_scan(
        self,
        *,
        provider: str,
        date_from: date,
        date_to: date,
        params: dict,
        status: str = "running",
    ) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO scans (created_at, provider, date_from, date_to, params_json, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    provider,
                    date_from.isoformat(),
                    date_to.isoformat(),
                    json.dumps(params),
                    status,
                ),
            )
            return int(cur.lastrowid)

    def update_scan_status(self, scan_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE scans SET status = ? WHERE id = ?", (status, scan_id))

    def save_offers(self, scan_id: int, trips: list[ScoredTrip]) -> int:
        if not trips:
            return 0
        rows = [
            (
                scan_id,
                t.weekend_date.isoformat(),
                t.return_date.isoformat(),
                t.destination,
                t.destination_name,
                t.country,
                t.outbound.origin,
                t.inbound.destination,
                t.outbound.airline,
                t.inbound.airline,
                t.outbound.flight_number,
                t.inbound.flight_number,
                t.outbound.departure_dt.isoformat(),
                t.outbound.arrival_dt.isoformat(),
                t.inbound.departure_dt.isoformat(),
                t.inbound.arrival_dt.isoformat(),
                t.outbound.duration_minutes,
                t.inbound.duration_minutes,
                t.outbound.price_gbp,
                t.inbound.price_gbp,
                1 if t.is_open_jaw else 0,
                t.pricing_mode,
                t.total_price_gbp,
                t.beach_hours,
                t.gbp_per_beach_hour,
                t.sea_temp_c,
                t.sea_temp_source,
                t.booking_url,
            )
            for t in trips
        ]
        placeholders = ", ".join(["?"] * 28)
        with self._connect() as conn:
            conn.executemany(
                f"""
                INSERT INTO offers (
                    scan_id, weekend_date, return_date, destination, destination_name, country,
                    out_origin, in_dest, out_airline, in_airline, out_flight, in_flight,
                    out_dep, out_arr, in_dep, in_arr, out_duration_min, in_duration_min,
                    out_price_gbp, in_price_gbp, is_open_jaw, pricing_mode, total_price_gbp,
                    beach_hours, gbp_per_beach_hour, sea_temp_c, sea_temp_source, booking_url
                ) VALUES ({placeholders})
                """,
                rows,
            )
        return len(rows)

    def get_latest_scan_id(self) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM scans WHERE status = 'completed' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return int(row["id"]) if row else None

    def list_scans(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.created_at, s.provider, s.date_from, s.date_to, s.status,
                       COUNT(o.id) AS offer_count
                FROM scans s
                LEFT JOIN offers o ON o.scan_id = s.id
                GROUP BY s.id
                ORDER BY s.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_grouped_deals(
        self,
        *,
        scan_id: int | None = None,
        min_sea_temp_c: float = 17.0,
        include_cold: bool = False,
        min_beach_hours: float = 0.0,
        max_price_gbp: float | None = None,
        allow_open_jaw: bool = True,
        origin: str | None = None,
        destination: str | None = None,
        weekend_date: date | None = None,
        sort_by: str = "value",
    ) -> list[GroupedDeal]:
        """Return grouped deals (#1 best + alternatives) for a scan with price deltas."""
        target_scan_id = scan_id or self.get_latest_scan_id()
        if target_scan_id is None:
            return []

        clauses = ["scan_id = ?", "beach_hours >= ?"]
        params: list[object] = [target_scan_id, min_beach_hours]

        if max_price_gbp is not None:
            clauses.append("total_price_gbp <= ?")
            params.append(max_price_gbp)
        if not allow_open_jaw:
            clauses.append("is_open_jaw = 0")
        if origin:
            ap = origin.strip().upper()
            clauses.append("(out_origin = ? OR in_dest = ?)")
            params.extend([ap, ap])
        if destination:
            clauses.append("destination = ?")
            params.append(destination.strip().upper())
        if weekend_date is not None:
            clauses.append("weekend_date = ?")
            params.append(weekend_date.isoformat())

        where_sql = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM offers WHERE {where_sql}",
                params,
            ).fetchall()

            if not rows:
                return []

            trips: list[ScoredTrip] = []
            for r in rows:
                trip = _row_to_scored_trip(r, min_sea_temp_c=min_sea_temp_c)
                if not include_cold and not trip.is_swimmable:
                    continue
                trips.append(trip)

            if not trips:
                return []

            grouped_map: dict[tuple[str, date], list[ScoredTrip]] = defaultdict(list)
            for t in trips:
                grouped_map[(t.destination, t.weekend_date)].append(t)

            # Query historical stats per (destination, weekend_date) before target_scan_id
            deals: list[GroupedDeal] = []
            for (dest_code, wk_date), group_trips in grouped_map.items():
                sorted_group = sort_scored_trips(group_trips, sort_by=sort_by)
                best = sorted_group[0]
                alts = sorted_group[1:]

                hist_rows = conn.execute(
                    """
                    SELECT scan_id, MIN(total_price_gbp) AS min_price
                    FROM offers
                    WHERE destination = ? AND weekend_date = ? AND scan_id < ?
                    GROUP BY scan_id
                    ORDER BY scan_id DESC
                    """,
                    (dest_code, wk_date.isoformat(), target_scan_id),
                ).fetchall()

                previous_best = float(hist_rows[0]["min_price"]) if hist_rows else None
                prior_all_time = (
                    min(float(h["min_price"]) for h in hist_rows) if hist_rows else None
                )
                all_time_low = (
                    min(best.total_price_gbp, prior_all_time)
                    if prior_all_time is not None
                    else best.total_price_gbp
                )
                price_delta = (
                    round(best.total_price_gbp - previous_best, 2)
                    if previous_best is not None
                    else None
                )
                is_atl = prior_all_time is not None and best.total_price_gbp < prior_all_time

                deals.append(
                    GroupedDeal(
                        best=best,
                        alternatives=alts,
                        previous_best_gbp=previous_best,
                        price_delta_gbp=price_delta,
                        all_time_low_gbp=round(all_time_low, 2),
                        is_all_time_low=is_atl,
                    )
                )

        # Sort grouped deals using the exact same preference on `deal.best`
        order_lookup = {
            id(t): idx
            for idx, t in enumerate(sort_scored_trips([d.best for d in deals], sort_by=sort_by))
        }
        deals.sort(key=lambda d: order_lookup[id(d.best)])
        return deals

    def get_price_history(
        self,
        destination: str,
        weekend_date: date,
    ) -> list[dict]:
        """Return chronological best price and sea temp snapshots for a (destination, weekend)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.id AS scan_id,
                       s.created_at,
                       MIN(o.total_price_gbp) AS best_price_gbp,
                       MAX(o.beach_hours) AS max_beach_hours,
                       MIN(o.gbp_per_beach_hour) AS best_gbp_per_hour,
                       AVG(o.sea_temp_c) AS sea_temp_c
                FROM offers o
                JOIN scans s ON s.id = o.scan_id
                WHERE o.destination = ? AND o.weekend_date = ?
                GROUP BY s.id
                ORDER BY s.id ASC
                """,
                (destination.strip().upper(), weekend_date.isoformat()),
            ).fetchall()
            return [dict(r) for r in rows]


def _row_to_scored_trip(row: sqlite3.Row, *, min_sea_temp_c: float) -> ScoredTrip:
    sea_temp = float(row["sea_temp_c"]) if row["sea_temp_c"] is not None else None
    is_swimmable = True if sea_temp is None else (sea_temp >= min_sea_temp_c)

    outbound = FlightLeg(
        origin=row["out_origin"],
        destination=row["destination"],
        airline=row["out_airline"],
        flight_number=row["out_flight"],
        departure_dt=datetime.fromisoformat(row["out_dep"]),
        arrival_dt=datetime.fromisoformat(row["out_arr"]),
        duration_minutes=int(row["out_duration_min"]),
        stops=0,
        price_gbp=float(row["out_price_gbp"]),
        booking_url=row["booking_url"],
    )
    inbound = FlightLeg(
        origin=row["destination"],
        destination=row["in_dest"],
        airline=row["in_airline"],
        flight_number=row["in_flight"],
        departure_dt=datetime.fromisoformat(row["in_dep"]),
        arrival_dt=datetime.fromisoformat(row["in_arr"]),
        duration_minutes=int(row["in_duration_min"]),
        stops=0,
        price_gbp=float(row["in_price_gbp"]),
        booking_url=row["booking_url"],
    )
    return ScoredTrip(
        weekend_date=date.fromisoformat(row["weekend_date"]),
        return_date=date.fromisoformat(row["return_date"]),
        destination=row["destination"],
        destination_name=row["destination_name"],
        country=row["country"],
        outbound=outbound,
        inbound=inbound,
        is_open_jaw=bool(row["is_open_jaw"]),
        pricing_mode=row["pricing_mode"],
        total_price_gbp=float(row["total_price_gbp"]),
        beach_hours=float(row["beach_hours"]),
        gbp_per_beach_hour=float(row["gbp_per_beach_hour"]),
        sea_temp_c=sea_temp,
        sea_temp_source=row["sea_temp_source"],
        is_swimmable=is_swimmable,
        booking_url=row["booking_url"],
    )

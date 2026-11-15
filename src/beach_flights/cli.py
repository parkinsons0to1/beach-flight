"""Typer + Rich CLI for beach-flights."""

from __future__ import annotations

import tomllib
from datetime import date, time
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from beach_flights.core.destinations import DESTINATIONS, PRESET_NAMES, resolve_destinations
from beach_flights.core.scanner import BeachScanner
from beach_flights.models import GroupedDeal, ScanConfig
from beach_flights.storage.db import FlightDatabase

app = typer.Typer(
    name="beach-flights",
    help=(
        "Find and track 1-night beach trips from LGW & LHR "
        "by beach hours per pound and sea temp."
    ),
    no_args_is_help=True,
)
console = Console()


def _parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise typer.BadParameter(f"Expected HH:MM time, got '{value}'")
    return time(int(parts[0]), int(parts[1]))


def _load_toml_defaults(config_path: Path | None) -> dict:
    path = config_path or Path("config.toml")
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _render_deals_table(
    deals: list[GroupedDeal],
    *,
    show_alts: bool = False,
    title: str = "Top 1-Night Beach Deals",
) -> None:
    if not deals:
        console.print("[yellow]No matching 1-night deals found for the current filters.[/yellow]")
        return

    table = Table(title=title, show_lines=show_alts)
    table.add_column("#", style="dim", width=3)
    table.add_column("Destination", style="bold cyan")
    table.add_column("Weekend", style="white")
    table.add_column("Outbound", style="green")
    table.add_column("Inbound", style="magenta")
    table.add_column("Beach Hrs", justify="right", style="bold")
    table.add_column("Sea °C", justify="right")
    table.add_column("Price", justify="right", style="bold yellow")
    table.add_column("£/Hr", justify="right", style="bold")
    table.add_column("Alts / Delta", style="dim")

    for idx, deal in enumerate(deals, start=1):
        b = deal.best
        sea_str = (
            f"[bright_cyan]{b.sea_temp_c:.1f}°C[/bright_cyan]"
            if b.sea_temp_c is not None and b.is_swimmable
            else (
                f"[blue]{b.sea_temp_c:.1f}°C ❄[/blue]"
                if b.sea_temp_c is not None
                else "[dim]n/a[/dim]"
            )
        )
        out_str = (
            f"{b.outbound.origin} {b.outbound.departure_dt.strftime('%H:%M')} -> "
            f"{b.outbound.arrival_dt.strftime('%H:%M')} ({b.outbound.airline})"
        )
        in_str = (
            f"{b.inbound.departure_dt.strftime('%H:%M')} -> "
            f"{b.inbound.destination} {b.inbound.arrival_dt.strftime('%H:%M')} "
            f"({b.inbound.airline})"
        )
        badges: list[str] = []
        if b.is_open_jaw:
            badges.append("open-jaw")
        if b.pricing_mode == "round_trip":
            badges.append("RT")
        if deal.alternatives:
            badges.append(f"+{len(deal.alternatives)} alts")
        if deal.is_all_time_low:
            badges.append("[green]ATL![/green]")
        elif deal.price_delta_gbp is not None and deal.price_delta_gbp < 0:
            badges.append(f"[green]-£{abs(deal.price_delta_gbp):.0f}[/green]")
        elif deal.price_delta_gbp is not None and deal.price_delta_gbp > 0:
            badges.append(f"[red]+£{deal.price_delta_gbp:.0f}[/red]")

        table.add_row(
            str(idx),
            f"{b.destination_name} ({b.destination})",
            f"{b.weekend_date.strftime('%a %d %b')}->{b.return_date.strftime('%a %d %b')}",
            out_str,
            in_str,
            f"{b.beach_hours:.1f}h",
            sea_str,
            f"£{b.total_price_gbp:.0f}",
            f"£{b.gbp_per_beach_hour:.2f}",
            " | ".join(badges),
        )

        if show_alts and deal.alternatives:
            for alt in deal.alternatives[:3]:
                alt_out = (
                    f"{alt.outbound.origin} {alt.outbound.departure_dt.strftime('%H:%M')} "
                    f"-> {alt.outbound.arrival_dt.strftime('%H:%M')}"
                )
                alt_in = (
                    f"{alt.inbound.departure_dt.strftime('%H:%M')} -> "
                    f"{alt.inbound.destination} {alt.inbound.arrival_dt.strftime('%H:%M')}"
                )
                table.add_row(
                    "",
                    "  ↳ alt",
                    "",
                    alt_out,
                    alt_in,
                    f"{alt.beach_hours:.1f}h",
                    "",
                    f"£{alt.total_price_gbp:.0f}",
                    f"£{alt.gbp_per_beach_hour:.2f}",
                    alt.pricing_mode,
                )

    console.print(table)


@app.command()
def scan(
    origins: str = typer.Option("LGW,LHR", help="Comma-separated London origins."),
    dest: str | None = typer.Option(
        None, help="Comma-separated beach IATA codes (overrides --preset)."
    ),
    preset: str = typer.Option(
        "winter-sun", help=f"Destination preset ({', '.join(PRESET_NAMES)})."
    ),
    date_from: str | None = typer.Option(None, "--from", help="Start date YYYY-MM-DD."),
    date_to: str | None = typer.Option(None, "--to", help="End date YYYY-MM-DD."),
    weeks: int = typer.Option(4, help="Weeks ahead to scan if --from/--to are omitted."),
    weekend_days: str = typer.Option(
        "sat-sun", help="Comma-separated: sat-sun,fri-sat,sun-mon."
    ),
    open_jaw: bool = typer.Option(
        True, "--open-jaw/--same-airport", help="Allow LGW out + LHR back mixing."
    ),
    out_start: str = typer.Option("05:00", help="Earliest outbound departure HH:MM."),
    out_end: str = typer.Option("10:30", help="Latest outbound departure HH:MM."),
    arr_latest: str = typer.Option("16:45", help="Latest outbound local arrival HH:MM."),
    in_start: str = typer.Option("16:15", help="Earliest inbound departure HH:MM."),
    in_end: str = typer.Option("23:30", help="Latest inbound departure HH:MM."),
    min_hours: float = typer.Option(24.0, help="Minimum beach hours on the ground."),
    min_sea_temp: float = typer.Option(
        17.0, help="Minimum sea temp °C (17.0 = Brighton peak baseline)."
    ),
    include_cold: bool = typer.Option(
        False, help="Include destinations colder than --min-sea-temp."
    ),
    max_price: float = typer.Option(300.0, help="Maximum total round-trip GBP price."),
    sort_by: str = typer.Option("value", "--sort", help="Sort by: value, price, hours, temp."),
    provider: str = typer.Option("fli", help="Flight backend: fli or serpapi."),
    round_trips: bool = typer.Option(
        True, "--round-trips/--no-round-trips", help="Also check LHR round-trip offers."
    ),
    notify: bool = typer.Option(False, help="Send Discord/Telegram alerts if configured."),
    alert_under: float | None = typer.Option(None, help="Alert threshold in GBP."),
    db_path: Path = typer.Option(Path("data/flights.db"), help="SQLite database path."),
    config_file: Path | None = typer.Option(None, help="Optional TOML config file."),
) -> None:
    """Run a live scan for 1-night weekend beach flights + sea temperatures."""
    _ = _load_toml_defaults(config_file)
    parsed_origins = [o.strip().upper() for o in origins.split(",") if o.strip()]
    parsed_dests = [d.strip().upper() for d in dest.split(",") if d.strip()] if dest else []
    parsed_weekends = [w.strip().lower() for w in weekend_days.split(",") if w.strip()]

    cfg = ScanConfig(
        origins=parsed_origins,
        destinations=parsed_dests,
        allow_open_jaw=open_jaw,
        weekend_days=parsed_weekends,  # type: ignore[arg-type]
        outbound_dep_start=_parse_hhmm(out_start),
        outbound_dep_end=_parse_hhmm(out_end),
        outbound_arr_latest=_parse_hhmm(arr_latest) if arr_latest else None,
        inbound_dep_start=_parse_hhmm(in_start),
        inbound_dep_end=_parse_hhmm(in_end),
        min_beach_hours=min_hours,
        min_sea_temp_c=min_sea_temp,
        include_cold=include_cold,
        max_price_gbp=max_price,
        check_round_trips=round_trips,
        provider=provider,  # type: ignore[arg-type]
        sort_by=sort_by,  # type: ignore[arg-type]
    )

    d_from = date.fromisoformat(date_from) if date_from else None
    d_to = date.fromisoformat(date_to) if date_to else None

    db = FlightDatabase(db_path)
    scanner = BeachScanner(db=db)
    summary = scanner.run_scan(
        cfg,
        date_from=d_from,
        date_to=d_to,
        weeks=weeks,
        preset=preset,
        notify=notify,
        alert_under_gbp=alert_under,
        progress_cb=lambda msg: console.print(f"[dim]{msg}[/dim]"),
    )

    console.print(
        f"\n[bold green]Scan #{summary.scan_id} complete[/bold green]: "
        f"{summary.total_offers_saved} qualifying offers saved "
        f"({summary.swimmable_deals_count} swimmable >= {min_sea_temp:.1f}°C, "
        f"{summary.cold_deals_count} colder)."
    )
    if summary.errors:
        warns = "; ".join(summary.errors[:3])
        console.print(f"[yellow]Warnings ({len(summary.errors)}):[/yellow] {warns}")

    _render_deals_table(
        summary.grouped_deals,
        show_alts=False,
        title=f"Scan #{summary.scan_id} Beach Leaderboard (min sea {min_sea_temp:.1f}°C)",
    )


@app.command()
def best(
    min_hours: float = typer.Option(24.0, help="Minimum beach hours."),
    min_sea_temp: float = typer.Option(17.0, help="Minimum sea temp °C."),
    include_cold: bool = typer.Option(False, help="Include deals below min sea temp."),
    max_price: float | None = typer.Option(None, help="Maximum total GBP price."),
    open_jaw: bool = typer.Option(
        True, "--open-jaw/--same-airport", help="Allow open-jaw itineraries."
    ),
    origin: str | None = typer.Option(None, help="Filter to LGW or LHR."),
    dest: str | None = typer.Option(None, help="Filter to destination IATA."),
    sort_by: str = typer.Option("value", "--sort", help="Sort by: value, price, hours, temp."),
    expand: bool = typer.Option(
        False, help="Show alternative flight combinations per destination/weekend."
    ),
    db_path: Path = typer.Option(Path("data/flights.db"), help="SQLite database path."),
) -> None:
    """Query the best saved deals from SQLite without making network calls."""
    db = FlightDatabase(db_path)
    deals = db.get_grouped_deals(
        min_sea_temp_c=min_sea_temp,
        include_cold=include_cold,
        min_beach_hours=min_hours,
        max_price_gbp=max_price,
        allow_open_jaw=open_jaw,
        origin=origin,
        destination=dest,
        sort_by=sort_by,
    )
    _render_deals_table(deals, show_alts=expand, title="Saved Beach Deals (Latest Scan)")


@app.command()
def history(
    dest: str = typer.Option(..., help="Destination IATA code, e.g. AGP."),
    weekend: str = typer.Option(..., help="Weekend outbound date YYYY-MM-DD."),
    db_path: Path = typer.Option(Path("data/flights.db"), help="SQLite database path."),
) -> None:
    """Show historical price and sea temperature snapshots for a destination/weekend."""
    db = FlightDatabase(db_path)
    rows = db.get_price_history(dest, date.fromisoformat(weekend))
    if not rows:
        console.print(f"[yellow]No price history found for {dest.upper()} on {weekend}.[/yellow]")
        return

    table = Table(title=f"Price History: {dest.upper()} ({weekend})")
    table.add_column("Scan #", style="dim")
    table.add_column("Timestamp (UTC)")
    table.add_column("Best £", justify="right", style="bold yellow")
    table.add_column("£/Beach Hr", justify="right")
    table.add_column("Max Hours", justify="right")
    table.add_column("Sea °C", justify="right", style="cyan")

    for r in rows:
        sea = f"{r['sea_temp_c']:.1f}°C" if r["sea_temp_c"] is not None else "n/a"
        table.add_row(
            str(r["scan_id"]),
            str(r["created_at"])[:19],
            f"£{r['best_price_gbp']:.0f}",
            f"£{r['best_gbp_per_hour']:.2f}",
            f"{r['max_beach_hours']:.1f}h",
            sea,
        )
    console.print(table)


@app.command()
def destinations(
    preset: str = typer.Option("all", help=f"Filter preset ({', '.join(PRESET_NAMES)})."),
) -> None:
    """List supported beach destinations, presets, timezones, and offshore coordinates."""
    items = resolve_destinations(preset=preset)
    table = Table(title=f"Beach Destinations ({preset})")
    table.add_column("IATA", style="bold cyan")
    table.add_column("Destination")
    table.add_column("Country")
    table.add_column("Timezone", style="dim")
    table.add_column("Offshore SST Coords", style="dim")
    table.add_column("Presets", style="green")

    for d in items:
        table.add_row(
            d.iata,
            d.name,
            d.country,
            d.timezone,
            f"{d.sea_lat:.2f}, {d.sea_lon:.2f}",
            ", ".join(d.presets),
        )
    console.print(table)
    console.print(f"[dim]Total catalog size: {len(DESTINATIONS)} beach airports.[/dim]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(8080, help="HTTP port."),
    db_path: Path = typer.Option(Path("data/flights.db"), help="SQLite database path."),
) -> None:
    """Launch the local FastAPI web dashboard."""
    from beach_flights.web.app import create_app

    web_app = create_app(db_path=db_path)
    console.print(f"[bold green]Dashboard running at http://{host}:{port}[/bold green]")
    uvicorn.run(web_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()

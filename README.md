# Beach Flights (`LGW` / `LHR`)

Track and rank **1-night weekend beach trips** from London Gatwick (`LGW`) and London Heathrow (`LHR`) by **waking hours on the beach per pound (`£/beach hr`)** and **live sea surface temperature (`>= 17.0°C` Brighton swim baseline)**.

## Key Features
- **Early-Out / Late-Back Filtering:** Targets 05:00–10:30 outbound flights (landing by 14:00) and 18:00–23:30 returns, non-stop only.
- **Timezone-Exact Ground Time (`beach_hours`):** Computes exact hours between landing and return takeoff in UTC across UK, European, Canary, and Cyprus timezones.
- **Live & Forecast Sea Temperature Gate:** Batches offshore beach coordinates against the free Open-Meteo Marine API so cold destinations (`< 17.0°C`) never outrank swimmable beaches.
- **Open-Jaw Mixing + Legacy Round-Trip Check:** Pairs independent one-ways across `LGW` and `LHR` (e.g., Gatwick out, Heathrow back) and compares against LHR round-trip fares.
- **SQLite Price History & Alerts:** Stores every qualifying itinerary, groups the leaderboard by `(destination, weekend)` with expandable alternatives, tracks price drops / all-time lows, and optionally notifies Discord or Telegram.
- **CLI + FastAPI Dashboard:** Run stateless scans via `cron` or explore deals visually in a local web UI.

## Usage

```bash
uv sync

# Scan winter-sun preset (TFS, LPA, ACE, AGP, ALC, FAO, MLA, LCA, PFO) for next 4 Saturdays
uv run beach-flights scan --preset winter-sun --weeks 4

# Scan specific beaches, include Fri->Sat nights, and show colder seas below swimmable deals
uv run beach-flights scan --dest LPA,TFS,AGP,NCE --weekend-days sat-sun,fri-sat --include-cold

# Query saved deals from SQLite with expandable alternative flight times
uv run beach-flights best --expand

# View historical price snapshots for a route/weekend
uv run beach-flights history --dest LPA --weekend 2026-11-21

# Launch the local FastAPI web dashboard
uv run beach-flights serve --port 8080
```

## Optional Webhooks & Paid Provider
- Discord alerts: set `DISCORD_WEBHOOK_URL` and pass `--notify --alert-under 110` to `scan`.
- Telegram alerts: set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` and pass `--notify`.
- SerpApi backend: set `SERPAPI_API_KEY` and pass `--provider serpapi`.

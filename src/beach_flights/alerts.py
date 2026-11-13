"""Optional Discord & Telegram webhook notifications for beach flight deals."""

from __future__ import annotations

import os

import httpx

from beach_flights.models import GroupedDeal
from beach_flights.providers.http_utils import create_http_client


def format_deal_lines(deals: list[GroupedDeal], limit: int = 5) -> str:
    lines: list[str] = []
    for idx, deal in enumerate(deals[:limit], start=1):
        b = deal.best
        sea_str = f"{b.sea_temp_c:.1f}°C" if b.sea_temp_c is not None else "n/a"
        delta_str = ""
        if deal.is_all_time_low:
            delta_str = " [ALL-TIME LOW]"
        elif deal.price_delta_gbp is not None and deal.price_delta_gbp < 0:
            delta_str = f" [down £{abs(deal.price_delta_gbp):.0f}]"
        lines.append(
            f"{idx}. {b.destination_name} ({b.destination}) "
            f"{b.weekend_date.isoformat()}->{b.return_date.isoformat()} | "
            f"£{b.total_price_gbp:.0f} (£{b.gbp_per_beach_hour:.2f}/hr) | "
            f"{b.beach_hours:.1f}h beach | Sea {sea_str} | "
            f"{b.outbound.origin} {b.outbound.departure_dt.strftime('%H:%M')} -> "
            f"{b.inbound.destination} {b.inbound.departure_dt.strftime('%H:%M')}{delta_str}"
        )
    return "\n".join(lines)


def send_deal_alerts(
    deals: list[GroupedDeal],
    *,
    alert_under_gbp: float | None = None,
    discord_webhook_url: str | None = None,
    telegram_bot_token: str | None = None,
    telegram_chat_id: str | None = None,
    client: httpx.Client | None = None,
) -> list[str]:
    """Send notifications for qualifying swimmable deals. Returns channels notified."""
    swimmable = [d for d in deals if d.best.is_swimmable]
    if alert_under_gbp is not None:
        matched = [
            d
            for d in swimmable
            if d.best.total_price_gbp <= alert_under_gbp or d.is_all_time_low
        ]
    else:
        matched = swimmable[:5]

    if not matched:
        return []

    discord_url = discord_webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")
    tg_token = telegram_bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    if not discord_url and not (tg_token and tg_chat):
        return []

    message = "🏖️ **Beach Flights Alert**\n" + format_deal_lines(matched)
    notified: list[str] = []
    owns_client = client is None
    http = client or create_http_client(10.0)
    try:
        if discord_url:
            resp = http.post(discord_url, json={"content": message[:1900]})
            resp.raise_for_status()
            notified.append("discord")
        if tg_token and tg_chat:
            tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            resp = http.post(tg_url, json={"chat_id": tg_chat, "text": message[:4000]})
            resp.raise_for_status()
            notified.append("telegram")
    finally:
        if owns_client:
            http.close()

    return notified

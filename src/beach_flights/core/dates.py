"""Weekend 1-night date pair generation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

WeekendPattern = Literal["sat-sun", "fri-sat", "sun-mon"]

# Python weekday(): Mon=0 .. Fri=4, Sat=5, Sun=6
PATTERN_WEEKDAY: dict[WeekendPattern, int] = {
    "fri-sat": 4,
    "sat-sun": 5,
    "sun-mon": 6,
}


def generate_weekend_pairs(
    date_from: date,
    date_to: date,
    patterns: list[WeekendPattern] | None = None,
) -> list[tuple[date, date]]:
    """Generate sorted (outbound_date, return_date) 1-night pairs in [date_from, date_to]."""
    if date_to < date_from:
        raise ValueError(f"date_to ({date_to}) must be >= date_from ({date_from})")

    active_patterns: list[WeekendPattern] = patterns or ["sat-sun"]
    target_weekdays = {PATTERN_WEEKDAY[p] for p in active_patterns}

    pairs: list[tuple[date, date]] = []
    cur = date_from
    while cur <= date_to:
        if cur.weekday() in target_weekdays:
            ret = cur + timedelta(days=1)
            pairs.append((cur, ret))
        cur += timedelta(days=1)
    return pairs


def default_date_window(weeks: int = 4, start_from: date | None = None) -> tuple[date, date]:
    """Return a default [start, end] range starting tomorrow for `weeks` weeks."""
    base = start_from or date.today()
    start = base + timedelta(days=1)
    end = start + timedelta(days=max(1, weeks) * 7)
    return start, end

"""
Shared helpers for tests that need valid future draw dates.
"""

from datetime import datetime, timedelta, timezone


def future_hour_iso(minute: int = 0) -> str:
    """A UTC timestamp in the future, within the current year, at the given minute."""
    now = datetime.now(timezone.utc)
    candidate = (now + timedelta(hours=2)).replace(minute=minute, second=0, microsecond=0)
    if candidate.year != now.year:
        # Last day of the year: fall back to the latest valid slot.
        candidate = now.replace(hour=23, minute=minute, second=0, microsecond=0)
    return candidate.strftime("%Y-%m-%dT%H:%M:%SZ")


def next_year_iso() -> str:
    """A timestamp in the following year (rejected by the current-year rule)."""
    return f"{datetime.now(timezone.utc).year + 1}-01-15T14:00:00Z"

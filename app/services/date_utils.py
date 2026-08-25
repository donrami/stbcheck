"""
Date parsing utilities for expiry date handling. Stdlib only (zoneinfo).
"""

import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

# Explicit formats tried in order.
_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
    "%Y-%m",
    "%d.%m.%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
]

# Human-readable formats (e.g. admin-injected "April 20, 2027, 4:19 pm"),
# applied after normalizing out commas/extra whitespace.
_HUMAN_FORMATS = [
    "%B %d %Y %I:%M %p",
    "%B %d %Y",
    "%b %d %Y %I:%M %p",
    "%b %d %Y",
]


def _localize(dt: datetime, timezone: str) -> datetime:
    """Attach portal timezone to a naive datetime (best effort)."""
    if timezone != "UTC":
        try:
            dt = dt.replace(tzinfo=ZoneInfo(timezone))
        except Exception:
            pass
    return dt


def _normalize_human(s: str) -> Optional[str]:
    lowered = re.sub(r"[,\s]+", " ", s.strip().lower())
    return lowered or None


def parse_expiry_date(date_str: str, timezone: str = "UTC") -> Optional[datetime]:
    """
    Parse expiry date string: unix timestamps, fixed formats, then
    human-readable month-name formats.

    Args:
        date_str: Date string from portal
        timezone: Timezone name (default UTC) attached to naive results

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None

    s = str(date_str).strip()

    # Unix timestamp (seconds or milliseconds)
    if s.isdigit():
        ts = int(s)
        if ts > 10_000_000_000:
            ts //= 1000
        try:
            return _localize(datetime.fromtimestamp(ts), timezone)
        except (ValueError, OverflowError, OSError):
            pass

    for fmt in _FORMATS:
        for candidate in (s, s.split()[0]):
            try:
                return _localize(datetime.strptime(candidate, fmt), timezone)
            except ValueError:
                continue

    # ponytail: no fuzzy parsing (dateutil dropped); covers the known
    # "Month DD, YYYY[, HH:MM am/pm]" admin format only — extend
    # _HUMAN_FORMATS when a portal ships something else.
    normalized = _normalize_human(s)
    for fmt in _HUMAN_FORMATS:
        try:
            return _localize(datetime.strptime(normalized, fmt), timezone)
        except (ValueError, TypeError):
            continue

    return None

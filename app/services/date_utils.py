"""
Date parsing utilities for expiry date handling.
"""

from datetime import datetime
from typing import Optional

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

try:
    from dateutil import parser as dateparser
    DATEUTIL_AVAILABLE = True
except ImportError:
    DATEUTIL_AVAILABLE = False


def parse_expiry_date(date_str: str, timezone: str = "UTC") -> Optional[datetime]:
    """
    Parse expiry date string with multiple formats and timezone handling.

    Args:
        date_str: Date string from portal
        timezone: Timezone name (default UTC) for localization

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None

    date_str = str(date_str).strip()

    if date_str.isdigit():
        try:
            ts = int(date_str)
            if ts > 10_000_000_000:
                ts = ts // 1000
            dt = datetime.fromtimestamp(ts)
            if timezone != "UTC" and PYTZ_AVAILABLE:
                try:
                    tz = pytz.timezone(timezone)
                    dt = tz.localize(dt)
                except Exception:
                    pass
            return dt
        except (ValueError, OverflowError, OSError):
            pass

    formats = [
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

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.split()[0], fmt)
            if timezone != "UTC" and PYTZ_AVAILABLE:
                try:
                    tz = pytz.timezone(timezone)
                    dt = tz.localize(dt)
                except Exception:
                    pass
            return dt
        except (ValueError, AttributeError):
            continue

    if DATEUTIL_AVAILABLE:
        try:
            dt = dateparser.parse(date_str, fuzzy=True)
            if dt:
                if timezone != "UTC" and dt.tzinfo is None and PYTZ_AVAILABLE:
                    try:
                        tz = pytz.timezone(timezone)
                        dt = tz.localize(dt)
                    except Exception:
                        pass
                return dt
        except Exception:
            pass

    return None

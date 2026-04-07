"""
Expiry date detection utilities.
"""

import re
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class ExpirySource:
    """Tracks where an expiry date was found."""

    field_name: str
    endpoint: str  # 'profile' or 'account_info'
    raw_value: str
    parsed_value: Optional[str] = None


def detect_expiry(data, depth=0):
    """
    Recursively search for expiry date in portal response data.

    Args:
        data: Dictionary containing portal response data
        depth: Current recursion depth (max 4)

    Returns:
        Expiry date string if found, None otherwise
    """
    if not isinstance(data, dict) or depth > 4:
        return None

    # Priority keys for expiry dates - ordered by priority
    primary_keys = [
        # Stalker/Ministra specific (high priority)
        "expire_billing_date",
        "tariff_expired_date",
        # Standard fields
        "expire_date",
        "exp_date",
        "expDate",
        "max_view_date",
        "end_date",
        "end_date_time",
        "date_end",
        "valid_until",
        "access_end",
        "active_until",
        "subscription_end",
        "billing_end",
        "plan_expires",
        "expires",
        "expiry_date",
        "expired",
        "phone",
    ]

    # Values that mean "no expiry" — return them as-is
    unlimited_values = [
        "unlimited",
        "lifetime",
        "never",
        "infinity",
        "infinite",
        "permanent",
        "forever",
        "no expiry",
        "no limit",
        "no expiration",
    ]

    # Enhanced junk/invalid values to skip
    junk_values = {
        "0",
        "0000-00-00",
        "0000-00-00 00:00:00",
        "null",
        "none",
        "false",
        "0000000000",
        "1970-01-01",
        "1900-01-01",
        "0001-01-01",
        "",
    }

    # 1. Check primary keys
    for key in primary_keys:
        val = data.get(key)
        if val is not None:
            val_str = str(val).strip()
            if val_str.lower() in unlimited_values:
                return str(val)
            if val_str.lower() not in junk_values:
                if key == "phone" and not re.match(r"\d{4}-\d{2}-\d{2}", val_str):
                    continue
                return val_str

    # 2. Aggressive search: Check ANY key that contains date/expire/end keywords
    for k, v in data.items():
        if v is None:
            continue

        if isinstance(v, (dict, list)):
            continue

        v_str = str(v).strip()
        if not v_str:
            continue

        k_low = str(k).lower()
        if any(
            x in k_low
            for x in [
                "expire",
                "end_date",
                "valid_until",
                "exp_date",
                "access_end",
                "billing",
                "subscription",
                "tariff",
            ]
        ):
            if v_str.lower() not in junk_values:
                return v_str

    # 3. Recursively check ALL nested dicts
    for key, value in data.items():
        if isinstance(value, dict):
            res = detect_expiry(value, depth + 1)
            if res:
                return res
        elif isinstance(value, list) and len(value) > 0:
            for item in value:
                if isinstance(item, dict):
                    res = detect_expiry(item, depth + 1)
                    if res:
                        return res

    return None


def detect_expiry_with_source(
    data, endpoint: str = "profile", depth: int = 0
) -> Tuple[Optional[str], Optional[ExpirySource]]:
    """
    Recursively search for expiry date in portal response data, tracking the source.

    Args:
        data: Dictionary containing portal response data
        endpoint: Name of the endpoint ('profile' or 'account_info')
        depth: Current recursion depth (max 4)

    Returns:
        Tuple of (expiry_date_string, ExpirySource) or (None, None)
    """
    if not isinstance(data, dict) or depth > 4:
        return None, None

    if depth <= 2:
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"[detect] depth={depth}, endpoint={endpoint}, keys={list(data.keys())[:10]}"
        )

    primary_keys = [
        "expire_billing_date",
        "tariff_expired_date",
        "expire_date",
        "exp_date",
        "expDate",
        "max_view_date",
        "end_date",
        "end_date_time",
        "date_end",
        "valid_until",
        "access_end",
        "active_until",
        "subscription_end",
        "billing_end",
        "plan_expires",
        "expires",
        "expiry_date",
        "expired",
        "phone",
    ]

    unlimited_values = [
        "unlimited",
        "lifetime",
        "never",
        "infinity",
        "infinite",
        "permanent",
        "forever",
        "no expiry",
        "no limit",
        "no expiration",
    ]

    junk_values = {
        "0",
        "0000-00-00",
        "0000-00-00 00:00:00",
        "null",
        "none",
        "false",
        "0000000000",
        "1970-01-01",
        "1900-01-01",
        "0001-01-01",
        "",
    }

    for key in primary_keys:
        val = data.get(key)
        if val is not None:
            val_str = str(val).strip()
            if val_str.lower() in unlimited_values:
                source = ExpirySource(
                    field_name=key,
                    endpoint=endpoint,
                    raw_value=str(val),
                    parsed_value=str(val),
                )
                return str(val), source
            if val_str.lower() not in junk_values:
                if key == "phone" and not re.match(r"\d{4}-\d{2}-\d{2}", val_str):
                    continue
                if val_str.isdigit() and len(val_str) >= 10:
                    try:
                        ts = int(val_str)
                        if ts > 10_000_000_000:
                            ts = ts // 1000
                        from datetime import datetime as _dt

                        dt = _dt.fromtimestamp(ts)
                        formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
                        source = ExpirySource(
                            field_name=key,
                            endpoint=endpoint,
                            raw_value=str(val),
                            parsed_value=formatted,
                        )
                        return formatted, source
                    except (ValueError, OverflowError):
                        source = ExpirySource(
                            field_name=key, endpoint=endpoint, raw_value=str(val)
                        )
                        return val_str, source
                else:
                    source = ExpirySource(
                        field_name=key,
                        endpoint=endpoint,
                        raw_value=str(val),
                        parsed_value=val_str,
                    )
                    return val_str, source

    for k, v in data.items():
        if v is None:
            continue

        if not isinstance(v, str):
            continue

        v_str = v.strip()
        if not v_str:
            continue

        k_low = str(k).lower()
        if any(
            x in k_low
            for x in [
                "expire",
                "end_date",
                "valid_until",
                "exp_date",
                "access_end",
                "billing",
                "subscription",
                "tariff",
            ]
        ):
            if v_str.lower() not in junk_values:
                if "-" in v_str or (v_str.isdigit() and len(v_str) >= 10):
                    if v_str.isdigit() and len(v_str) >= 10:
                        try:
                            ts = int(v_str)
                            if ts > 10_000_000_000:
                                ts = ts // 1000
                            from datetime import datetime as _dt

                            dt = _dt.fromtimestamp(ts)
                            formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
                            source = ExpirySource(
                                field_name=k,
                                endpoint=endpoint,
                                raw_value=v_str,
                                parsed_value=formatted,
                            )
                            return formatted, source
                        except (ValueError, OverflowError):
                            source = ExpirySource(
                                field_name=k, endpoint=endpoint, raw_value=v_str
                            )
                            return v_str, source
                    source = ExpirySource(
                        field_name=k,
                        endpoint=endpoint,
                        raw_value=v_str,
                        parsed_value=v_str,
                    )
                    return v_str, source

    for key, value in data.items():
        if isinstance(value, dict):
            res, source = detect_expiry_with_source(value, endpoint, depth + 1)
            if res:
                return res, source
        elif isinstance(value, list) and len(value) > 0:
            for item in value:
                if isinstance(item, dict):
                    res, source = detect_expiry_with_source(item, endpoint, depth + 1)
                    if res:
                        return res, source

    return None, None

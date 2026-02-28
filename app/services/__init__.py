"""
Services module for STBcheck.

Contains business logic for portal interactions and utilities.
"""

from app.services.stalker import StalkerPortal
from app.services.utils import (
    detect_expiry,
    is_portal_url,
    extract_portal_mac_pairs,
    clean_stalker_url,
    is_safe_url,
    PORTAL_HEADERS,
)

__all__ = [
    "StalkerPortal",
    "detect_expiry",
    "is_portal_url",
    "extract_portal_mac_pairs",
    "clean_stalker_url",
    "is_safe_url",
    "PORTAL_HEADERS",
]
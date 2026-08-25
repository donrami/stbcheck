"""
Services module for STBcheck.

Contains business logic for portal interactions and utilities.
"""

from app.services.base import (
    PORTAL_HEADERS,
    MAG200_USER_AGENT,
    MAG254_USER_AGENT,
    MAG250_XUA,
)
from app.services.expiry import detect_expiry, detect_expiry_with_source, ExpirySource
from app.services.date_utils import parse_expiry_date
from app.services.url_validator import (
    is_safe_url,
    is_safe_url_with_redirect_check,
    is_portal_url,
)
from app.services.text_parser import extract_portal_mac_pairs, clean_stalker_url

__all__ = [
    # Base constants
    "PORTAL_HEADERS",
    "MAG200_USER_AGENT",
    "MAG254_USER_AGENT",
    "MAG250_XUA",
    # Expiry detection
    "detect_expiry",
    "detect_expiry_with_source",
    "ExpirySource",
    "parse_expiry_date",
    # URL validation
    "is_safe_url",
    "is_safe_url_with_redirect_check",
    "is_portal_url",
    # Text parsing
    "extract_portal_mac_pairs",
    "clean_stalker_url",
]

"""
Shared constants and base utilities for Stalker services.
"""

import re
from typing import Optional, List, Any, Dict

# MAG200 User-Agent string (used for portal headers)
MAG200_USER_AGENT = (
    "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) "
    "MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
)

# MAG254 User-Agent string (used for streaming and X-User-Agent)
MAG254_USER_AGENT = (
    "Mozilla/5.0 (QtEmbedded; U; Linux; C) MAG254 stbapp ver: 2 rev: 250 Safari/533.16"
)

# Standard MAG250 X-User-Agent header value
MAG250_XUA = "model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c"

# Default headers for portal communication
PORTAL_HEADERS = {
    "User-Agent": MAG200_USER_AGENT,
    "Connection": "keep-alive",
}


def clean_json_response(text: str) -> str:
    """
    Clean JSON response from portal wrappers.

    Args:
        text: Raw response text

    Returns:
        Cleaned JSON string
    """
    if not text:
        return ""
    text = text.strip()
    if text.startswith("/*-secure-") and text.endswith("*/"):
        text = text[10:-2]
    js_match = re.search(r"on_success\([^,]+,\s*(\{.*\}|\[.*\])\s*\)", text, re.DOTALL)
    if js_match:
        text = js_match.group(1)
    return text


def get_handshake_paths(base_url: str, add_trailing_slash: bool = False) -> List[str]:
    """
    Generate list of endpoint paths to try for handshake.

    Args:
        base_url: Base portal URL
        add_trailing_slash: If True, add trailing slash to base_url when not ending in .php

    Returns:
        List of candidate endpoint URLs
    """
    base_variant = base_url
    if add_trailing_slash and not base_url.endswith(".php"):
        base_variant = f"{base_url}/"

    return [
        f"{base_url}/server/load.php",
        f"{base_url}/portal.php",
        base_variant,
    ]


def extract_token(response: Any) -> Optional[str]:
    """
    Extract auth token from handshake response.

    Args:
        response: Response data (dict or string)

    Returns:
        Token string if found, None otherwise
    """
    if isinstance(response, dict):
        return response.get("token")
    elif isinstance(response, str):
        return response
    return None


def unwrap_response(data: Any) -> Any:
    """
    Unwrap portal response envelope (js/result).

    Args:
        data: Raw response data

    Returns:
        Unwrapped data (usually dict or list)
    """
    if not isinstance(data, dict):
        return data

    if "js" in data:
        data = data["js"]

    if isinstance(data, dict) and "result" in data:
        result = data["result"]
        if isinstance(result, (dict, list)):
            return result

    return data

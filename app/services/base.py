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
    # Remove any leading/trailing whitespace, BOM, and non-printable characters
    text = text.strip()
    # Remove BOM if present
    if text.startswith("\ufeff"):
        text = text[1:]
    # Remove null bytes
    text = text.replace("\x00", "")
    # Try to extract JSON from common JS wrappers
    if text.startswith("/*-secure-") and text.endswith("*/"):
        text = text[10:-2]
    # Look for on_success callback pattern
    js_match = re.search(r"on_success\([^,]+,\s*(\{.*\}|\[.*\])\s*\)", text, re.DOTALL)
    if js_match:
        text = js_match.group(1)
    # Also try to extract JSON from anywhere in the text if we still don't have a brace
    if not text.startswith("{") and not text.startswith("["):
        # Find first JSON object or array
        brace_match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(1)
    return text.strip()


def normalize_mac(mac: str) -> str:
    """Normalize MAC to uppercase with colons (XX:XX:XX:XX:XX:XX).

    Args:
        mac: MAC address in any common format (with/without colons, hyphens, uppercase/lowercase)

    Returns:
        Normalized MAC string, or original if invalid (length not 12 or contains non-hex chars)
    """
    if not mac:
        return mac
    clean = mac.upper().replace("-", ":").replace(":", "")
    if len(clean) == 12 and all(c in "0123456789ABCDEF" for c in clean):
        return ":".join([clean[i : i + 2] for i in range(0, 12, 2)])
    return mac


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
        f"{base_url}/stalker_portal/server/load.php",
        f"{base_url}/stalker_portal/portal.php",
        f"{base_url}/c/server/load.php",
        f"{base_url}/c/portal.php",
    ]


def extract_token(response: Any) -> Optional[str]:
    """
    Extract auth token from handshake response.

    Supports multiple response formats commonly used by Stalker portals:
    - Direct string token
    - {"token": "..."}
    - {"js": {"token": "..."}}
    - {"result": {"token": "..."}}
    - {"data": {"token": "..."}}
    - Nested structures with alternative keys like "ptoken", "session_token", etc.

    Args:
        response: Response data (dict, string, or other)

    Returns:
        Token string if found, None otherwise
    """
    if isinstance(response, str):
        # Sometimes the entire response is just the token
        return response.strip()

    if isinstance(response, dict):
        # Check common token keys at top level (including alternatives)
        token_keys = [
            "token",
            "ptoken",
            "session_token",
            "auth_token",
            "access_token",
            "jwt",
            "auth",
        ]
        for key in token_keys:
            if key in response and isinstance(response[key], str):
                return response[key].strip()

        # Recursively search in nested dicts/lists for token
        def search_nested(obj: Any) -> Optional[str]:
            if isinstance(obj, dict):
                # Check this level first
                for key in token_keys:
                    if key in obj and isinstance(obj[key], str):
                        return obj[key].strip()
                # Recurse into values
                for v in obj.values():
                    result = search_nested(v)
                    if result:
                        return result
            elif isinstance(obj, list):
                for item in obj:
                    result = search_nested(item)
                    if result:
                        return result
            return None

        found = search_nested(response)
        if found:
            return found

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

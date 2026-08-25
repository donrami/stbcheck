"""
Shared constants and base utilities for Stalker services.
"""

import json
import re
from typing import Optional, List, Any

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
    Clean JSON response, removing common wrappers and extracting the first valid JSON object.

    Args:
        text: Raw response text

    Returns:
        Cleaned JSON string, or empty string if no valid JSON found
    """
    if not text:
        return ""

    # Remove BOM and null bytes
    text = text.lstrip("\ufeff").replace("\x00", "")
    text = text.strip()

    # If it looks like valid JSON already, try parsing directly
    if text.startswith("{") or text.startswith("["):
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass  # Fall through to extraction

    # Remove common JS wrappers
    if text.startswith("/*-secure-") and text.endswith("*/"):
        text = text[10:-2].strip()

    # Extract from on_success callback
    js_match = re.search(r"on_success\([^,]+,\s*(\{.*\}|\[.*\])\s*\)", text, re.DOTALL)
    if js_match:
        candidate = js_match.group(1)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Find the first balanced brace block (object or array)
    start = -1
    for i, ch in enumerate(text):
        if ch == "{" or ch == "[":
            start = i
            break

    if start == -1:
        return ""

    # Use a simple stack-based parser to find the matching closing brace/bracket
    stack = []
    in_string = False
    escape = False
    opening = text[start]
    closing = "}" if opening == "{" else "]"

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\" and in_string:
            escape = True
            continue

        if ch == '"' and not escape:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == opening:
            stack.append(ch)
        elif ch == closing:
            if stack and stack[-1] == opening:
                stack.pop()
                if not stack:
                    # Found complete JSON
                    candidate = text[start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        # Continue searching after this position
                        start = i + 1
                        # reset and look for next opening
                        for j in range(start, len(text)):
                            if text[j] == "{" or text[j] == "[":
                                start = j
                                opening = text[j]
                                closing = "}" if opening == "{" else "]"
                                stack = []
                                break
                        continue
        elif ch == "[" or ch == "(":
            # Ignore other bracket types inside; they are part of data
            pass

    # No valid JSON found
    return ""


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

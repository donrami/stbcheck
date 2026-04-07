"""
URL validation and SSRF protection utilities.
"""

import re
import ipaddress
from urllib.parse import urlparse
from typing import Optional

from app.config import settings


def _is_hostname_forbidden(hostname: str) -> bool:
    """
    Check if a hostname is forbidden (private/localhost).

    Args:
        hostname: Hostname string to check

    Returns:
        True if hostname is forbidden, False otherwise
    """
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return True
    except ValueError:
        if hostname.lower() in (
            "localhost",
            "localhost.localdomain",
            "localhost6",
            "localhost6.localdomain6",
        ):
            return True
    return False


def is_safe_url(url_str: str, allow_redirects: bool = False) -> bool:
    """
    Validate URL safety to prevent SSRF attacks.

    Args:
        url_str: URL string to validate
        allow_redirects: If True, follow redirects and validate final URL.
                        If False, only validate the initial URL.

    Returns:
        True if URL is safe, False otherwise
    """
    try:
        parsed = urlparse(url_str)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        if _is_hostname_forbidden(hostname):
            return False

        if allow_redirects:
            import requests

            try:
                response = requests.head(
                    url_str,
                    timeout=settings.logo_fetch_timeout,
                    allow_redirects=True,
                    verify=settings.verify_ssl,
                )
                final_url = response.url
                final_parsed = urlparse(final_url)
                final_hostname = final_parsed.hostname

                if final_hostname and _is_hostname_forbidden(final_hostname):
                    return False
            except Exception:
                return False

        return True
    except Exception:
        return False


def is_safe_url_with_redirect_check(url_str: str) -> bool:
    """
    Validate URL and follow redirects to check the final destination.

    Args:
        url_str: URL string to validate

    Returns:
        True if URL is safe (initial and final destination), False otherwise
    """
    return is_safe_url(url_str, allow_redirects=True)


def is_portal_url(url: str) -> bool:
    """
    Check if a URL appears to be a Stalker/Ministra portal URL.

    Args:
        url: URL string to check

    Returns:
        True if URL looks like a portal URL, False otherwise
    """
    u = url.lower().rstrip("/")
    return (
        u.endswith("/c") or "/c/" in u or "/portal.php" in u or "/server/load.php" in u
    )

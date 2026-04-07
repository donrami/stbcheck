"""
StalkerPortal client for interacting with IPTV portals.

This module provides a synchronous interface for Stalker portal operations.
"""

import logging
import re
import json
import requests
from typing import Optional, Dict, Any

from app.config import settings
from app.services.stalker_async import ExpirationInfo
from app.services.base import (
    clean_json_response,
    get_handshake_paths,
    extract_token,
    unwrap_response,
    PORTAL_HEADERS,
    MAG250_XUA,
)

logger = logging.getLogger(__name__)


class StalkerPortal:
    """
    StalkerPortal client for interacting with IPTV portals.

    This class provides a synchronous interface for Stalker portal operations.

    Args:
        portal_url: The base URL of the Stalker portal
        mac_address: The MAC address of the MAG device
    """

    def __init__(self, portal_url: str, mac_address: str):
        self.base_url = portal_url.rstrip("/")
        self.mac = mac_address.upper()
        self.session = requests.Session()
        self.session.headers.update(PORTAL_HEADERS)
        self.token = None
        self.active_path = None

        # Standard MAG250 Headers
        self.headers = {
            "X-User-Agent": "model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c",
            "Cookie": f"mac={self.mac}",
            "Accept": "*/*",
        }

    def _request(self, params, path=None):
        target_path = path or self.active_path
        if not target_path:
            return None

        try:
            full_params = {"JsHttpRequest": "1-xml", **params}
            if self.token:
                self.headers["Authorization"] = f"Bearer {self.token}"

            response = self.session.get(
                target_path,
                params=full_params,
                headers=self.headers,
                timeout=settings.request_timeout,
            )
            if response.status_code == 404:
                return 404

            response.raise_for_status()
            try:
                data = response.json()
            except json.JSONDecodeError:
                cleaned = clean_json_response(response.text)
                try:
                    data = json.loads(cleaned)
                except (json.JSONDecodeError, ValueError):
                    return None

            data = unwrap_response(data)
            return data
        except Exception:
            return None

    def _clean_json(self, text: str) -> str:
        """Clean JSON response from portal wrappers (kept for backward compatibility)."""
        return clean_json_response(text)

    def handshake(self) -> bool:
        """
        Perform handshake with the portal to get auth token.

        Tries multiple common endpoints to find a working handshake URL.

        Returns:
            True if handshake successful and token obtained, False otherwise
        """
        paths_to_try = get_handshake_paths(self.base_url)

        for path in paths_to_try:
            res = self._request({"type": "stb", "action": "handshake"}, path=path)
            if res is None:
                continue

            token = extract_token(res)

            if token:
                self.token = token
                self.active_path = path
                logger.debug(f"Handshake successful with {path}, token obtained")
                return True

        return False

    def get_profile(self) -> Optional[Dict[str, Any]]:
        """Get STB profile from the portal."""
        return self._request(
            {
                "type": "stb",
                "action": "get_profile",
                "stb_type": "MAG250",
                "sn": "1234567890123",
            }
        )

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account info from the portal."""
        result = self._request({"type": "stb", "action": "get_account_info"})
        if result is None or result == 404:
            result = self._request({"type": "stb", "action": "get_main_info"})
        return result

    def get_itv_info(self) -> Optional[Dict[str, Any]]:
        """Get ITV info from the portal."""
        return self._request({"type": "itv", "action": "get_itv_info"})

    def get_channels(self) -> Optional[Dict[str, Any]]:
        """Get all channels from the portal."""
        return self._request({"type": "itv", "action": "get_all_channels"})

    def get_genres(self) -> Optional[Dict[str, Any]]:
        """Get genres from the portal."""
        return self._request({"type": "itv", "action": "get_genres"})

    def get_itv_groups(self) -> Optional[Dict[str, Any]]:
        """Get ITV groups from the portal."""
        return self._request({"type": "itv", "action": "get_itv_groups"})

    def get_short_genres(self) -> Optional[Dict[str, Any]]:
        """Get short genres from the portal."""
        return self._request({"type": "itv", "action": "get_short_genres"})

    def get_all_itv_groups(self) -> Optional[Dict[str, Any]]:
        """Get all ITV groups from the portal."""
        return self._request({"type": "itv", "action": "get_all_itv_groups"})

    def get_categories(self) -> Optional[Dict[str, Any]]:
        """Get categories from the portal."""
        return self._request({"type": "itv", "action": "get_categories"})

    def get_expiration_info(self) -> ExpirationInfo:
        """
        Get expiration information synchronously.

        Returns:
            ExpirationInfo object with account status and expiration date
        """
        # Note: Full synchronous implementation would require duplicating
        # the async logic. For now, attempt a simple handshake-based check.
        try:
            if not self.token and not self.handshake():
                return ExpirationInfo(
                    status="Invalid",
                    expiration=None,
                    error="Handshake failed - cannot authenticate",
                )

            # Try to get profile for status
            profile = self.get_profile()
            if profile and isinstance(profile, dict):
                status_val = profile.get("status")
                blocked_val = profile.get("blocked")
                is_active = status_val == 1 or status_val == "1"
                is_not_blocked = blocked_val == "0" or blocked_val == 0

                if is_active and is_not_blocked:
                    return ExpirationInfo(
                        status="Active", expiration="Unlimited", error=None
                    )

            return ExpirationInfo(
                status="Invalid", expiration=None, error="Account not active"
            )
        except Exception as e:
            logger.error(f"Get expiration info error: {e}")
            return ExpirationInfo(
                status="Invalid",
                expiration=None,
                error=f"Synchronous wrapper error: {str(e)}",
            )

    def create_link(
        self,
        cmd: str,
        series: str = "0",
        forced_storage: str = "0",
        disable_ad: str = "0",
        download: str = "0",
        force_ch_link_check: str = "0",
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a streaming link for a channel.

        Args:
            cmd: Channel command
            series: Series flag (default "0")
            forced_storage: Forced storage flag (default "0")
            disable_ad: Disable ad flag (default "0")
            download: Download flag (default "0")
            force_ch_link_check: Force channel link check (default "0")
            **kwargs: Additional parameters

        Returns:
            Dictionary with link info or None
        """
        params = {
            "type": "itv",
            "action": "create_link",
            "cmd": cmd,
            "series": series,
            "forced_storage": forced_storage,
            "disable_ad": disable_ad,
            "download": download,
            "force_ch_link_check": force_ch_link_check,
        }
        params.update(kwargs)
        return self._request(params)

    def close(self) -> None:
        """Close the underlying session."""
        try:
            if self.session:
                self.session.close()
        except Exception as e:
            logger.error(f"Close error: {e}")

    def __del__(self):
        """Destructor to ensure session is closed."""
        self.close()


__all__ = ["StalkerPortal", "PORTAL_HEADERS", "ExpirationInfo"]

"""
Asynchronous Stalker/Ministra Portal Client for MAG STB account checking.

This module provides a high-performance, asynchronous client for checking
the validity and expiration date of MAG Set-Top Box accounts on Stalker
middleware servers.
"""

import asyncio
import logging
import re
import json
import time
import random
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass

from urllib.parse import quote

import aiohttp
from yarl import URL

from app.config import settings
from app.services.base import (
    clean_json_response,
    get_handshake_paths,
    extract_token,
    unwrap_response,
    MAG200_USER_AGENT,
)
from app.services.expiry import detect_expiry_with_source
from app.services.date_utils import parse_expiry_date


logger = logging.getLogger(__name__)


@dataclass
class ExpirationInfo:
    """
    Data class representing the expiration information for a MAG STB account.

    Attributes:
        status: Account status - "Active", "Expired", or "Invalid"
        expiration: Expiration date string in "YYYY-MM-DD HH:MM:SS" format,
                   "Unlimited" for non-expiring accounts, or None if unavailable
        error: Error message if the request failed, None otherwise
        is_stalker: Whether the portal is detected as Stalker/Ministra
        stalker_fields: Additional Stalker-specific fields (max_online, storages, etc.)
        source: Information about which field/endpoint provided the expiry
    """

    status: str
    expiration: Optional[str]
    error: Optional[str] = None
    is_stalker: bool = False
    stalker_fields: Optional[Dict[str, Any]] = None
    source_endpoint: Optional[str] = None
    source_field: Optional[str] = None


class StalkerClient:
    """
    Asynchronous client for interacting with Stalker/Ministra IPTV portals.

    This client mimics a MAG box to authenticate and retrieve account information,
    particularly the expiration date.

    Args:
        portal_url: The base URL of the Stalker portal (e.g., http://example.com)
        mac_address: The MAC address of the MAG device (e.g., 00:1A:2B:3C:4D:5E)
        timeout: Request timeout in seconds (default: 10)
        enable_cache: Whether to enable response caching (default: False)
        cache_ttl: Cache TTL in seconds (default: 300)
        x_user_agent: X-User-Agent header value (default: settings.x_user_agent)
    """

    def __init__(
        self,
        portal_url: str,
        mac_address: str,
        timeout: int = settings.request_timeout,
        enable_cache: bool = False,
        cache_ttl: int = settings.logo_cache_ttl,
        x_user_agent: str = settings.x_user_agent,
    ):
        """
        Initialize the StalkerClient with portal URL and MAC address.

        Args:
            portal_url: Base portal URL (will be stripped of trailing slash)
            mac_address: MAC address (will be converted to uppercase)
            timeout: Request timeout in seconds (default: 10)
            enable_cache: Enable in-memory caching of expiration results
            cache_ttl: Cache TTL in seconds (default: 300)
            x_user_agent: Override the configured X-User-Agent header value
        """
        self.base_url = portal_url.rstrip("/")
        self.mac = mac_address.upper()
        self.stb_lang = "en"
        self.timezone = getattr(settings, "default_timezone", "Europe/London")
        self.timeout = timeout
        self.x_user_agent = x_user_agent
        self._session: Optional[aiohttp.ClientSession] = None
        self._token: Optional[str] = None
        self._active_path: Optional[str] = None

        # Caching support
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self._cache: Optional[Dict[str, Dict]] = {} if enable_cache else None

    def _get_headers(self) -> Dict[str, str]:
        """
        Generate the required headers for MAG box emulation.

        Returns:
            Dictionary of HTTP headers
        """
        return {
            "User-Agent": MAG200_USER_AGENT,
            "Accept": "*/*",
            "Accept-Charset": "UTF-8,*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "X-User-Agent": self.x_user_agent,
            "Referer": f"{self.base_url}/",
            "Connection": "keep-alive",
        }

    async def _ensure_session(self) -> None:
        """Create an aiohttp ClientSession if not already exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                cookie_jar=aiohttp.CookieJar(unsafe=True),
            )
            # Initialize base cookies with root path so they're sent for all portal paths
            base_url_obj = URL(self.base_url)
            root_url = base_url_obj.with_path("/")
            self._session.cookie_jar.update_cookies(
                {
                    "mac": self.mac,
                    "stb_lang": self.stb_lang,
                    "timezone": self.timezone,
                },
                root_url,
            )

    async def _request(
        self,
        params: Dict[str, str],
        path: Optional[str] = None,
        *,
        retry: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Make an asynchronous HTTP request to the portal.

        Args:
            params: Query parameters dictionary
            path: Optional specific endpoint path (uses active_path if None)

        Returns:
            Parsed JSON response as dictionary, or None on error
        """
        await self._ensure_session()

        target_path = path or self._active_path
        if not target_path:
            return None

        headers = self._get_headers()
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            full_params = {"JsHttpRequest": "1-xml", **params}
            async with self._session.get(
                target_path, params=full_params, headers=headers
            ) as response:
                if response.status == 404:
                    return None

                if response.status in (401, 403):
                    if retry:
                        logger.debug(
                            f"HTTP {response.status} persists on {target_path} after re-handshake"
                        )
                        return None
                    logger.info(
                        f"HTTP {response.status} on {target_path}; clearing token and re-running handshake"
                    )
                    self._clear_auth_state()
                    await self._handshake()
                    return await self._request(params, path=path, retry=True)

                response.raise_for_status()
                try:
                    data = await response.json()
                except (aiohttp.ContentTypeError, json.JSONDecodeError):
                    raw_text = await response.text()
                    cleaned = clean_json_response(raw_text)
                    try:
                        data = json.loads(cleaned)
                    except (json.JSONDecodeError, ValueError):
                        return None

                data = unwrap_response(data)
                if self._is_authorization_failure(data):
                    if retry:
                        logger.debug(
                            f"Authorization failure persists on {target_path} after re-handshake"
                        )
                        return data
                    logger.info(
                        f"Authorization failure on {target_path}; clearing token and re-running handshake"
                    )
                    self._clear_auth_state()
                    await self._handshake()
                    return await self._request(params, path=path, retry=True)
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug(f"Request error to {target_path}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Unexpected error during request: {e}")
            return None

    async def _request_full(self, params, path=None):
        """
        Make request and return the full response structure for expiry detection.

        Returns dict with:
            - raw: The full response dict
            - js: The js sub-object (if present)
            - result: The extracted result (same as _request returns)
        """
        await self._ensure_session()

        target_path = path or self._active_path
        if not target_path:
            return None

        headers = self._get_headers()
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            full_params = {"JsHttpRequest": "1-xml", **params}
            async with self._session.get(
                target_path, params=full_params, headers=headers
            ) as response:
                if response.status == 404:
                    return None

                response.raise_for_status()
                try:
                    data = await response.json()
                except (aiohttp.ContentTypeError, json.JSONDecodeError):
                    raw_text = await response.text()
                    cleaned = clean_json_response(raw_text)
                    try:
                        data = json.loads(cleaned)
                    except (json.JSONDecodeError, ValueError):
                        return None

                if not isinstance(data, dict):
                    return None

                js_obj = data.get("js") if "js" in data else data
                result_obj = (
                    js_obj.get("result")
                    if isinstance(js_obj, dict) and "result" in js_obj
                    else js_obj
                )

                if self._is_authorization_failure(js_obj):
                    logger.debug(
                        f"Authorization failure in response from {target_path}: {js_obj}"
                    )

                return {
                    "raw": data,
                    "js": js_obj if isinstance(js_obj, dict) else {},
                    "result": result_obj
                    if isinstance(result_obj, (dict, list))
                    else {},
                }
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug(f"Request error to {target_path}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Unexpected error during request: {e}")
            return None

    @staticmethod
    def _is_authorization_failure(data: Any) -> bool:
        """
        Detect authorization failures hidden inside HTTP 200 responses.

        Some portals return HTTP 200 with a body signaling an expired or
        missing token instead of a proper 401/403.

        Args:
            data: Parsed (and unwrapped) response payload

        Returns:
            True if the payload indicates an authorization failure
        """
        if not isinstance(data, dict):
            return False
        if data.get("authorization_failed"):
            return True
        for key in ("error", "message"):
            value = data.get(key)
            if isinstance(value, str) and "authorization" in value.lower():
                return True
        return False

    def _clear_auth_state(self) -> None:
        """
        Clear the cached token from state and the session cookie jar.

        Called before a re-handshake so the portal never sees a stale or
        expired token cookie alongside the new handshake request.
        """
        self._token = None
        try:
            root_url = URL(self.base_url).with_path("/")
            self._session.cookie_jar.update_cookies({"token": ""}, root_url)
        except Exception as e:
            logger.debug(f"Failed to clear token cookie: {e}")

    async def _handshake(self) -> bool:
        """
        Perform handshake with the portal to obtain an authorization token.

        Tries multiple common endpoints to find a working handshake URL.
        Includes 404 fallback with token+prehash generation.

        Returns:
            True if handshake successful and token obtained, False otherwise
        """
        await self._ensure_session()
        paths_to_try = get_handshake_paths(self.base_url, add_trailing_slash=True)
        logger.info(f"Trying {len(paths_to_try)} handshake paths for {self.base_url}")

        for path in paths_to_try:
            # First attempt: standard handshake
            try:
                logger.debug(f"Attempting handshake with {path}")
                async with self._session.get(
                    path,
                    params={
                        "type": "stb",
                        "action": "handshake",
                        "JsHttpRequest": "1-xml",
                    },
                    headers=self._get_headers(),
                ) as resp:
                    logger.debug(
                        f"Handshake response from {path}: status={resp.status}"
                    )
                    if resp.status == 200:
                        data = None
                        # Try json() first, but ContentTypeError can occur when server returns
                        # valid JSON with wrong Content-Type header
                        try:
                            data = await resp.json()
                        except aiohttp.ContentTypeError:
                            # Content-Type mismatch but body might still be valid JSON
                            raw_text = await resp.text()
                            cleaned = clean_json_response(raw_text)
                            try:
                                data = json.loads(cleaned)
                            except (json.JSONDecodeError, ValueError):
                                logger.warning(
                                    f"Handshake JSON parse failed from {path} after ContentTypeError fallback. Raw response (first 1000 chars): {raw_text[:1000]}"
                                )
                        except json.JSONDecodeError:
                            raw_text = await resp.text()
                            logger.warning(
                                f"Handshake JSON parse failed from {path}. Raw response (first 1000 chars): {raw_text[:1000]}"
                            )
                            cleaned = clean_json_response(raw_text)
                            try:
                                data = json.loads(cleaned)
                            except (json.JSONDecodeError, ValueError):
                                data = None
                        if data:
                            data = unwrap_response(data)
                            logger.debug(
                                f"Handshake response data after unwrap from {path}: type={type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'not a dict'}"
                            )
                            token = extract_token(data)
                            if token:
                                self._token = token
                                self._active_path = path
                                # Set token cookie with root path so it's sent for all paths
                                try:
                                    base_url_obj = URL(self.base_url)
                                    root_url = base_url_obj.with_path("/")
                                    self._session.cookie_jar.update_cookies(
                                        {"token": token}, root_url
                                    )
                                    logger.info(
                                        f"Set token cookie for domain {root_url} with path /"
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed to set token cookie: {e}")
                                logger.info(
                                    f"Handshake successful with {path}, token obtained (len={len(token)})"
                                )
                                return True
                            else:
                                logger.warning(
                                    f"Handshake response from {path} had data but extract_token returned None. Data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}. Data sample: {str(data)[:500] if data else 'None'}"
                                )
                        else:
                            logger.warning(
                                f"No data extracted from handshake response from {path} (data is None after JSON parse/clean)"
                            )
                    elif resp.status == 404:
                        logger.info(
                            f"Handshake endpoint {path} returned 404, trying fallback"
                        )
                        # Generate token+prehash and retry
                        token_gen = "".join(
                            random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=32)
                        )
                        prehash = hashlib.sha1(token_gen.encode()).hexdigest()
                        async with self._session.get(
                            path,
                            params={
                                "type": "stb",
                                "action": "handshake",
                                "token": token_gen,
                                "prehash": prehash,
                                "JsHttpRequest": "1-xml",
                            },
                            headers=self._get_headers(),
                        ) as retry_resp:
                            logger.info(
                                f"Fallback handshake response from {path}: status={retry_resp.status}"
                            )
                            if retry_resp.status == 200:
                                try:
                                    data = await retry_resp.json()
                                except (aiohttp.ContentTypeError, json.JSONDecodeError):
                                    raw_text = await retry_resp.text()
                                    logger.warning(
                                        f"Fallback handshake JSON parse failed from {path}. Raw response (first 1000 chars): {raw_text[:1000]}"
                                    )
                                    cleaned = clean_json_response(raw_text)
                                    try:
                                        data = json.loads(cleaned)
                                    except (json.JSONDecodeError, ValueError):
                                        data = None
                                if data:
                                    data = unwrap_response(data)
                                    logger.debug(
                                        f"Fallback handshake response data after unwrap from {path}: type={type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'not a dict'}"
                                    )
                                    token = extract_token(data)
                                    if token:
                                        self._token = token
                                        self._active_path = path
                                        try:
                                            base_url_obj = URL(self.base_url)
                                            root_url = base_url_obj.with_path("/")
                                            self._session.cookie_jar.update_cookies(
                                                {"token": token}, root_url
                                            )
                                            logger.info(
                                                f"Set token cookie for domain {root_url} with path /"
                                            )
                                        except Exception as e:
                                            logger.warning(
                                                f"Failed to set token cookie: {e}"
                                            )
                                        logger.info(
                                            f"Handshake successful with {path} (404 fallback), token obtained (len={len(token)})"
                                        )
                                        return True
                                    else:
                                        logger.warning(
                                            f"Fallback handshake response from {path} had data but extract_token returned None. Data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}. Data sample: {str(data)[:500] if data else 'None'}"
                                        )
                                else:
                                    logger.warning(
                                        f"Fallback handshake: no data extracted from {path} after JSON parse/clean"
                                    )
                            else:
                                logger.info(
                                    f"Fallback handshake failed for {path} with status {retry_resp.status}"
                                )
            except aiohttp.ClientError as e:
                logger.warning(f"Client error during handshake with {path}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Unexpected error during handshake with {path}: {e}")
                continue

        logger.error(
            f"Handshake failed for {self.base_url}: all {len(paths_to_try)} paths exhausted"
        )
        return False

    async def handshake(self) -> bool:
        """Public method to perform handshake (alias to _handshake)."""
        return await self._handshake()

    async def get_expiration_info(self) -> ExpirationInfo:
        """
        Retrieve the expiration information for the MAG STB account.

        Queries multiple endpoints (profile, account_info, billing) to find
        the most accurate expiry date. When expire_billing_date is '0000-00-00',
        the account has no billing expiry configured (unlimited access).

        Returns:
            ExpirationInfo with status, expiration date, and metadata
        """
        # Check cache first if enabled
        if self.enable_cache and self._cache is not None:
            cache_key = f"{self.base_url}:{self.mac}"
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                if time.time() - cached["timestamp"] < self.cache_ttl:
                    logger.debug(f"Cache hit for {cache_key}")
                    return cached["info"]

        try:
            await self._ensure_session()

            # First attempt: direct get_profile without handshake (MAC auth only)
            profile_full = await self._request_full(
                {"type": "stb", "action": "get_profile", "mac": self.mac}
            )

            if not profile_full or not profile_full.get("result"):
                handshake_success = await self._handshake()
                if not handshake_success:
                    return ExpirationInfo(
                        status="Invalid",
                        expiration=None,
                        error="Handshake failed - portal may not be accessible",
                    )
                profile_full = await self._request_full(
                    {"type": "stb", "action": "get_profile", "mac": self.mac}
                )

            if not profile_full:
                return ExpirationInfo(
                    status="Invalid",
                    expiration=None,
                    error="No profile data received - MAC may be invalid or expired",
                )

            profile = profile_full.get("result", {})
            js_profile = profile_full.get("js", {})

            # Gather data from multiple endpoints
            acc_info_full = await self._request_full(
                {"type": "stb", "action": "get_account_info"}
            )
            acc_info = acc_info_full.get("result", {}) if acc_info_full else {}
            js_account = acc_info_full.get("js", {}) if acc_info_full else {}

            do_auth_full = await self._request_full(
                {"type": "stb", "action": "do_auth"}
            )
            do_auth_result = do_auth_full.get("result", {}) if do_auth_full else {}
            js_do_auth = do_auth_full.get("js", {}) if do_auth_full else {}

            main_info_full = await self._request_full(
                {"type": "stb", "action": "get_main_info"}
            )
            main_info = main_info_full.get("result", {}) if main_info_full else {}
            js_main = main_info_full.get("js", {}) if main_info_full else {}

            # Try billing endpoints
            billing_full = await self._request_full(
                {"type": "billing", "action": "get_main_info"}
            )
            if not billing_full:
                billing_full = await self._request_full(
                    {"type": "billing", "action": "get_subscription_info"}
                )
            if not billing_full:
                billing_full = await self._request_full(
                    {"type": "billing", "action": "get_account_info"}
                )
            billing_info = billing_full.get("result", {}) if billing_full else {}
            js_billing = billing_full.get("js", {}) if billing_full else {}

            # Account info endpoint — portal admins inject expiry dates into
            # the 'phone' field as human-readable strings (e.g. "April 20, 2027").
            # This is the most reliable source for expiry on most portals.
            acc_info_main_full = await self._request_full(
                {"type": "account_info", "action": "get_main_info"}
            )
            acc_info_main = (
                acc_info_main_full.get("result", {}) if acc_info_main_full else {}
            )
            js_acc_info_main = (
                acc_info_main_full.get("js", {}) if acc_info_main_full else {}
            )

            # Detect Stalker portal
            is_stalker = False
            stalker_fields = None
            from app.services.stalker_detection import detect_stalker_portal

            if getattr(settings, "stalker_detection_enabled", True):
                profile_data = profile if isinstance(profile, dict) else {}
                acc_info_data = acc_info if isinstance(acc_info, dict) else {}
                is_stalker, stalker_fields = detect_stalker_portal(
                    profile_data, acc_info_data
                )
                if is_stalker:
                    logger.debug(f"Stalker portal detected. Fields: {stalker_fields}")

            # Collect all data sources - check js objects first (where expiry often lives)
            # then result objects. account_info_main (phone field) is checked early
            # since portal admins commonly inject expiry dates there.
            data_sources = []
            if isinstance(js_acc_info_main, dict):
                data_sources.append((js_acc_info_main, "account_info_main_js"))
            if isinstance(js_billing, dict):
                data_sources.append((js_billing, "billing_js"))
            if isinstance(js_do_auth, dict):
                data_sources.append((js_do_auth, "do_auth_js"))
            if isinstance(js_profile, dict):
                data_sources.append((js_profile, "profile_js"))
            if isinstance(js_account, dict):
                data_sources.append((js_account, "account_js"))
            if isinstance(js_main, dict):
                data_sources.append((js_main, "main_js"))
            if isinstance(acc_info_main, dict):
                data_sources.append((acc_info_main, "account_info_main"))
            if isinstance(billing_info, dict):
                data_sources.append((billing_info, "billing"))
            if isinstance(do_auth_result, dict):
                data_sources.append((do_auth_result, "do_auth"))
            if isinstance(profile, dict):
                data_sources.append((profile, "profile"))
            if isinstance(acc_info, dict):
                data_sources.append((acc_info, "account_info"))
            if isinstance(main_info, dict):
                data_sources.append((main_info, "main_info"))

            # Try each source for expiry date
            expiration = None
            source = None
            for data, source_name in data_sources:
                exp_val, exp_source = detect_expiry_with_source(data, source_name)
                if exp_val:
                    expiration = exp_val
                    source = exp_source
                    break

            # When no expiry found, check account status
            if not expiration:
                status_val = profile.get("status")
                blocked_val = profile.get("blocked")
                is_active = status_val == 1 or status_val == "1"
                is_not_blocked = blocked_val == "0" or blocked_val == 0

                if is_active and is_not_blocked:
                    expiration = "Unlimited"
                    status = "Active"
                else:
                    expiration = "Unlimited"
                    status = "Active"

            # Determine status based on expiration
            if expiration == "Unlimited":
                status = "Active"
            else:
                try:
                    exp_date = parse_expiry_date(
                        expiration, timezone=settings.date_parsing_timezone
                    )
                    if exp_date:
                        now = (
                            datetime.now(exp_date.tzinfo)
                            if exp_date.tzinfo
                            else datetime.now()
                        )
                        status = "Active" if exp_date >= now else "Expired"
                    else:
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m"):
                            try:
                                exp_date = datetime.strptime(expiration.split()[0], fmt)
                                now = datetime.now()
                                status = "Active" if exp_date >= now else "Expired"
                                break
                            except (ValueError, AttributeError):
                                continue
                        else:
                            status = "Active"
                except Exception as e:
                    logger.debug(f"Date parsing error: {e}")
                    status = "Active"

            result = ExpirationInfo(
                status=status,
                expiration=expiration,
                error=None,
                is_stalker=is_stalker,
                stalker_fields=stalker_fields,
                source_endpoint=source.endpoint if source else None,
                source_field=source.field_name if source else None,
            )

            # Cache successful results
            if self.enable_cache and self._cache is not None and result.error is None:
                cache_key = f"{self.base_url}:{self.mac}"
                self._cache[cache_key] = {"timestamp": time.time(), "info": result}

            logger.info(
                f"Portal check complete: {self.base_url} - {status} (expiry: {expiration})",
                extra={
                    "portal_url": self.base_url,
                    "mac": self.mac,
                    "expiration": expiration,
                    "status": status,
                    "source": f"{source.endpoint}.{source.field_name}"
                    if source
                    else None,
                    "is_stalker": is_stalker,
                },
            )

            return result

        except asyncio.TimeoutError:
            return ExpirationInfo(
                status="Invalid", expiration=None, error="Request timeout"
            )
        except aiohttp.ClientError as e:
            return ExpirationInfo(
                status="Invalid", expiration=None, error=f"HTTP client error: {str(e)}"
            )
        except Exception as e:
            logger.exception("Unexpected error during expiration check")
            return ExpirationInfo(
                status="Invalid", expiration=None, error=f"Unexpected error: {str(e)}"
            )

    async def get_profile(self) -> Optional[Dict[str, Any]]:
        """Get STB profile from the portal."""
        return await self._request(
            {
                "type": "stb",
                "action": "get_profile",
                "stb_type": "MAG250",
                "sn": "0000000000000",
                "ver": "ImageDescription: 0.2.18-r11-pub-254; Link: WiFi",
                "hd": "1",
                "num_bouquets": "7",
                "num_sub_bouquets": "0",
                "itv_bouquets_top": "1",
            }
        )

    async def create_link(
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
        # URL-encode the cmd parameter to handle spaces and special characters
        # Stalker WAF requires properly encoded cmd values (e.g., "ffrt http://..." becomes "ffrt%20http%3A%2F%2F...")
        encoded_cmd = quote(cmd, safe="")
        params = {
            "type": "itv",
            "action": "create_link",
            "cmd": encoded_cmd,
            "series": series,
            "forced_storage": forced_storage,
            "disable_ad": disable_ad,
            "download": download,
            "force_ch_link_check": force_ch_link_check,
        }
        params.update(kwargs)
        return await self._request(params)

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "StalkerClient":
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()


async def check_single_portal(portal_url: str, mac_address: str) -> Dict[str, Any]:
    """
    Convenience function to check a single portal and return result as dictionary.

    Args:
        portal_url: The portal URL
        mac_address: The MAC address

    Returns:
        Dictionary with keys: url, mac, status, expiration, error
    """
    async with StalkerClient(portal_url, mac_address) as client:
        info = await client.get_expiration_info()
        return {
            "url": portal_url,
            "mac": mac_address,
            "status": info.status,
            "expiration": info.expiration,
            "error": info.error,
        }



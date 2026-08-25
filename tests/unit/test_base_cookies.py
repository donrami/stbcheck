"""
Unit tests for base cookies initialization in Stalker clients.

Tests that mac, stb_lang, and timezone cookies are properly set in the session.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.stalker_async import StalkerClient


class TestAsyncBaseCookies:
    """Tests for StalkerClient base cookies."""

    @pytest.mark.asyncio
    async def test_async_session_has_base_cookies(self):
        """Test that StalkerClient session contains base cookies after _ensure_session."""
        client = StalkerClient("http://example.com", "00:11:22:33:44:55")
        await client._ensure_session()
        # The cookie_jar is a CookieJar, we can inspect
        cookies = client._session.cookie_jar
        # Find cookies by name
        mac_cookie = None
        lang_cookie = None
        tz_cookie = None
        for cookie in cookies:
            if cookie.key == "mac":
                mac_cookie = cookie
            elif cookie.key == "stb_lang":
                lang_cookie = cookie
            elif cookie.key == "timezone":
                tz_cookie = cookie
        assert mac_cookie is not None, "mac cookie not found"
        assert mac_cookie.value == "00:11:22:33:44:55"
        assert lang_cookie is not None, "stb_lang cookie not found"
        assert lang_cookie.value == "en"
        assert tz_cookie is not None, "timezone cookie not found"
        assert tz_cookie.value == "Europe/London"
        await client.close()

    @pytest.mark.asyncio
    async def test_async_base_cookies_normalized_mac(self):
        """Test that MAC is normalized in async client cookies."""
        client = StalkerClient("http://example.com", "aa:bb:cc:dd:ee:ff")
        await client._ensure_session()
        mac_cookie = next(
            (c for c in client._session.cookie_jar if c.key == "mac"), None
        )
        assert mac_cookie is not None
        assert mac_cookie.value == "AA:BB:CC:DD:EE:FF"
        await client.close()

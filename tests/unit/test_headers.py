"""
Unit tests for HTTP headers in Stalker clients.

Tests that _get_headers (sync) and _get_headers (async) contain required headers
and exclude Cookie header.
"""

import pytest
from unittest.mock import patch

from app.services.stalker_async import StalkerClient
from app.services.stalker import StalkerPortal
from app.services.base import MAG200_USER_AGENT, MAG250_XUA


class TestAsyncHeaders:
    """Tests for StalkerClient._get_headers."""

    @pytest.mark.asyncio
    async def test_async_headers_include_required_fields(self):
        """Test that async _get_headers includes Referer, Accept-Language, etc."""
        client = StalkerClient("http://example.com", "00:11:22:33:44:55")
        headers = client._get_headers()
        assert "User-Agent" in headers
        assert headers["User-Agent"] == MAG200_USER_AGENT
        assert "Accept" in headers
        assert headers["Accept"] == "*/*"
        assert "Accept-Charset" in headers
        assert "Accept-Language" in headers
        assert headers["Accept-Language"] == "en-US,en;q=0.5"
        assert "X-User-Agent" in headers
        assert headers["X-User-Agent"] == MAG250_XUA
        assert "Referer" in headers
        assert headers["Referer"] == "http://example.com/"
        assert "Connection" in headers
        assert headers["Connection"] == "keep-alive"
        # No manual Cookie
        assert "Cookie" not in headers

    @pytest.mark.asyncio
    async def test_async_headers_referer_with_subpath(self):
        """Test Referer includes subpath correctly."""
        client = StalkerClient(
            "http://example.com/stalker_portal/c", "00:11:22:33:44:55"
        )
        headers = client._get_headers()
        assert headers["Referer"] == "http://example.com/stalker_portal/c/"


class TestSyncHeaders:
    """Tests for StalkerPortal headers."""

    def test_sync_headers_include_required_fields(self):
        """Test that sync client headers include required fields."""
        portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
        headers = portal.headers
        assert "User-Agent" in headers
        assert headers["User-Agent"] == MAG200_USER_AGENT
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert headers["Accept-Language"] == "en-US,en;q=0.5"
        assert "X-User-Agent" in headers
        assert headers["X-User-Agent"] == MAG250_XUA
        assert "Referer" in headers
        assert headers["Referer"] == "http://example.com/"
        assert "Connection" in headers
        # No Cookie
        assert "Cookie" not in headers

    def test_sync_headers_referer_with_subpath(self):
        """Test Referer includes subpath correctly."""
        portal = StalkerPortal("http://example.com/c", "00:11:22:33:44:55")
        assert portal.headers["Referer"] == "http://example.com/c/"

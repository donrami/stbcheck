"""
Unit tests for handshake 404 fallback mechanism.

Tests that when the standard handshake endpoint returns 404, the client
generates a random token and its SHA1 prehash, then retries successfully.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.services.stalker_async import StalkerClient
from app.services.stalker import StalkerPortal
from app.services.base import extract_token


def make_async_response(status, json_data):
    """Create a mock response that can be used in async with."""
    resp = MagicMock()
    resp.status = status
    if json_data is not None:

        async def json_func():
            return json_data

        resp.json = json_func
    # Make it an async context manager
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


class TestAsyncHandshake404Fallback:
    """Tests for async client handshake 404 fallback."""

    @pytest.mark.asyncio
    async def test_handshake_404_fallback_success(self):
        """Test that 404 on first request triggers token+prehash retry that succeeds."""
        with patch(
            "app.services.stalker_async.aiohttp.ClientSession"
        ) as mock_session_class:
            # Mock session with cookie_jar
            mock_session = MagicMock()
            mock_session.cookie_jar = MagicMock()
            mock_session_class.return_value = mock_session

            # Responses: first attempt 404, fallback 200 with token
            mock_resp_404 = make_async_response(404, None)
            mock_resp_200 = make_async_response(
                200, {"js": {"token": "generated_token"}}
            )

            # get method returns response directly (not a coroutine) for simplicity
            mock_session.get = MagicMock(side_effect=[mock_resp_404, mock_resp_200])

            client = StalkerClient("http://example.com", "00:11:22:33:44:55")
            result = await client._handshake()

            assert result is True
            assert client._token == "generated_token"
            assert client._active_path == "http://example.com/server/load.php"
            assert mock_session.get.call_count == 2

    @pytest.mark.asyncio
    async def test_handshake_404_fallback_updates_cookie_jar(self):
        """Test that token is added to cookie jar after fallback success."""
        with patch(
            "app.services.stalker_async.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.cookie_jar = MagicMock()
            mock_session_class.return_value = mock_session

            mock_resp_404 = make_async_response(404, None)
            mock_resp_200 = make_async_response(
                200, {"js": {"token": "fallback_token"}}
            )

            mock_session.get = MagicMock(side_effect=[mock_resp_404, mock_resp_200])

            client = StalkerClient("http://example.com", "00:11:22:33:44:55")
            result = await client._handshake()

            assert result is True
            assert client._token == "fallback_token"
            # Verify cookie_jar.update_cookies called at least once
            assert mock_session.cookie_jar.update_cookies.called


class TestSyncHandshake404Fallback:
    """Tests for sync client handshake 404 fallback."""

    def test_sync_handshake_404_fallback_success(self):
        """Test sync: 404 triggers token+prehash retry."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_resp_404 = MagicMock()
            mock_resp_404.status_code = 404

            mock_resp_200 = MagicMock()
            mock_resp_200.status_code = 200
            mock_resp_200.json.return_value = {"js": {"token": "sync_token"}}

            mock_session.get.side_effect = [mock_resp_404, mock_resp_200]

            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            result = portal.handshake()

            assert result is True
            assert portal.token == "sync_token"
            assert portal.active_path == "http://example.com/server/load.php"

    def test_sync_handshake_404_fallback_multiple_paths(self):
        """Test sync: 404 on first path, fallback fails, second path succeeds."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_resp_404 = MagicMock()
            mock_resp_404.status_code = 404

            mock_resp_success = MagicMock()
            mock_resp_success.status_code = 200
            mock_resp_success.json.return_value = {"js": {"token": "token_path2"}}

            mock_session.get.side_effect = [
                mock_resp_404,  # path1 first attempt
                mock_resp_404,  # path1 fallback
                mock_resp_success,  # path2 first attempt
            ]

            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            result = portal.handshake()

            assert result is True
            assert portal.token == "token_path2"
            assert portal.active_path == "http://example.com/portal.php"
            assert mock_session.get.call_count == 3

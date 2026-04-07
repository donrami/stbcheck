"""
Unit tests for automatic token refresh on 401/403 responses.

Tests that _request() detects 401/403, performs handshake, clears token,
and retries the original request.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.services.stalker_async import StalkerClient
from app.services.stalker import StalkerPortal


def make_async_response(status, json_data):
    """Create a mock response that can be used in async with."""
    resp = MagicMock()
    resp.status = status
    if json_data is not None:

        async def json_func():
            return json_data

        resp.json = json_func
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


class TestAsyncTokenRefresh:
    """Tests for async client automatic token refresh."""

    @pytest.mark.asyncio
    async def test_request_401_triggers_handshake_and_retry(self):
        """Test that 401 response causes handshake and a retry."""
        with patch(
            "app.services.stalker_async.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.cookie_jar = MagicMock()
            mock_session_class.return_value = mock_session

            base_url = "http://example.com"
            client = StalkerClient(base_url, "00:11:22:33:44:55")
            client._active_path = f"{base_url}/server/load.php"

            # Responses: initial 401, handshake 200, retry 200 with data
            mock_resp_401 = make_async_response(401, None)
            mock_resp_handshake = make_async_response(
                200, {"js": {"token": "new_token"}}
            )
            mock_resp_retry = make_async_response(
                200, {"js": {"result": {"data": "value"}}}
            )

            # get returns response directly (not coroutine) to simplify
            mock_session.get = MagicMock(
                side_effect=[mock_resp_401, mock_resp_handshake, mock_resp_retry]
            )

            result = await client._request({"type": "stb", "action": "get_profile"})

            assert result == {"data": "value"}
            assert client._token == "new_token"
            assert mock_session.get.call_count == 3

    @pytest.mark.asyncio
    async def test_request_403_similar_behavior(self):
        """Test that 403 also triggers refresh."""
        with patch(
            "app.services.stalker_async.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.cookie_jar = MagicMock()
            mock_session_class.return_value = mock_session

            base_url = "http://example.com"
            client = StalkerClient(base_url, "00:11:22:33:44:55")
            client._active_path = f"{base_url}/server/load.php"

            mock_resp_403 = make_async_response(403, None)
            mock_resp_handshake = make_async_response(
                200, {"js": {"token": "token_after_403"}}
            )
            mock_resp_retry = make_async_response(200, {"js": {"result": "ok"}})

            mock_session.get = MagicMock(
                side_effect=[mock_resp_403, mock_resp_handshake, mock_resp_retry]
            )

            result = await client._request({"type": "stb", "action": "get_profile"})
            # After unwrap: returns {"result": "ok"} because result is not dict/list
            assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_token_cleared_before_handshake(self):
        """Test that token is cleared from state and cookie jar before handshake."""
        with patch(
            "app.services.stalker_async.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.cookie_jar = MagicMock()
            mock_session_class.return_value = mock_session

            base_url = "http://example.com"
            client = StalkerClient(base_url, "00:11:22:33:44:55")
            client._active_path = f"{base_url}/server/load.php"
            client._token = "old_token"

            mock_resp_401 = make_async_response(401, None)
            mock_resp_handshake = make_async_response(
                200, {"js": {"token": "refreshed"}}
            )
            mock_resp_retry = make_async_response(200, {"js": {"result": "success"}})

            mock_session.get = MagicMock(
                side_effect=[mock_resp_401, mock_resp_handshake, mock_resp_retry]
            )

            result = await client._request({"type": "stb", "action": "get_profile"})

            assert result == {"result": "success"}
            assert client._token == "refreshed"
            # The update_cookies should have been called at least twice: clear and set
            assert mock_session.cookie_jar.update_cookies.call_count >= 2


class TestSyncTokenRefresh:
    """Tests for sync client automatic token refresh."""

    def test_sync_request_401_triggers_handshake_and_retry(self):
        """Test sync: 401 causes handshake and retry."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            base_url = "http://example.com"
            portal = StalkerPortal(base_url, "00:11:22:33:44:55")
            portal.active_path = f"{base_url}/server/load.php"

            mock_resp_401 = MagicMock()
            mock_resp_401.status_code = 401

            mock_resp_handshake = MagicMock()
            mock_resp_handshake.status_code = 200
            mock_resp_handshake.json.return_value = {"js": {"token": "new_sync_token"}}

            mock_resp_retry = MagicMock()
            mock_resp_retry.status_code = 200
            mock_resp_retry.json.return_value = {"js": {"result": {"data": "sync_val"}}}

            mock_session.get.side_effect = [
                mock_resp_401,
                mock_resp_handshake,
                mock_resp_retry,
            ]

            result = portal._request({"type": "stb", "action": "get_profile"})

            assert result == {"data": "sync_val"}
            assert portal.token == "new_sync_token"
            assert mock_session.get.call_count == 3

    def test_sync_request_403_behaves_similarly(self):
        """Test sync: 403 also triggers refresh."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            base_url = "http://example.com"
            portal = StalkerPortal(base_url, "00:11:22:33:44:55")
            portal.active_path = f"{base_url}/server/load.php"

            mock_resp_403 = MagicMock()
            mock_resp_403.status_code = 403

            mock_resp_handshake = MagicMock()
            mock_resp_handshake.status_code = 200
            mock_resp_handshake.json.return_value = {"js": {"token": "sync_token_403"}}

            mock_resp_retry = MagicMock()
            mock_resp_retry.status_code = 200
            mock_resp_retry.json.return_value = {"js": {"result": "ok"}}

            mock_session.get.side_effect = [
                mock_resp_403,
                mock_resp_handshake,
                mock_resp_retry,
            ]

            result = portal._request({"type": "stb", "action": "get_profile"})
            # After unwrap: data becomes {"result": "ok"} because result is not dict/list
            assert result == {"result": "ok"}

    def test_sync_token_cleared_before_handshake(self):
        """Test that token is cleared from state and cookie before handshake."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            base_url = "http://example.com"
            portal = StalkerPortal(base_url, "00:11:22:33:44:55")
            portal.active_path = f"{base_url}/server/load.php"
            portal.token = "old_token"

            mock_resp_401 = MagicMock()
            mock_resp_401.status_code = 401
            mock_resp_handshake = MagicMock()
            mock_resp_handshake.status_code = 200
            mock_resp_handshake.json.return_value = {"js": {"token": "new_token"}}
            mock_resp_retry = MagicMock()
            mock_resp_retry.status_code = 200
            mock_resp_retry.json.return_value = {"js": {"result": "ok"}}

            mock_session.get.side_effect = [
                mock_resp_401,
                mock_resp_handshake,
                mock_resp_retry,
            ]

            result = portal._request({"type": "stb", "action": "get_profile"})

            assert result == {"result": "ok"}
            assert portal.token == "new_token"
            # The session cookies should have been updated to clear token
            assert mock_session.cookies.update.called

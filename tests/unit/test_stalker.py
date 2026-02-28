"""
Unit tests for app/services/stalker.py

Tests for StalkerPortal class methods using mocked HTTP requests:
- handshake() success/failure scenarios
- _clean_json() various formats
- _request() error handling
"""

import json
import pytest
from unittest.mock import MagicMock, patch, Mock

from app.services.stalker import StalkerPortal, PORTAL_HEADERS


class TestStalkerPortalInit:
    """Tests for StalkerPortal initialization."""

    def test_init_stores_url_and_mac(self):
        """Test that URL and MAC are stored correctly."""
        portal = StalkerPortal("http://example.com/stalker_portal/c/", "00:11:22:33:44:55")
        
        assert portal.base_url == "http://example.com/stalker_portal/c"
        assert portal.mac == "00:11:22:33:44:55"

    def test_init_normalizes_mac_to_uppercase(self):
        """Test that MAC is normalized to uppercase."""
        portal = StalkerPortal("http://example.com", "aa:bb:cc:dd:ee:ff")
        
        assert portal.mac == "AA:BB:CC:DD:EE:FF"

    def test_init_removes_trailing_slash(self):
        """Test that trailing slash is removed from URL."""
        portal = StalkerPortal("http://example.com/", "00:11:22:33:44:55")
        
        assert portal.base_url == "http://example.com"

    def test_init_creates_session(self):
        """Test that a session is created with correct headers."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            
            mock_session_class.assert_called_once()
            mock_session.headers.update.assert_called_once_with(PORTAL_HEADERS)

    def test_init_sets_headers(self):
        """Test that portal headers are set correctly."""
        portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
        
        assert "X-User-Agent" in portal.headers
        assert "Cookie" in portal.headers
        assert "Accept" in portal.headers
        assert portal.headers["Cookie"] == "mac=00:11:22:33:44:55"


class TestCleanJson:
    """Tests for _clean_json method."""

    def test_clean_json_secure_wrapper(self):
        """Test cleaning /*-secure- wrapper."""
        portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
        
        raw = '/*-secure-\n{"token":"abc123"}\n*/'
        result = portal._clean_json(raw)
        
        # The implementation strips the wrapper but keeps internal whitespace
        assert '"token":"abc123"' in result

    def test_clean_json_on_success_wrapper(self):
        """Test cleaning on_success() wrapper."""
        portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
        
        raw = 'on_success(this, {"token":"abc123"})'
        result = portal._clean_json(raw)
        
        assert result == '{"token":"abc123"}'

    def test_clean_json_array_in_on_success(self):
        """Test cleaning array in on_success() wrapper."""
        portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
        
        raw = 'on_success(this, [{"id":"1"},{"id":"2"}])'
        result = portal._clean_json(raw)
        
        assert result == '[{"id":"1"},{"id":"2"}]'

    def test_clean_json_no_wrapper(self):
        """Test that plain JSON is returned unchanged."""
        portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
        
        raw = '{"token":"abc123"}'
        result = portal._clean_json(raw)
        
        assert result == '{"token":"abc123"}'

    def test_clean_json_empty_string(self):
        """Test cleaning empty string."""
        portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
        
        result = portal._clean_json("")
        assert result == ""

    def test_clean_json_none(self):
        """Test cleaning None."""
        portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
        
        result = portal._clean_json(None)
        assert result == ""

    def test_clean_json_whitespace(self):
        """Test cleaning whitespace-only string."""
        portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
        
        result = portal._clean_json("   ")
        assert result == ""


class TestRequest:
    """Tests for _request method."""

    def test_request_success_json_response(self):
        """Test successful request with JSON response."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": {"token": "abc123"}}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal._request({"type": "stb", "action": "handshake"})
            
            assert result == {"token": "abc123"}

    def test_request_returns_404(self):
        """Test request returns 404 status."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal._request({"type": "stb", "action": "handshake"})
            
            assert result == 404

    def test_request_no_active_path(self):
        """Test request without active path returns None."""
        portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
        portal.active_path = None
        
        result = portal._request({"type": "stb", "action": "handshake"})
        
        assert result is None

    def test_request_json_decode_error_with_clean(self):
        """Test handling JSON decode error with cleanable response."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = json.JSONDecodeError("test", "", 0)
            mock_response.text = '/*-secure-\n{"token":"abc123"}\n*/'
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal._request({"type": "stb", "action": "handshake"})
            
            assert result == {"token": "abc123"}

    def test_request_json_decode_error_uncleanable(self):
        """Test handling JSON decode error with uncleanable response."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = json.JSONDecodeError("test", "", 0)
            mock_response.text = "not valid json"
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal._request({"type": "stb", "action": "handshake"})
            
            assert result is None

    def test_request_exception_handling(self):
        """Test exception handling in request."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            mock_session.get.side_effect = Exception("Network error")
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal._request({"type": "stb", "action": "handshake"})
            
            assert result is None

    def test_request_adds_jshttprequest_param(self):
        """Test that JsHttpRequest param is added."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": {"token": "abc123"}}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            portal._request({"type": "stb", "action": "handshake"})
            
            call_args = mock_session.get.call_args
            params = call_args[1]["params"]
            assert "JsHttpRequest" in params
            assert params["JsHttpRequest"] == "1-xml"

    def test_request_adds_authorization_header(self):
        """Test that Authorization header is added when token exists."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": {"token": "abc123"}}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            portal.token = "existing_token"
            
            portal._request({"type": "stb", "action": "get_profile"})
            
            call_args = mock_session.get.call_args
            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer existing_token"

    def test_request_extracts_result_field(self):
        """Test that result field is extracted from response."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": {"result": {"data": "value"}}}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal._request({"type": "stb", "action": "handshake"})
            
            assert result == {"data": "value"}


class TestHandshake:
    """Tests for handshake method."""

    def test_handshake_success_first_path(self):
        """Test successful handshake on first path."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": {"token": "abc123"}}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            
            result = portal.handshake()
            
            assert result is True
            assert portal.token == "abc123"
            assert portal.active_path == "http://example.com/server/load.php"

    def test_handshake_success_second_path(self):
        """Test successful handshake on second path after 404 on first."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            # First call returns 404, second returns success
            mock_response_404 = MagicMock()
            mock_response_404.status_code = 404
            
            mock_response_success = MagicMock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {"js": {"token": "abc123"}}
            
            mock_session.get.side_effect = [mock_response_404, mock_response_success]
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            
            result = portal.handshake()
            
            assert result is True
            assert portal.token == "abc123"
            assert portal.active_path == "http://example.com/portal.php"

    def test_handshake_all_paths_fail(self):
        """Test handshake failure when all paths fail."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            
            result = portal.handshake()
            
            assert result is False
            assert portal.token is None
            assert portal.active_path is None

    def test_handshake_no_token_in_response(self):
        """Test handshake when response doesn't contain token."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": {"other_field": "value"}}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            
            result = portal.handshake()
            
            assert result is False
            assert portal.token is None

    def test_handshake_tries_all_three_paths(self):
        """Test that handshake tries all three paths."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response_404 = MagicMock()
            mock_response_404.status_code = 404
            
            mock_response_success = MagicMock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {"js": {"token": "abc123"}}
            
            # First two 404, third succeeds
            mock_session.get.side_effect = [
                mock_response_404,  # /server/load.php
                mock_response_404,  # /portal.php
                mock_response_success  # base_url
            ]
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            
            result = portal.handshake()
            
            assert result is True
            assert mock_session.get.call_count == 3
            assert portal.active_path == "http://example.com"


class TestStalkerPortalMethods:
    """Tests for other StalkerPortal methods."""

    def test_get_channels(self):
        """Test get_channels method."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": [{"id": "1", "name": "Channel 1"}]}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal.get_channels()
            
            assert result == [{"id": "1", "name": "Channel 1"}]

    def test_get_genres(self):
        """Test get_genres method."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": [{"id": "1", "title": "Sports"}]}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal.get_genres()
            
            assert result == [{"id": "1", "title": "Sports"}]

    def test_create_link(self):
        """Test create_link method."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": {"cmd": "http://stream.example.com/video.ts"}}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal.create_link("ffmpeg http://cmd")
            
            assert result == {"cmd": "http://stream.example.com/video.ts"}

    def test_get_profile(self):
        """Test get_profile method."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": {"id": "12345", "login": "user"}}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal.get_profile()
            
            assert result == {"id": "12345", "login": "user"}

    def test_get_account_info(self):
        """Test get_account_info method."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"js": {"login": "user", "status": "Active"}}
            mock_session.get.return_value = mock_response
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal.get_account_info()
            
            assert result == {"login": "user", "status": "Active"}

    def test_get_account_info_fallback_to_main_info(self):
        """Test get_account_info falls back to get_main_info on 404."""
        with patch("app.services.stalker.requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            mock_response_404 = MagicMock()
            mock_response_404.status_code = 404
            
            mock_response_success = MagicMock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {"js": {"login": "user"}}
            
            mock_session.get.side_effect = [mock_response_404, mock_response_success]
            
            portal = StalkerPortal("http://example.com", "00:11:22:33:44:55")
            portal.active_path = "http://example.com/server/load.php"
            
            result = portal.get_account_info()
            
            assert result == {"login": "user"}

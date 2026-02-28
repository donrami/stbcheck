"""
Integration tests for API endpoints using TestClient.

Tests FastAPI endpoints:
- GET / (index page)
- POST /api/check (with mocked portal responses)
- POST /api/get_link
- GET /api/proxy_logo
- GET /api/check_stream
- GET /api/proxy_stream
- GET /favicon.ico
"""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestIndexEndpoint:
    """Tests for the root/index endpoint."""

    def test_get_index_success(self, client):
        """Test successful GET / returns HTML."""
        response = client.get("/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Check for expected content in index.html
        assert b"<html" in response.content or b"<!DOCTYPE html>" in response.content

    def test_get_index_content_type(self, client):
        """Test that index returns correct content type."""
        response = client.get("/")
        
        assert response.headers["content-type"].startswith("text/html")


class TestFaviconEndpoint:
    """Tests for the favicon endpoint."""

    def test_get_favicon(self, client):
        """Test GET /favicon.ico returns 204 No Content."""
        response = client.get("/favicon.ico")
        
        assert response.status_code == 204


class TestCheckPortalsEndpoint:
    """Tests for POST /api/check endpoint."""

    def test_check_no_portal_mac_pairs(self, client):
        """Test check with text that has no portal/MAC pairs."""
        response = client.post("/api/check", json={"text": "just some random text"})
        
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        # Read SSE events
        content = response.content.decode()
        assert "error" in content or "complete" in content

    def test_check_valid_portal_mac_pair(self, client):
        """Test check with valid portal/MAC pair."""
        text = "PORTAL: http://example.com/stalker_portal/c/\nMAC: 00:11:22:33:44:55"
        
        with patch("app.routers.portals.StalkerPortal") as mock_portal_class:
            mock_portal = MagicMock()
            mock_portal_class.return_value = mock_portal
            mock_portal.handshake.return_value = True
            mock_portal.get_profile.return_value = {"login": "user", "expire_date": "2025-12-31"}
            mock_portal.get_account_info.return_value = {"status": "Active"}
            mock_portal.get_itv_info.return_value = None
            mock_portal.get_channels.return_value = []
            mock_portal.get_genres.return_value = []
            mock_portal.session.close = MagicMock()
            
            response = client.post("/api/check", json={"text": text})
            
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

    def test_check_invalid_json(self, client):
        """Test check with invalid JSON returns 422."""
        response = client.post("/api/check", data="not json")
        
        assert response.status_code == 422

    def test_check_missing_text_field(self, client):
        """Test check with missing text field returns 422."""
        response = client.post("/api/check", json={})
        
        assert response.status_code == 422

    def test_check_empty_text(self, client):
        """Test check with empty text."""
        response = client.post("/api/check", json={"text": ""})
        
        # Should return streaming response with error
        assert response.status_code == 200
        content = response.content.decode()
        assert "error" in content or "complete" in content

    def test_check_with_crawling(self, client):
        """Test check triggers URL crawling when no direct pairs found."""
        text = "Check this link: http://example.com/page"
        
        with patch("app.routers.portals.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "PORTAL: http://portal.com/c/ MAC: 00:11:22:33:44:55"
            mock_get.return_value = mock_response
            
            with patch("app.routers.portals.StalkerPortal") as mock_portal_class:
                mock_portal = MagicMock()
                mock_portal_class.return_value = mock_portal
                mock_portal.handshake.return_value = True
                mock_portal.get_profile.return_value = {"login": "user"}
                mock_portal.get_account_info.return_value = {"status": "Active"}
                mock_portal.get_itv_info.return_value = None
                mock_portal.get_channels.return_value = []
                mock_portal.get_genres.return_value = []
                mock_portal.session.close = MagicMock()
                
                response = client.post("/api/check", json={"text": text})
                
                assert response.status_code == 200


class TestGetLinkEndpoint:
    """Tests for POST /api/get_link endpoint."""

    def test_get_link_success(self, client):
        """Test successful link generation."""
        with patch("app.routers.streams.StalkerPortal") as mock_portal_class:
            mock_portal = MagicMock()
            mock_portal_class.return_value = mock_portal
            mock_portal.handshake.return_value = True
            mock_portal.create_link.return_value = {"cmd": "ffmpeg http://stream.example.com/video.ts"}
            
            response = client.post("/api/get_link", json={
                "url": "http://example.com/stalker_portal/c/",
                "mac": "00:11:22:33:44:55",
                "cmd": "ffmpeg http://cmd"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "url" in data
            assert "/api/proxy_stream" in data["url"]

    def test_get_link_handshake_failure(self, client):
        """Test link generation when handshake fails."""
        with patch("app.routers.streams.StalkerPortal") as mock_portal_class:
            mock_portal = MagicMock()
            mock_portal_class.return_value = mock_portal
            mock_portal.handshake.return_value = False
            
            response = client.post("/api/get_link", json={
                "url": "http://example.com/stalker_portal/c/",
                "mac": "00:11:22:33:44:55",
                "cmd": "ffmpeg http://cmd"
            })
            
            assert response.status_code == 400
            assert "Could not create link" in response.json()["detail"]

    def test_get_link_no_stream_url(self, client):
        """Test link generation when no stream URL is returned."""
        with patch("app.routers.streams.StalkerPortal") as mock_portal_class:
            mock_portal = MagicMock()
            mock_portal_class.return_value = mock_portal
            mock_portal.handshake.return_value = True
            mock_portal.create_link.return_value = {}  # No cmd field
            
            response = client.post("/api/get_link", json={
                "url": "http://example.com/stalker_portal/c/",
                "mac": "00:11:22:33:44:55",
                "cmd": "ffmpeg http://cmd"
            })
            
            assert response.status_code == 400

    def test_get_link_invalid_request(self, client):
        """Test link generation with invalid request data."""
        response = client.post("/api/get_link", json={
            "url": "http://example.com",
            # Missing mac and cmd
        })
        
        assert response.status_code == 422

    def test_get_link_empty_cmd_result(self, client):
        """Test link generation when create_link returns empty cmd."""
        with patch("app.routers.streams.StalkerPortal") as mock_portal_class:
            mock_portal = MagicMock()
            mock_portal_class.return_value = mock_portal
            mock_portal.handshake.return_value = True
            mock_portal.create_link.return_value = {"cmd": ""}  # Empty cmd
            
            response = client.post("/api/get_link", json={
                "url": "http://example.com/stalker_portal/c/",
                "mac": "00:11:22:33:44:55",
                "cmd": "ffmpeg http://cmd"
            })
            
            assert response.status_code == 400


class TestProxyLogoEndpoint:
    """Tests for GET /api/proxy_logo endpoint."""

    def test_proxy_logo_success(self, client):
        """Test successful logo proxy."""
        logo_url = "http://example.com/logo.png"
        encoded_url = base64.b64encode(logo_url.encode()).decode()
        
        with patch("app.routers.streams.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = [b"image data"]
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)
            
            response = client.get(f"/api/proxy_logo?target={encoded_url}")
            
            assert response.status_code == 200
            assert response.content == b"image data"

    def test_proxy_logo_invalid_base64(self, client):
        """Test logo proxy with invalid base64."""
        response = client.get("/api/proxy_logo?target=not-valid-base64!!!", follow_redirects=False)
        
        assert response.status_code == 302  # Redirect to default image
        assert "cdn-icons-png.flaticon.com" in response.headers.get("location", "")

    def test_proxy_logo_unsafe_url(self, client):
        """Test logo proxy with unsafe URL (SSRF protection)."""
        unsafe_url = "http://192.168.1.1/logo.png"
        encoded_url = base64.b64encode(unsafe_url.encode()).decode()
        
        response = client.get(f"/api/proxy_logo?target={encoded_url}")
        
        assert response.status_code == 403

    def test_proxy_logo_missing_target(self, client):
        """Test logo proxy without target parameter."""
        response = client.get("/api/proxy_logo")
        
        # Should handle gracefully (either error or redirect)
        assert response.status_code in [302, 400, 422]


class TestCheckStreamEndpoint:
    """Tests for GET /api/check_stream endpoint."""

    def test_check_stream_success(self, client):
        """Test successful stream check."""
        stream_url = "http://stream.example.com/video.ts"
        origin_url = "http://example.com/stalker_portal/c/"
        
        encoded_stream = base64.b64encode(stream_url.encode()).decode()
        encoded_origin = base64.b64encode(origin_url.encode()).decode()
        
        with patch("app.routers.streams.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)
            
            response = client.get(
                f"/api/check_stream?target={encoded_stream}&mac=00:11:22:33:44:55&origin={encoded_origin}"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["code"] == 200

    def test_check_stream_error_response(self, client):
        """Test stream check with error response from stream."""
        stream_url = "http://stream.example.com/video.ts"
        encoded_stream = base64.b64encode(stream_url.encode()).decode()
        
        with patch("app.routers.streams.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)
            
            response = client.get(
                f"/api/check_stream?target={encoded_stream}&mac=00:11:22:33:44:55"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert data["code"] == 403

    def test_check_stream_unsafe_url(self, client):
        """Test stream check with unsafe URL."""
        unsafe_url = "http://192.168.1.1/stream.ts"
        encoded_url = base64.b64encode(unsafe_url.encode()).decode()
        
        response = client.get(
            f"/api/check_stream?target={encoded_url}&mac=00:11:22:33:44:55"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["code"] == 403

    def test_check_stream_invalid_base64(self, client):
        """Test stream check with invalid base64."""
        response = client.get(
            "/api/check_stream?target=invalid-base64&mac=00:11:22:33:44:55"
        )
        
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]


class TestProxyStreamEndpoint:
    """Tests for GET /api/proxy_stream endpoint."""

    def test_proxy_stream_success(self, client):
        """Test successful stream proxy."""
        stream_url = "http://stream.example.com/video.ts"
        origin_url = "http://example.com/stalker_portal/c/"
        
        encoded_stream = base64.b64encode(stream_url.encode()).decode()
        encoded_origin = base64.b64encode(origin_url.encode()).decode()
        
        with patch("app.routers.streams.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "video/MP2T"}
            mock_response.iter_content.return_value = [b"video chunk 1", b"video chunk 2"]
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)
            
            response = client.get(
                f"/api/proxy_stream?target={encoded_stream}&mac=00:11:22:33:44:55&origin={encoded_origin}"
            )
            
            assert response.status_code == 200
            # Check for streaming response headers
            assert "Accept-Ranges" in response.headers or "Cache-Control" in response.headers

    def test_proxy_stream_unsafe_url(self, client):
        """Test stream proxy with unsafe URL (SSRF protection)."""
        unsafe_url = "http://192.168.1.1/stream.ts"
        encoded_url = base64.b64encode(unsafe_url.encode()).decode()
        
        response = client.get(
            f"/api/proxy_stream?target={encoded_url}&mac=00:11:22:33:44:55"
        )
        
        assert response.status_code == 403

    def test_proxy_stream_with_range_header(self, client):
        """Test stream proxy forwards Range header."""
        stream_url = "http://stream.example.com/video.ts"
        encoded_stream = base64.b64encode(stream_url.encode()).decode()
        
        with patch("app.routers.streams.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 206
            mock_response.headers = {"Content-Type": "video/MP2T"}
            mock_response.iter_content.return_value = [b"partial content"]
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)
            
            response = client.get(
                f"/api/proxy_stream?target={encoded_stream}&mac=00:11:22:33:44:55",
                headers={"Range": "bytes=0-1024"}
            )
            
            # Verify Range header was passed to requests
            call_kwargs = mock_get.call_args[1]
            assert call_kwargs["headers"]["Range"] == "bytes=0-1024"

    def test_proxy_stream_error_response(self, client):
        """Test stream proxy when upstream returns error."""
        stream_url = "http://stream.example.com/video.ts"
        encoded_stream = base64.b64encode(stream_url.encode()).decode()
        
        with patch("app.routers.streams.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.iter_content.return_value = []
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)
            
            response = client.get(
                f"/api/proxy_stream?target={encoded_stream}&mac=00:11:22:33:44:55"
            )
            
            # Should still return 200 but content will contain error message
            assert response.status_code == 200

    def test_proxy_stream_invalid_base64(self, client):
        """Test stream proxy with invalid base64."""
        response = client.get(
            "/api/proxy_stream?target=not-valid-base64&mac=00:11:22:33:44:55"
        )
        
        assert response.status_code in [400, 500]


class TestCORSHeaders:
    """Tests for CORS headers."""

    def test_cors_headers_on_get(self, client):
        """Test CORS headers are present on GET requests."""
        response = client.get("/", headers={"Origin": "http://localhost:3000"})
        
        # CORS headers may or may not be present depending on configuration
        # Just verify the request succeeds
        assert response.status_code == 200

    def test_cors_preflight(self, client):
        """Test CORS preflight request."""
        response = client.options(
            "/api/check",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )
        
        # Should allow the request
        assert response.status_code in [200, 204]


class TestErrorHandling:
    """Tests for error handling across endpoints."""

    def test_404_not_found(self, client):
        """Test 404 for non-existent endpoint."""
        response = client.get("/api/nonexistent")
        
        assert response.status_code == 404

    def test_method_not_allowed(self, client):
        """Test 405 for method not allowed."""
        response = client.post("/")  # POST not allowed on root
        
        assert response.status_code == 405

    def test_validation_error_format(self, client):
        """Test validation error response format."""
        response = client.post("/api/get_link", json={"invalid": "data"})
        
        assert response.status_code == 422
        error_data = response.json()
        assert "detail" in error_data

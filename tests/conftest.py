"""
Pytest fixtures and configuration for STBcheck tests.

This module provides shared fixtures for unit and integration tests.
"""

import base64
import json
import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


# =============================================================================
# App and Client Fixtures
# =============================================================================

@pytest.fixture
def app():
    """Create and configure the FastAPI app for testing."""
    from app.main import app
    return app


@pytest.fixture
def client(app):
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


# =============================================================================
# Mock Fixtures for StalkerPortal
# =============================================================================

@pytest.fixture
def mock_stalker_portal():
    """Create a mock StalkerPortal instance."""
    with patch("app.services.stalker.StalkerPortal") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_session():
    """Create a mock requests.Session for StalkerPortal tests."""
    with patch("app.services.stalker.requests.Session") as mock_session_class:
        mock_session_instance = MagicMock()
        mock_session_class.return_value = mock_session_instance
        yield mock_session_instance


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_portal_url():
    """Return a sample portal URL."""
    return "http://example.com/stalker_portal/c/"


@pytest.fixture
def sample_mac_address():
    """Return a sample MAC address."""
    return "00:1A:2B:3C:4D:5E"


@pytest.fixture
def sample_profile_data():
    """Return sample profile data from a portal."""
    return {
        "id": "12345",
        "name": "Test User",
        "login": "testuser",
        "status": 1,
        "expire_date": "2025-12-31"
    }


@pytest.fixture
def sample_account_info():
    """Return sample account info from a portal."""
    return {
        "login": "testuser",
        "account": {
            "expire_date": "2025-12-31",
            "status": "Active"
        }
    }


@pytest.fixture
def sample_channels_data():
    """Return sample channels data."""
    return [
        {
            "id": "1",
            "name": "Test Channel 1",
            "cmd": "ffmpeg http://stream1.example.com",
            "logo": "/images/logo1.png",
            "tv_genre_id": "1"
        },
        {
            "id": "2",
            "name": "Test Channel 2",
            "cmd": "ffmpeg http://stream2.example.com",
            "logo": "/images/logo2.png",
            "tv_genre_id": "2"
        }
    ]


@pytest.fixture
def sample_genres_data():
    """Return sample genres/categories data."""
    return [
        {"id": "1", "title": "Sports"},
        {"id": "2", "title": "Movies"}
    ]


@pytest.fixture
def sample_text_with_pairs():
    """Return sample text containing portal URL and MAC address."""
    return """
    PORTAL: http://example.com/stalker_portal/c/
    MAC: 00:1A:2B:3C:4D:5E
    
    Panel: http://example2.com/portal.php
    ID: AA:BB:CC:DD:EE:FF
    """


@pytest.fixture
def sample_text_emoji_format():
    """Return sample text with emoji formatting."""
    return """
    🛰 ➤ http://example.com/stalker_portal/c/
    ✅ ➤ 00:1A:2B:3C:4D:5E
    """


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture
def mock_requests_get():
    """Mock requests.get for HTTP calls."""
    with patch("requests.get") as mock_get:
        yield mock_get


@pytest.fixture
def mock_requests_session():
    """Mock requests.Session for session-based HTTP calls."""
    with patch("requests.Session") as mock_session_class:
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        yield mock_session


@pytest.fixture
def encoded_logo_url():
    """Return a base64-encoded logo URL."""
    url = "http://example.com/logo.png"
    return base64.b64encode(url.encode()).decode()


@pytest.fixture
def encoded_stream_url():
    """Return a base64-encoded stream URL."""
    url = "http://stream.example.com/video.ts"
    return base64.b64encode(url.encode()).decode()


@pytest.fixture
def encoded_origin_url():
    """Return a base64-encoded origin URL."""
    url = "http://example.com/stalker_portal/c/"
    return base64.b64encode(url.encode()).decode()

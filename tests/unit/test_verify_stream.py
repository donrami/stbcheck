"""
Unit tests for verify_stream function.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from app.routers.streams import verify_stream


def make_mock_response(status=200, content_type="video/mp2t", headers=None):
    """Create a mock aiohttp response that works as async context manager."""
    resp = MagicMock()
    resp.status = status
    resp.headers = headers or {}
    if content_type:
        resp.headers["Content-Type"] = content_type

    async def json_func():
        return {}

    resp.json = json_func

    # Async context manager support
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


@pytest.mark.asyncio
async def test_verify_stream_success_video():
    """Test verification succeeds with video content type."""
    session = MagicMock()
    response = make_mock_response(200, "video/mp2t")
    session.get = AsyncMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is True


@pytest.mark.asyncio
async def test_verify_stream_success_octet_stream():
    """Test verification succeeds with octet-stream."""
    session = MagicMock()
    response = make_mock_response(200, "application/octet-stream")
    session.get = AsyncMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is True


@pytest.mark.asyncio
async def test_verify_stream_success_mpegurl():
    """Test verification succeeds with x-mpegurl."""
    session = MagicMock()
    response = make_mock_response(200, "application/x-mpegurl")
    session.get = AsyncMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is True


@pytest.mark.asyncio
async def test_verify_stream_success_206_partial():
    """Test verification succeeds with 206 Partial Content."""
    session = MagicMock()
    response = make_mock_response(206, "video/mp4")
    session.get = AsyncMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is True


@pytest.mark.asyncio
async def test_verify_stream_fails_404():
    """Test verification fails with 404."""
    session = MagicMock()
    response = make_mock_response(404, "text/html")
    session.get = AsyncMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is False


@pytest.mark.asyncio
async def test_verify_stream_success_video():
    """Test verification succeeds with video content type."""
    session = MagicMock()
    response = make_mock_response(200, "video/mp2t")
    session.get = MagicMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is True


@pytest.mark.asyncio
async def test_verify_stream_success_octet_stream():
    """Test verification succeeds with octet-stream."""
    session = MagicMock()
    response = make_mock_response(200, "application/octet-stream")
    session.get = MagicMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is True


@pytest.mark.asyncio
async def test_verify_stream_success_mpegurl():
    """Test verification succeeds with x-mpegurl."""
    session = MagicMock()
    response = make_mock_response(200, "application/x-mpegurl")
    session.get = MagicMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is True


@pytest.mark.asyncio
async def test_verify_stream_success_206_partial():
    """Test verification succeeds with 206 Partial Content."""
    session = MagicMock()
    response = make_mock_response(206, "video/mp4")
    session.get = MagicMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is True


@pytest.mark.asyncio
async def test_verify_stream_fails_404():
    """Test verification fails with 404."""
    session = MagicMock()
    response = make_mock_response(404, "text/html")
    session.get = MagicMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is False


@pytest.mark.asyncio
async def test_verify_stream_fails_bad_content_type():
    """Test verification fails with non-video content type."""
    session = MagicMock()
    response = make_mock_response(200, "text/html")
    session.get = MagicMock(return_value=response)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is False


@pytest.mark.asyncio
async def test_verify_stream_timeout():
    """Test verification returns False on timeout."""
    session = MagicMock()

    # Simulate timeout by having get raise TimeoutError
    async def raise_timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    session.get = AsyncMock(side_effect=raise_timeout)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is False


@pytest.mark.asyncio
async def test_verify_stream_exception():
    """Test verification returns False on generic exception."""
    session = MagicMock()

    async def raise_exception(*args, **kwargs):
        raise Exception("Network error")

    session.get = AsyncMock(side_effect=raise_exception)

    result = await verify_stream(
        "http://example.com/stream", "http://example.com", session
    )
    assert result is False

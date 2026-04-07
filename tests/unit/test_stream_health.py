"""
Unit tests for stream health monitoring and circuit breaker functionality.

Tests for StreamHealthMonitor class and related health tracking.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.routers.streams import (
    StreamHealthMonitor,
    _stream_monitor,
    _stream_proxy_stats,
)


class TestStreamHealthMonitor:
    """Tests for the StreamHealthMonitor circuit breaker."""

    def test_initial_state(self):
        """Test circuit starts closed with no failures."""
        monitor = StreamHealthMonitor(failure_threshold=3, open_duration=60)
        assert not monitor.should_skip("http://example.com/stream")

    def test_record_success_resets_failures(self):
        """Test that success resets consecutive failure count."""
        monitor = StreamHealthMonitor(failure_threshold=3, open_duration=60)
        url = "http://example.com/stream"

        # Record some failures manually
        monitor.record_stream_failure(url, is_error=True, use_domain=False)
        monitor.record_stream_failure(url, is_error=True, use_domain=False)
        assert (
            monitor.should_skip(url, use_domain=False) is False
        )  # Still under threshold

        monitor.record_stream_success(url, use_domain=False)
        # After success, failures should reset; the recorded failures count should be 0
        # We can check should_skip still returns False
        assert not monitor.should_skip(url, use_domain=False)

    def test_circuit_opens_after_threshold(self):
        """Test circuit opens after consecutive failures reach threshold."""
        monitor = StreamHealthMonitor(failure_threshold=3, open_duration=60)
        url = "http://example.com/stream"

        for _ in range(3):
            monitor.record_stream_failure(url, is_error=True, use_domain=False)

        assert monitor.should_skip(url, use_domain=False) is True

    def test_circuit_auto_closes_after_timeout(self):
        """Test circuit closes automatically after open_duration."""
        monitor = StreamHealthMonitor(failure_threshold=3, open_duration=1)  # 1 second
        url = "http://example.com/stream"

        for _ in range(3):
            monitor.record_stream_failure(url, is_error=True, use_domain=False)

        assert monitor.should_skip(url, use_domain=False) is True

        # Wait for circuit to be eligible to close (half-open trial)
        time.sleep(1.1)

        # After timeout, should_skip should allow trial (returns False) because circuit resets to half-open
        # But we haven't attempted again, so still closed? Actually our implementation sets open_until, and if current time > open_until, we reset open_until to 0 and return False (so half-open trial). So it should be False.
        assert not monitor.should_skip(url, use_domain=False)

    def test_domain_level_tracking(self):
        """Test that domain-level tracking groups failures by netloc."""
        monitor = StreamHealthMonitor(failure_threshold=2, open_duration=60)
        url1 = "http://example.com/stream1"
        url2 = "http://example.com/stream2"
        url3 = "http://other.com/stream"

        # Failures on same domain
        monitor.record_stream_failure(url1, is_error=True, use_domain=True)
        assert not monitor.should_skip(url2, use_domain=True)  # 1 failure, not open

        monitor.record_stream_failure(url2, is_error=True, use_domain=True)
        assert (
            monitor.should_skip(url3, use_domain=True) is False
        )  # Different domain ok
        assert (
            monitor.should_skip(url1, use_domain=True) is True
        )  # Same domain now open
        assert monitor.should_skip(url2, use_domain=True) is True

    def test_get_stats(self):
        """Test get_stats returns expected structure."""
        monitor = StreamHealthMonitor()
        stats = monitor.get_stats()
        assert "total_circuits" in stats
        assert "open_circuits" in stats
        assert "circuits" in stats
        assert isinstance(stats["circuits"], list)

    def test_success_not_counted_as_failure(self):
        """Test that success does not increment failure count."""
        monitor = StreamHealthMonitor(failure_threshold=2, open_duration=60)
        url = "http://example.com/stream"
        monitor.record_stream_success(url, use_domain=False)
        assert not monitor.should_skip(url, use_domain=False)


class TestGlobalProxyStats:
    """Tests for global proxy statistics tracking."""

    def test_initial_stats(self):
        """Test initial values of global stats dict."""
        # _stream_proxy_stats should exist and have keys
        assert "total_requests" in _stream_proxy_stats
        assert "successful" in _stream_proxy_stats
        assert "failed" in _stream_proxy_stats
        assert "circuit_opens" in _stream_proxy_stats

    def test_stats_are_mutable(self):
        """Test that stats can be modified (they are used for monitoring)."""
        initial_total = _stream_proxy_stats["total_requests"]
        _stream_proxy_stats["total_requests"] += 1
        assert _stream_proxy_stats["total_requests"] == initial_total + 1
        # Reset
        _stream_proxy_stats["total_requests"] = initial_total

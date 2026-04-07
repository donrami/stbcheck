"""
Unit tests for MAC address normalization.

Tests for normalize_mac function from app.services.base
"""

import pytest
from app.services.base import normalize_mac


class TestNormalizeMac:
    """Tests for normalize_mac function."""

    def test_normalizes_colon_separated_uppercase(self):
        """Test MAC with colons already uppercase remains unchanged."""
        mac = "AA:BB:CC:DD:EE:FF"
        result = normalize_mac(mac)
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_normalizes_colon_separated_lowercase(self):
        """Test MAC with colons lowercase is converted to uppercase."""
        mac = "aa:bb:cc:dd:ee:ff"
        result = normalize_mac(mac)
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_normalizes_hyphen_separated(self):
        """Test MAC with hyphens is converted to colons uppercase."""
        mac = "aa-bb-cc-dd-ee-ff"
        result = normalize_mac(mac)
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_normalizes_no_separator(self):
        """Test MAC without separators is split into colon format."""
        mac = "aabbccddeeff"
        result = normalize_mac(mac)
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_normalizes_mixed_separator_and_case(self):
        """Test mixed separators and case."""
        mac = "Aa-Bb:CcDdEeFf"
        result = normalize_mac(mac)
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_handles_all_uppercase_without_separator(self):
        """Test all uppercase without separator."""
        mac = "001A2B3C4D5E"
        result = normalize_mac(mac)
        assert result == "00:1A:2B:3C:4D:5E"

    def test_invalid_length_returns_original(self):
        """Test MAC with incorrect length is returned unchanged."""
        mac = "00:11:22:33:44"  # only 5 octets
        result = normalize_mac(mac)
        assert result == "00:11:22:33:44"

    def test_invalid_characters_return_original(self):
        """Test MAC with non-hex characters is returned unchanged."""
        mac = "GG:HH:II:JJ:KK:LL"
        result = normalize_mac(mac)
        assert result == "GG:HH:II:JJ:KK:LL"

    def test_empty_string_returns_empty(self):
        """Test empty string returns empty."""
        result = normalize_mac("")
        assert result == ""

    def test_none_returns_none(self):
        """Test None returns None."""
        result = normalize_mac(None)
        assert result is None

    def test_normalizes_various_real_world_formats(self):
        """Test a variety of real-world MAC formats."""
        test_cases = [
            ("00:1A:2B:3C:4D:5E", "00:1A:2B:3C:4D:5E"),
            ("00-1a-2b-3c-4d-5e", "00:1A:2B:3C:4D:5E"),
            ("001a2b3c4d5e", "00:1A:2B:3C:4D:5E"),
            ("001A2B3C4D5E", "00:1A:2B:3C:4D:5E"),
            ("00:1a:2b:3c:4d:5e", "00:1A:2B:3C:4D:5E"),
            ("00-1A-2B-3C-4D-5E", "00:1A:2B:3C:4D:5E"),
        ]
        for input_mac, expected in test_cases:
            result = normalize_mac(input_mac)
            assert result == expected, (
                f"Failed for {input_mac}: got {result}, expected {expected}"
            )

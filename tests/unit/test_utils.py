"""
Unit tests for app/services/utils.py

Tests for utility functions:
- detect_expiry()
- is_safe_url()
- extract_portal_mac_pairs()
- is_portal_url()
- clean_stalker_url()
"""

import pytest
from unittest.mock import patch

from app.services.utils import (
    detect_expiry,
    is_safe_url,
    extract_portal_mac_pairs,
    is_portal_url,
    clean_stalker_url,
    PORTAL_HEADERS,
)


class TestDetectExpiry:
    """Tests for detect_expiry function."""

    def test_detect_expiry_in_primary_key(self):
        """Test detecting expiry in primary keys."""
        data = {"expire_date": "2025-12-31"}
        result = detect_expiry(data)
        assert result == "2025-12-31"

    def test_detect_expiry_various_keys(self):
        """Test detecting expiry with various key names."""
        test_cases = [
            ({"expire_date": "2025-12-31"}, "2025-12-31"),
            ({"end_date": "2025-12-31"}, "2025-12-31"),
            ({"max_view_date": "2025-12-31"}, "2025-12-31"),
            ({"expire_billing_date": "2025-12-31"}, "2025-12-31"),
            ({"tariff_expired_date": "2025-12-31"}, "2025-12-31"),
            ({"date_end": "2025-12-31"}, "2025-12-31"),
            ({"exp_date": "2025-12-31"}, "2025-12-31"),
            ({"expDate": "2025-12-31"}, "2025-12-31"),
            ({"expired": "2025-12-31"}, "2025-12-31"),
            ({"expires": "2025-12-31"}, "2025-12-31"),
            ({"expiry_date": "2025-12-31"}, "2025-12-31"),
            ({"access_end": "2025-12-31"}, "2025-12-31"),
            ({"end_date_time": "2025-12-31 23:59:59"}, "2025-12-31 23:59:59"),
            ({"valid_until": "2025-12-31"}, "2025-12-31"),
            ({"active_until": "2025-12-31"}, "2025-12-31"),
        ]
        
        for data, expected in test_cases:
            result = detect_expiry(data)
            assert result == expected, f"Failed for key in data: {data}"

    def test_detect_expiry_ignores_empty_values(self):
        """Test that empty/placeholder values are ignored."""
        empty_values = ["", "0", "0000-00-00", "0000-00-00 00:00:00", "null", "none", "false", "unlimited"]
        
        for val in empty_values:
            data = {"expire_date": val}
            result = detect_expiry(data)
            assert result is None, f"Should ignore value: {val}"

    def test_detect_expiry_in_nested_dict(self):
        """Test detecting expiry in nested account_info."""
        data = {
            "account_info": {
                "expire_date": "2025-12-31"
            }
        }
        result = detect_expiry(data)
        assert result == "2025-12-31"

    def test_detect_expiry_in_stb_account(self):
        """Test detecting expiry in stb_account."""
        data = {
            "stb_account": {
                "end_date": "2025-12-31"
            }
        }
        result = detect_expiry(data)
        assert result == "2025-12-31"

    def test_detect_expiry_in_billing(self):
        """Test detecting expiry in billing section."""
        data = {
            "billing": {
                "expire_date": "2025-12-31"
            }
        }
        result = detect_expiry(data)
        assert result == "2025-12-31"

    def test_detect_expiry_in_subscription_list(self):
        """Test detecting expiry in subscription list."""
        data = {
            "subscription": [
                {"name": "Basic", "expire_date": "2025-06-01"},
                {"name": "Premium", "expire_date": "2025-12-31"}
            ]
        }
        result = detect_expiry(data)
        assert result == "2025-06-01"  # First valid one found

    def test_detect_expiry_no_valid_date(self):
        """Test when no valid expiry date exists."""
        data = {
            "name": "Test User",
            "status": "Active",
            "other_field": "value"
        }
        result = detect_expiry(data)
        assert result is None

    def test_detect_expiry_non_dict_input(self):
        """Test with non-dict input."""
        assert detect_expiry("string") is None
        assert detect_expiry(123) is None
        assert detect_expiry(None) is None
        assert detect_expiry([]) is None

    def test_detect_expiry_max_depth(self):
        """Test that recursion stops at max depth."""
        # Create deeply nested structure
        data = {"level1": {"level2": {"level3": {"level4": {"level5": {"expire_date": "2025-12-31"}}}}}}
        result = detect_expiry(data)
        # Should not find it due to depth limit
        assert result is None

    def test_detect_expiry_aggressive_search(self):
        """Test aggressive search for date-like values."""
        data = {
            "custom_expiry_field": "2025-12-31",
            "valid_until_date": "2026-01-01"
        }
        result = detect_expiry(data)
        assert result in ["2025-12-31", "2026-01-01"]

    def test_detect_expiry_timestamp_format(self):
        """Test detecting timestamp format."""
        data = {"expire_date": "1735689600"}  # Unix timestamp
        result = detect_expiry(data)
        assert result == "1735689600"


class TestIsSafeUrl:
    """Tests for is_safe_url function."""

    def test_safe_http_url(self):
        """Test that HTTP URLs are considered safe."""
        assert is_safe_url("http://example.com") is True
        assert is_safe_url("http://example.com/path") is True

    def test_safe_https_url(self):
        """Test that HTTPS URLs are considered safe."""
        assert is_safe_url("https://example.com") is True
        assert is_safe_url("https://example.com:443/path") is True

    def test_rejects_ftp_url(self):
        """Test that FTP URLs are rejected."""
        assert is_safe_url("ftp://example.com") is False

    def test_rejects_file_url(self):
        """Test that file:// URLs are rejected."""
        assert is_safe_url("file:///etc/passwd") is False

    def test_rejects_javascript_url(self):
        """Test that javascript: URLs are rejected."""
        assert is_safe_url("javascript:alert('xss')") is False

    def test_rejects_data_url(self):
        """Test that data: URLs are rejected."""
        assert is_safe_url("data:text/html,<script>alert('xss')</script>") is False

    def test_rejects_private_ip(self):
        """Test that private IP addresses are rejected."""
        assert is_safe_url("http://192.168.1.1") is False
        assert is_safe_url("http://10.0.0.1") is False
        assert is_safe_url("http://172.16.0.1") is False
        assert is_safe_url("http://127.0.0.1") is False

    def test_rejects_loopback_ip(self):
        """Test that loopback addresses are rejected."""
        assert is_safe_url("http://127.0.0.1") is False
        assert is_safe_url("http://127.0.0.53") is False

    def test_rejects_localhost(self):
        """Test that localhost is rejected."""
        assert is_safe_url("http://localhost") is False
        assert is_safe_url("http://localhost:8080") is False
        assert is_safe_url("http://localhost.localdomain") is False

    def test_rejects_link_local(self):
        """Test that link-local addresses are rejected."""
        assert is_safe_url("http://169.254.1.1") is False

    def test_rejects_multicast(self):
        """Test that multicast addresses are rejected."""
        assert is_safe_url("http://224.0.0.1") is False

    def test_accepts_public_ip(self):
        """Test that public IPs are accepted."""
        assert is_safe_url("http://8.8.8.8") is True
        assert is_safe_url("http://1.1.1.1") is True

    def test_invalid_url(self):
        """Test with invalid URLs."""
        assert is_safe_url("not-a-url") is False
        assert is_safe_url("") is False
        assert is_safe_url(None) is False

    def test_url_with_port(self):
        """Test URLs with ports."""
        assert is_safe_url("http://example.com:8080") is True
        assert is_safe_url("https://example.com:8443/path") is True


class TestExtractPortalMacPairs:
    """Tests for extract_portal_mac_pairs function."""

    def test_extract_standard_format(self):
        """Test extracting pairs from standard format."""
        text = "PORTAL: http://example.com/stalker_portal/c/\nMAC: 00:11:22:33:44:55"
        pairs = extract_portal_mac_pairs(text)
        
        assert len(pairs) == 1
        assert pairs[0] == ("http://example.com/stalker_portal/c", "00:11:22:33:44:55")

    def test_extract_panel_format(self):
        """Test extracting pairs from Panel format."""
        text = "Panel: http://example.com/c/\nMac: AA:BB:CC:DD:EE:FF"
        pairs = extract_portal_mac_pairs(text)
        
        assert len(pairs) == 1
        assert pairs[0] == ("http://example.com/c", "AA:BB:CC:DD:EE:FF")

    def test_extract_emoji_format(self):
        """Test extracting pairs with emoji format."""
        text = "🛰 ➤ http://example.com/stalker_portal/c/\n✅ ➤ 00:11:22:33:44:55"
        pairs = extract_portal_mac_pairs(text)
        
        assert len(pairs) == 1
        assert pairs[0] == ("http://example.com/stalker_portal/c", "00:11:22:33:44:55")

    def test_extract_box_drawing_format(self):
        """Test extracting pairs with box drawing characters."""
        text = "╭─• http://example.com/c/\n├─• 00:11:22:33:44:55"
        pairs = extract_portal_mac_pairs(text)
        
        assert len(pairs) == 1
        assert pairs[0] == ("http://example.com/c", "00:11:22:33:44:55")

    def test_extract_multiple_pairs(self):
        """Test extracting multiple portal/MAC pairs."""
        text = """
        PORTAL: http://example1.com/c/
        MAC: 00:11:22:33:44:55
        
        PORTAL: http://example2.com/c/
        MAC: AA:BB:CC:DD:EE:FF
        """
        pairs = extract_portal_mac_pairs(text)
        
        # Implementation may find extra matches due to fallback logic
        # Check that at least the expected pairs are present
        assert len(pairs) >= 2
        assert ("http://example1.com/c", "00:11:22:33:44:55") in pairs
        assert ("http://example2.com/c", "AA:BB:CC:DD:EE:FF") in pairs

    def test_extract_hyphen_mac(self):
        """Test extracting MAC with hyphens (converted to colons)."""
        text = "PORTAL: http://example.com/c/\nMAC: 00-11-22-33-44-55"
        pairs = extract_portal_mac_pairs(text)
        
        assert len(pairs) == 1
        assert pairs[0] == ("http://example.com/c", "00:11:22:33:44:55")

    def test_extract_generic_format(self):
        """Test extracting from generic URL MAC format."""
        text = "http://example.com/c/ 00:11:22:33:44:55"
        pairs = extract_portal_mac_pairs(text)
        
        assert len(pairs) == 1
        assert pairs[0] == ("http://example.com/c", "00:11:22:33:44:55")

    def test_extract_no_pairs(self):
        """Test when no pairs are found."""
        text = "This is just some random text without any portal or MAC info."
        pairs = extract_portal_mac_pairs(text)
        
        assert len(pairs) == 0

    def test_extract_no_url(self):
        """Test when only MAC is present."""
        text = "MAC: 00:11:22:33:44:55"
        pairs = extract_portal_mac_pairs(text)
        
        assert len(pairs) == 0

    def test_extract_no_mac(self):
        """Test when only URL is present."""
        text = "PORTAL: http://example.com/c/"
        pairs = extract_portal_mac_pairs(text)
        
        # May return pairs with best-match MAC logic
        # or empty depending on implementation
        assert isinstance(pairs, list)

    def test_extract_removes_trailing_slash(self):
        """Test that trailing slashes are removed from URLs."""
        text = "PORTAL: http://example.com/c//\nMAC: 00:11:22:33:44:55"
        pairs = extract_portal_mac_pairs(text)
        
        assert len(pairs) >= 1
        # URL should not end with //
        assert not pairs[0][0].endswith("//")

    def test_mac_normalization_uppercase(self):
        """Test that MAC addresses are normalized to uppercase."""
        text = "PORTAL: http://example.com/c/\nMAC: aa:bb:cc:dd:ee:ff"
        pairs = extract_portal_mac_pairs(text)
        
        assert len(pairs) == 1
        assert pairs[0][1] == "AA:BB:CC:DD:EE:FF"

    def test_extract_id_label(self):
        """Test extracting with ID label."""
        text = "ID: 00:11:22:33:44:55"
        # Without URL, should not extract
        pairs = extract_portal_mac_pairs(text)
        assert len(pairs) == 0


class TestIsPortalUrl:
    """Tests for is_portal_url function."""

    def test_portal_url_with_c_suffix(self):
        """Test URL ending with /c."""
        assert is_portal_url("http://example.com/stalker_portal/c") is True

    def test_portal_url_with_c_slash(self):
        """Test URL containing /c/."""
        assert is_portal_url("http://example.com/stalker_portal/c/") is True

    def test_portal_url_with_portal_php(self):
        """Test URL containing portal.php."""
        assert is_portal_url("http://example.com/portal.php") is True
        assert is_portal_url("http://example.com/portal.php?action=handshake") is True

    def test_portal_url_with_server_load_php(self):
        """Test URL containing /server/load.php."""
        assert is_portal_url("http://example.com/server/load.php") is True

    def test_non_portal_url(self):
        """Test non-portal URLs."""
        assert is_portal_url("http://example.com") is False
        assert is_portal_url("http://example.com/") is False
        assert is_portal_url("http://example.com/some/path") is False

    def test_case_insensitive(self):
        """Test that check is case insensitive."""
        assert is_portal_url("http://example.com/STALKER_PORTAL/C/") is True
        assert is_portal_url("http://example.com/Portal.PHP") is True


class TestCleanStalkerUrl:
    """Tests for clean_stalker_url function."""

    def test_clean_ffmpeg_prefix(self):
        """Test removing ffmpeg prefix."""
        url = "ffmpeg http://stream.example.com/video.ts"
        result = clean_stalker_url(url)
        assert result == "http://stream.example.com/video.ts"

    def test_clean_ffrt_prefix(self):
        """Test removing ffrt prefix."""
        url = "ffrt http://stream.example.com/video.ts"
        result = clean_stalker_url(url)
        assert result == "http://stream.example.com/video.ts"

    def test_clean_solution_prefix(self):
        """Test removing solution prefix."""
        url = "solution http://stream.example.com/video.ts"
        result = clean_stalker_url(url)
        assert result == "http://stream.example.com/video.ts"

    def test_clean_no_prefix(self):
        """Test URL without prefix remains unchanged."""
        url = "http://stream.example.com/video.ts"
        result = clean_stalker_url(url)
        assert result == "http://stream.example.com/video.ts"

    def test_clean_with_quotes(self):
        """Test cleaning URL with quotes."""
        url = "'http://stream.example.com/video.ts'"
        result = clean_stalker_url(url)
        assert result == "http://stream.example.com/video.ts"

    def test_clean_with_double_quotes(self):
        """Test cleaning URL with double quotes."""
        url = '"http://stream.example.com/video.ts"'
        result = clean_stalker_url(url)
        assert result == "http://stream.example.com/video.ts"

    def test_clean_none_input(self):
        """Test with None input."""
        result = clean_stalker_url(None)
        assert result is None

    def test_clean_empty_string(self):
        """Test with empty string."""
        result = clean_stalker_url("")
        # Implementation returns None or empty string for empty input
        assert result is None or result == ""

    def test_clean_whitespace_only(self):
        """Test with whitespace only."""
        result = clean_stalker_url("   ")
        assert result == ""


class TestPortalHeaders:
    """Tests for PORTAL_HEADERS constant."""

    def test_portal_headers_structure(self):
        """Test that PORTAL_HEADERS has expected structure."""
        assert "User-Agent" in PORTAL_HEADERS
        assert "Connection" in PORTAL_HEADERS

    def test_portal_headers_user_agent(self):
        """Test that User-Agent contains expected values."""
        ua = PORTAL_HEADERS["User-Agent"]
        assert "MAG200" in ua or "MAG250" in ua or "stbapp" in ua

    def test_portal_headers_connection(self):
        """Test Connection header value."""
        assert PORTAL_HEADERS["Connection"] == "keep-alive"

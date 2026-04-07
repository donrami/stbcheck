"""
Unit tests for app/services/stalker_detection.py

Tests for Stalker portal detection and billing info extraction:
- detect_stalker_portal()
- extract_billing_info()
"""

import pytest
from typing import Dict, Any

from app.services.stalker_detection import detect_stalker_portal, extract_billing_info


class TestDetectStalkerPortal:
    """Tests for detect_stalker_portal function."""

    def test_detects_fname_indicator(self):
        """Test detection based on fname field."""
        profile = {"fname": "John Doe"}
        is_stalker, fields = detect_stalker_portal(profile, {})
        assert is_stalker is True
        assert fields["fname"] == "John Doe"

    def test_detects_expire_billing_date_indicator(self):
        """Test detection based on expire_billing_date field."""
        profile = {"expire_billing_date": "2025-12-31"}
        is_stalker, fields = detect_stalker_portal(profile, {})
        assert is_stalker is True
        assert fields["expire_billing_date"] == "2025-12-31"

    def test_detects_max_online_indicator(self):
        """Test detection based on max_online field."""
        profile = {"max_online": 3}
        is_stalker, fields = detect_stalker_portal(profile, {})
        assert is_stalker is True
        assert fields["max_online"] == 3

    def test_detects_from_account_info(self):
        """Test detection using account_info data."""
        account_info = {"expire_billing_date": "2025-12-31"}
        is_stalker, fields = detect_stalker_portal({}, account_info)
        assert is_stalker is True
        assert fields["expire_billing_date"] == "2025-12-31"

    def test_detects_from_both_sources(self):
        """Test detection combining profile and account_info."""
        profile = {"fname": "Jane"}
        account_info = {"expire_billing_date": "2025-12-31"}
        is_stalker, fields = detect_stalker_portal(profile, account_info)
        assert is_stalker is True
        assert fields["fname"] == "Jane"
        assert fields["expire_billing_date"] == "2025-12-31"

    def test_returns_false_when_no_indicators(self):
        """Test that non-Stalker portals return False."""
        profile = {"some_other_field": "value"}
        is_stalker, fields = detect_stalker_portal(profile, {})
        assert is_stalker is False
        assert fields["is_stalker"] is False

    def test_extracts_max_online_from_storages(self):
        """Test extracting max_online from nested storages."""
        profile = {
            "storages": {
                "1": {"max_online": 2, "name": "Basic"},
                "2": {"max_online": 3, "name": "Premium"},
            }
        }
        is_stalker, fields = detect_stalker_portal(profile, {})
        assert is_stalker is True
        assert fields["max_online"] == 3  # Maximum from storages

    def test_handles_zero_max_online(self):
        """Test that zero max_online values are ignored."""
        profile = {
            "storages": {
                "1": {"max_online": 0, "name": "Basic"},
                "2": {"max_online": 3, "name": "Premium"},
            }
        }
        is_stalker, fields = detect_stalker_portal(profile, {})
        assert fields["max_online"] == 3

    def test_handles_empty_storages(self):
        """Test handling of empty or invalid storages."""
        profile = {"storages": {}}
        is_stalker, fields = detect_stalker_portal(profile, {})
        assert fields["max_online"] is None

    def test_handles_none_storages(self):
        """Test handling of None storages."""
        profile = {"storages": None}
        is_stalker, fields = detect_stalker_portal(profile, {})
        assert fields["max_online"] is None

    def test_includes_all_stalker_fields_in_result(self):
        """Test that all detected Stalker fields are returned."""
        profile = {
            "fname": "Test User",
            "expire_billing_date": "2025-12-31",
            "max_online": 3,
            "storages": {"1": {"name": "Test"}},
        }
        is_stalker, fields = detect_stalker_portal(profile, {})
        assert "fname" in fields
        assert "expire_billing_date" in fields
        assert "max_online" in fields
        assert "storages" in fields
        assert "is_stalker" in fields


class TestExtractBillingInfo:
    """Tests for extract_billing_info function."""

    def test_extract_from_stalker_fields(self):
        """Test extracting billing info from Stalker fields."""
        stalker_fields = {
            "max_online": 3,
            "storages": {
                "1": {
                    "name": "Basic",
                    "max_online": 1,
                    "expire_billing_date": "2025-01-01",
                },
                "2": {
                    "name": "Premium",
                    "max_online": 3,
                    "expire_billing_date": "2025-12-31",
                },
            },
        }
        billing = extract_billing_info(stalker_fields)
        assert billing is not None
        assert billing["max_online"] == 3
        assert billing["total_storages"] == 2
        assert len(billing["packages"]) == 2

    def test_extract_includes_package_details(self):
        """Test that package details are correctly extracted."""
        stalker_fields = {
            "storages": {
                "5": {
                    "name": "Sports Pack",
                    "max_online": 2,
                    "expire_billing_date": "2025-06-30",
                },
            }
        }
        billing = extract_billing_info(stalker_fields)
        assert billing is not None
        pkg = billing["packages"][0]
        assert pkg["id"] == "5"
        assert pkg["name"] == "Sports Pack"
        assert pkg["max_online"] == 2
        assert pkg["expire_billing_date"] == "2025-06-30"

    def test_returns_none_when_no_billing_data(self):
        """Test that None is returned when no billing data available."""
        stalker_fields = {"max_online": None, "storages": {}}
        billing = extract_billing_info(stalker_fields)
        assert billing is None

    def test_handles_subscription_data(self):
        """Test extraction from subscription field."""
        stalker_fields = {
            "subscription": {
                "status": "active",
                "start_date": "2024-01-01",
                "end_date": "2025-12-31",
            }
        }
        billing = extract_billing_info(stalker_fields)
        assert billing is not None
        assert billing["subscription_status"] == "active"
        assert billing["subscription_start"] == "2024-01-01"
        assert billing["subscription_end"] == "2025-12-31"

    def test_combines_storages_and_subscription(self):
        """Test that both storages and subscription are included."""
        stalker_fields = {
            "max_online": 2,
            "storages": {"1": {"name": "Basic"}},
            "subscription": {"status": "active"},
        }
        billing = extract_billing_info(stalker_fields)
        assert billing is not None
        assert billing["total_storages"] == 1
        assert "subscription_status" in billing

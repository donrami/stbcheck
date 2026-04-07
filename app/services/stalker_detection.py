"""
Stalker/Ministra Portal Detection and Specialized Field Extraction.

This module provides functionality to detect if a portal is using Stalker/Ministra
middleware and extract Stalker-specific billing fields for more accurate expiry detection.
"""

from typing import Dict, Tuple, Optional, Any


def detect_stalker_portal(
    profile: Dict[str, Any], account_info: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any]]:
    """
    Detect if portal is a Stalker/Ministra portal and extract Stalker-specific fields.

    The detection is based on the presence of Stalker-specific field names and structures,
    particularly those related to billing management.

    Args:
        profile: Profile data from get_profile endpoint
        account_info: Account info from get_account_info endpoint

    Returns:
        Tuple of (is_stalker, stalker_fields_dict) where stalker_fields contains:
            - is_stalker: Boolean indicating if portal is Stalker-based
            - fname: User's full name (if available)
            - expire_billing_date: Billing expiration (Stalker's actual expiry field)
            - max_online: Maximum concurrent connections
            - storages: Storage/subscription data structure
    """
    # Ensure we have dicts
    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(account_info, dict):
        account_info = {}

    # Combine data from both endpoints for comprehensive detection
    combined = {**profile, **account_info}

    # Stalker-specific field indicators
    indicators = {
        "fname": combined.get("fname"),
        "expire_billing_date": combined.get("expire_billing_date"),
        "max_online": combined.get("max_online"),
        "storages": combined.get("storages"),
        "subscription": combined.get("subscription"),
    }

    # Check if any Stalker-specific field is present
    is_stalker = any(
        indicators[field] is not None
        for field in ["fname", "expire_billing_date", "max_online"]
    ) or (isinstance(indicators["storages"], dict) and len(indicators["storages"]) > 0)

    # Extract max_online from storages if needed (nested structure)
    max_online_val = None
    if indicators["storages"] and isinstance(indicators["storages"], dict):
        nums = []
        for storage in indicators["storages"].values():
            v = storage.get("max_online")
            if v and str(v).strip() not in ["0", ""]:
                try:
                    nums.append(int(str(v)))
                except (ValueError, TypeError):
                    pass
        if nums:
            max_online_val = max(nums)
        else:
            max_online_val = indicators["max_online"]
    else:
        max_online_val = indicators["max_online"]

    stalker_fields = {
        "is_stalker": is_stalker,
        "fname": indicators["fname"],
        "expire_billing_date": indicators["expire_billing_date"],
        "max_online": max_online_val,
        "storages": indicators["storages"],
        "subscription": indicators["subscription"],
    }

    return is_stalker, stalker_fields


def extract_billing_info(stalker_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract detailed billing information from Stalker storage/subscription data.

    Args:
        stalker_fields: Dictionary from detect_stalker_portal()

    Returns:
        Dictionary with billing details or None if not available
    """
    storages = stalker_fields.get("storages")
    subscription = stalker_fields.get("subscription")

    billing_info = {
        "max_online": stalker_fields.get("max_online"),
        "packages": [],
        "total_storages": 0,
    }

    # Process storages data if available
    if storages and isinstance(storages, dict):
        billing_info["total_storages"] = len(storages)
        for storage_id, storage_data in storages.items():
            if isinstance(storage_data, dict):
                pkg = {
                    "id": storage_id,
                    "name": storage_data.get("name"),
                    "max_online": storage_data.get("max_online"),
                    "expire_billing_date": storage_data.get("expire_billing_date"),
                }
                billing_info["packages"].append(pkg)

    # Process subscription data if available
    if subscription and isinstance(subscription, dict):
        billing_info["subscription_status"] = subscription.get("status")
        billing_info["subscription_start"] = subscription.get("start_date")
        billing_info["subscription_end"] = subscription.get("end_date")

    return billing_info if billing_info["total_storages"] > 0 or subscription else None

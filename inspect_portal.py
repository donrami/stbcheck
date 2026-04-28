#!/usr/bin/env python3
"""
Stalker Portal Response Inspector — Bug #3 Diagnostic Tool

Dumps full raw JSON responses from every Stalker Portal endpoint, including
all response layers (raw, js, result). This reveals exactly where expiry
data lives in each portal's response.

Usage:
    python inspect_portal.py <portal_url> <mac_address> [--output <dir>]

Examples:
    python inspect_portal.py http://example.com/c 00:1A:79:37:C9:89
    python inspect_portal.py http://example.com/c 00:1A:79:37:C9:89 --output portal_dump/
"""

import asyncio
import json
import sys
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

import aiohttp
from yarl import URL

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.base import (
    clean_json_response,
    get_handshake_paths,
    extract_token,
    unwrap_response,
    MAG200_USER_AGENT,
    MAG250_XUA,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("inspector")


# ---------------------------------------------------------------------------
# Endpoint definitions
# ---------------------------------------------------------------------------

# Currently called endpoints (from stalker_async.py get_expiration_info)
CURRENT_ENDPOINTS = [
    ("stb", "get_profile", {"stb_type": "MAG250", "sn": "1234567890123"}),
    ("stb", "get_account_info", {}),
    ("stb", "do_auth", {}),
    ("stb", "get_main_info", {}),
    ("billing", "get_main_info", {}),
    ("billing", "get_subscription_info", {}),
    ("billing", "get_account_info", {}),
]

# Additional endpoints we DON'T currently call — hypothesis H3
EXTRA_ENDPOINTS = [
    ("stb", "get_storage_info", {}),
    ("stb", "update_services", {}),
    ("stb", "get_favorites", {}),
    ("itv", "get_itv_info", {}),
    ("itv", "get_all_channels", {}),
    ("itv", "get_genres", {}),
    ("itv", "get_subscription", {}),
    ("watchdog", "get_events", {"event_active_id": "0", "init": "0", "cur_play_type": "1"}),
    # account_info type (different from stb type) — the proposed fix in issue #3
    ("account_info", "get_main_info", {}),
    ("account_info", "get_account_info", {}),
]


# ---------------------------------------------------------------------------
# Inspector client
# ---------------------------------------------------------------------------

class PortalInspector:
    """Makes requests to a Stalker portal and dumps every response layer."""

    def __init__(self, portal_url: str, mac: str, timeout: int = 15):
        self.base_url = portal_url.rstrip("/")
        self.mac = mac.upper()
        self.timeout = timeout
        self.token: Optional[str] = None
        self.active_path: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.results: list[dict] = []

    def _headers(self) -> Dict[str, str]:
        h = {
            "User-Agent": MAG200_USER_AGENT,
            "Accept": "*/*",
            "Accept-Charset": "UTF-8,*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "X-User-Agent": MAG250_XUA,
            "Referer": f"{self.base_url}/",
            "Connection": "keep-alive",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def _request_full(
        self, params: Dict[str, str], path: Optional[str] = None
    ) -> Optional[dict]:
        """Make request and return all 3 response layers."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                cookie_jar=aiohttp.CookieJar(unsafe=True),
            )
            base_url_obj = URL(self.base_url)
            root_url = base_url_obj.with_path("/")
            self.session.cookie_jar.update_cookies(
                {
                    "mac": self.mac,
                    "stb_lang": "en",
                    "timezone": "Europe/London",
                },
                root_url,
            )
            if self.token:
                self.session.cookie_jar.update_cookies({"token": self.token}, root_url)

        target_path = path or self.active_path
        if not target_path:
            return None

        full_params = {"JsHttpRequest": "1-xml", **params}
        try:
            async with self.session.get(
                target_path, params=full_params, headers=self._headers()
            ) as resp:
                raw_text = await resp.text()
                status = resp.status

                # Parse
                data = None
                try:
                    data = await resp.json()
                except (aiohttp.ContentTypeError, json.JSONDecodeError):
                    cleaned = clean_json_response(raw_text)
                    try:
                        data = json.loads(cleaned)
                    except (json.JSONDecodeError, ValueError):
                        data = None

                if data is None:
                    # Return what we can — raw text
                    return {
                        "raw": {"_parse_error": True, "_raw_text_preview": raw_text[:2000]},
                        "js": {},
                        "result": {},
                        "status": status,
                        "raw_text": raw_text,
                    }

                # Extract layers
                js_obj = data.get("js") if isinstance(data, dict) and "js" in data else data
                result_obj = (
                    js_obj.get("result")
                    if isinstance(js_obj, dict) and "result" in js_obj
                    else js_obj
                )

                return {
                    "raw": data if isinstance(data, dict) else {"_raw": data},
                    "js": js_obj if isinstance(js_obj, dict) else {},
                    "result": result_obj if isinstance(result_obj, (dict, list)) else {},
                    "status": status,
                }
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None

    async def handshake(self) -> bool:
        """Try all handshake paths."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                cookie_jar=aiohttp.CookieJar(unsafe=True),
            )
            base_url_obj = URL(self.base_url)
            root_url = base_url_obj.with_path("/")
            self.session.cookie_jar.update_cookies(
                {"mac": self.mac, "stb_lang": "en", "timezone": "Europe/London"},
                root_url,
            )

        import random, hashlib
        paths = get_handshake_paths(self.base_url, add_trailing_slash=True)

        for path in paths:
            try:
                # Standard handshake
                full_params = {"type": "stb", "action": "handshake", "JsHttpRequest": "1-xml"}
                async with self.session.get(
                    path, params=full_params, headers=self._headers()
                ) as resp:
                    raw_text = await resp.text()
                    if resp.status == 200:
                        data = None
                        try:
                            data = await resp.json()
                        except (aiohttp.ContentTypeError, json.JSONDecodeError):
                            cleaned = clean_json_response(raw_text)
                            try:
                                data = json.loads(cleaned)
                            except (json.JSONDecodeError, ValueError):
                                data = None

                        if data:
                            data = unwrap_response(data)
                            token = extract_token(data)
                            if token:
                                self.token = token
                                self.active_path = path
                                logger.info(f"Handshake OK: {path} (token len={len(token)})")
                                return True

                # 404 fallback
                if resp.status == 404:
                    token_gen = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=32))
                    prehash = hashlib.sha1(token_gen.encode()).hexdigest()
                    full_params = {
                        "type": "stb", "action": "handshake",
                        "token": token_gen, "prehash": prehash,
                        "JsHttpRequest": "1-xml",
                    }
                    async with self.session.get(path, params=full_params, headers=self._headers()) as retry_resp:
                        if retry_resp.status == 200:
                            data = None
                            try:
                                data = await retry_resp.json()
                            except (aiohttp.ContentTypeError, json.JSONDecodeError):
                                cleaned = clean_json_response(await retry_resp.text())
                                try:
                                    data = json.loads(cleaned)
                                except (json.JSONDecodeError, ValueError):
                                    data = None
                            if data:
                                data = unwrap_response(data)
                                token = extract_token(data)
                                if token:
                                    self.token = token
                                    self.active_path = path
                                    logger.info(f"Handshake OK (404 fallback): {path}")
                                    return True
            except Exception as e:
                logger.debug(f"Handshake attempt failed for {path}: {e}")
                continue

        logger.error("Handshake failed on all paths")
        return False

    async def inspect(self, extra: bool = False) -> list[dict]:
        """Run all endpoint checks and return results."""
        endpoints = list(CURRENT_ENDPOINTS)
        if extra:
            endpoints.extend(EXTRA_ENDPOINTS)

        logger.info(f"Checking {len(endpoints)} endpoints on {self.base_url} (MAC: {self.mac})")

        # Handshake
        ok = await self.handshake()
        if not ok:
            logger.warning("Handshake failed — some endpoints may not return data")

        # Check each endpoint
        for ep_type, ep_action, extra_params in endpoints:
            params = {"type": ep_type, "action": ep_action, **extra_params}
            logger.info(f"  → type={ep_type} action={ep_action}")
            resp = await self._request_full(params)

            record = {
                "endpoint": f"type={ep_type}&action={ep_action}",
                "params": params,
                "response": resp,
                "path_used": self.active_path,
                "token": self.token,
            }
            self.results.append(record)

            # Quick summary
            if resp is None:
                logger.info(f"    [NO RESPONSE]")
            elif resp.get("status") == 404:
                logger.info(f"    [404 NOT FOUND]")
            else:
                raw_keys = list(resp.get("raw", {}).keys())[:15]
                js_keys = list(resp.get("js", {}).keys())[:15]
                res_keys = list(resp.get("result", {}).keys())[:15] if isinstance(resp.get("result"), dict) else []
                logger.info(f"    raw keys: {raw_keys}")
                logger.info(f"    js keys:  {js_keys}")
                if res_keys:
                    logger.info(f"    result keys: {res_keys}")

        return self.results

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def find_expiry_fields(data: Any, path: str = "") -> list[tuple[str, Any]]:
    """Recursively find any key that might contain expiry/date info."""
    if not isinstance(data, dict):
        return []

    results = []
    expiry_keywords = [
        "expire", "exp_", "end_date", "valid_until", "access_end",
        "billing", "subscription", "tariff", "active_until",
        "max_view_date", "date_end", "plan_expires", "expires",
        "expiry_date", "expired", "end", "to",
    ]

    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key
        key_lower = key.lower()

        # Check if key name matches
        if any(kw in key_lower for kw in expiry_keywords):
            results.append((current_path, value))

        # Check if string value looks like a date
        if isinstance(value, str) and len(value) >= 8:
            if any(p in value for p in ["-", "/"]):
                parts = value.replace("/", "-").split("-")
                if len(parts) == 3 and parts[0].isdigit() and len(parts[0]) == 4:
                    if current_path not in [r[0] for r in results]:
                        results.append((current_path, value))

        # Recurse
        if isinstance(value, dict):
            results.extend(find_expiry_fields(value, current_path))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    results.extend(find_expiry_fields(item, f"{current_path}[{i}]"))

    return results


def analyze_results(results: list[dict]) -> str:
    """Generate an analysis summary from inspection results."""
    lines = []
    lines.append("=" * 70)
    lines.append("EXPIRY DATA ANALYSIS")
    lines.append("=" * 70)

    found_anywhere = False

    for record in results:
        resp = record.get("response")
        if resp is None:
            continue
        endpoint = record["endpoint"]

        for layer_name in ["raw", "js", "result"]:
            layer_data = resp.get(layer_name)
            if layer_data is None:
                continue
            if isinstance(layer_data, dict) and layer_data.get("_parse_error"):
                continue

            hits = find_expiry_fields(layer_data)
            if hits:
                found_anywhere = True
                lines.append(f"\n📍 Endpoint: {endpoint}")
                lines.append(f"   Layer: {layer_name}")
                for field_path, value in hits:
                    lines.append(f"   → {field_path} = {value}")

    if not found_anywhere:
        lines.append("\n❌ No expiry-related fields found in ANY endpoint/layer.")
        lines.append("   Possible causes:")
        lines.append("   - Portal requires specific auth parameters (device_id, signature)")
        lines.append("   - Portal uses a completely different API structure")
        lines.append("   - Expiry data is only returned after do_auth succeeds")
        lines.append("   - Account genuinely has no expiry (unlimited)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_results(results: list[dict], output_dir: str):
    """Save all results as JSON files."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Individual endpoint files
    for record in results:
        safe_name = record["endpoint"].replace("&", "_").replace("=", "_")
        filepath = out / f"{safe_name}.json"
        with open(filepath, "w") as f:
            json.dump(record["response"], f, indent=2, default=str)
        logger.info(f"  Saved: {filepath}")

    # Combined summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "portal": results[0].get("path_used", "") if results else "",
        "mac": results[0].get("token", "")[:0],  # placeholder
        "endpoints": [
            {
                "endpoint": r["endpoint"],
                "status": r["response"].get("status") if r["response"] else None,
                "has_raw": bool(r["response"].get("raw")) if r["response"] else False,
                "has_js": bool(r["response"].get("js")) if r["response"] else False,
                "has_result": bool(r["response"].get("result")) if r["response"] else False,
            }
            for r in results
        ],
    }
    with open(out / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Analysis
    analysis = analyze_results(results)
    with open(out / "analysis.txt", "w") as f:
        f.write(analysis)

    logger.info(f"\nAnalysis:\n{analysis}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    portal_url = sys.argv[1]
    mac = sys.argv[2]

    # Parse optional args
    output_dir = None
    extra_endpoints = False
    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--extra":
            extra_endpoints = True
            i += 1
        else:
            i += 1

    inspector = PortalInspector(portal_url, mac)

    try:
        results = await inspector.inspect(extra=extra_endpoints)

        # Always print analysis
        analysis = analyze_results(results)
        print(f"\n{analysis}")

        # Save if output dir specified
        if output_dir:
            save_results(results, output_dir)
        else:
            # Save to default location
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_dir = f"portal_inspect_{timestamp}"
            save_results(results, default_dir)

    finally:
        await inspector.close()


if __name__ == "__main__":
    asyncio.run(main())

"""
Router for portal-related endpoints.
"""

import base64
import html
import json
import re
import gc
import asyncio
import logging
from typing import Optional, List, Dict, Tuple

import requests
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.limiter import limiter

from app.config import settings
from app.models import CheckRequest
from app.services.stalker_async import StalkerClient
from app.services.base import PORTAL_HEADERS
from app.services.url_validator import is_safe_url, is_portal_url
from app.services.text_parser import extract_portal_mac_pairs


logger = logging.getLogger(__name__)
router = APIRouter()


def build_logo_url(channel_logo: str, portal_url: str) -> Optional[str]:
    """
    Build the proxy logo URL for a channel logo.

    Args:
        channel_logo: Raw logo URL from channel data
        portal_url: Base portal URL

    Returns:
        Proxy URL string or None if logo is invalid
    """
    if not channel_logo or channel_logo in ["None", "null", ""]:
        return None

    # Remove potential Stalker prefix like "s:0:"
    logo = re.sub(r"^s:\d+:", "", channel_logo)

    # Skip data URIs - these are embedded images, not fetchable URLs
    # The frontend can handle data URIs directly without proxy
    if logo.startswith("data:"):
        logger.debug(f"Logo is a data URI, skipping proxy: {logo[:50]}...")
        return None

    # Make absolute URL
    if logo.startswith("/"):
        logo = portal_url.rstrip("/") + logo
    elif not logo.startswith("http"):
        logo = portal_url.rstrip("/") + "/" + logo

    # Encode for proxy endpoint
    encoded = base64.b64encode(logo.encode()).decode()
    return f"/api/proxy_logo?target={encoded}"


def deduplicate_categories(categories: List[Dict]) -> List[Dict]:
    """
    Remove duplicate categories by ID while preserving order.

    Args:
        categories: List of category dicts with 'id' and 'title'

    Returns:
        Deduplicated list of categories
    """
    seen = set()
    result = []
    for cat in categories:
        cid = str(cat.get("id", ""))
        if cid and cid not in seen:
            seen.add(cid)
            result.append(
                {
                    "id": cid,
                    "title": str(cat.get("title") or cat.get("name", "")),
                }
            )
    return result


async def fetch_all_channels(client: StalkerClient) -> List[Dict]:
    """
    Fetch all channels from the portal using multiple fallback methods.

    Args:
        client: Authenticated StalkerClient

    Returns:
        List of channel dictionaries
    """
    itv_info = await client.get_itv_info()
    channels_raw = None
    if isinstance(itv_info, dict):
        channels_raw = (
            itv_info.get("channels")
            or itv_info.get("data")
            or itv_info.get("itv_items")
        )
    if not channels_raw:
        channels_raw = await client.get_channels()

    all_channels = []
    if isinstance(channels_raw, dict) and "data" in channels_raw:
        all_channels = channels_raw["data"]
    elif isinstance(channels_raw, list):
        all_channels = channels_raw

    return all_channels


async def fetch_all_categories(client: StalkerClient) -> List[Dict]:
    """
    Fetch all categories from the portal using multiple fallback methods.

    Args:
        client: Authenticated StalkerClient

    Returns:
        List of category dictionaries
    """
    genres_raw = await client.get_genres()
    if not genres_raw:
        genres_raw = await client.get_itv_groups()
    if not genres_raw:
        genres_raw = await client.get_short_genres()
    if not genres_raw:
        genres_raw = await client.get_all_itv_groups()
    if not genres_raw:
        genres_raw = await client.get_categories()

    # Also check itv_info as fallback
    if not genres_raw:
        itv_info = await client.get_itv_info()
        if isinstance(itv_info, dict):
            genres_raw = (
                itv_info.get("genres")
                or itv_info.get("groups")
                or itv_info.get("itv_groups")
            )

    categories = []
    if isinstance(genres_raw, dict) and "data" in genres_raw:
        categories = genres_raw["data"]
    elif isinstance(genres_raw, list):
        categories = genres_raw

    return categories


def enhance_channels_with_categories(
    channels: List[Dict], categories: List[Dict], portal_url: str
) -> Tuple[List[Dict], Dict[str, str]]:
    """
    Process channels to add category information and build category map.

    Args:
        channels: Raw list of channel dictionaries
        categories: Raw list of category dictionaries
        portal_url: Base portal URL for logo construction

    Returns:
        Tuple of (processed_channels, category_map)
    """
    # Build initial category map from categories
    cat_map = {}
    for c in categories:
        if isinstance(c, dict):
            cid = str(c.get("id", ""))
            ctitle = str(c.get("title") or c.get("name") or c.get("label") or cid)
            if cid:
                cat_map[cid] = ctitle

    processed_channels = []
    for c in channels:
        if not isinstance(c, dict):
            continue

        name = str(c.get("name", ""))
        logo = build_logo_url(str(c.get("logo", "")), portal_url)

        # Determine category ID
        cat_id = "uncategorized"
        for key in [
            "tv_genre_id",
            "category_id",
            "genre_id",
            "group_id",
            "genre",
            "itv_group_id",
        ]:
            val = c.get(key)
            if val is not None and str(val) != "":
                cat_id = str(val)
                break

        # Determine category name
        cat_name = None
        for key in ["category_name", "genre_name", "group_name", "genre_title"]:
            val = c.get(key)
            if val is not None and str(val) != "":
                cat_name = str(val)
                break

        # If we have category ID but no name in existing map, add it
        if cat_id != "uncategorized" and cat_name and cat_id not in cat_map:
            cat_map[cat_id] = cat_name
            categories.append({"id": cat_id, "title": cat_name})

        processed_channels.append(
            {
                "id": c.get("id"),
                "name": name,
                "cmd": c.get("cmd"),
                "logo": logo,
                "category_id": cat_id,
            }
        )

    # Ensure all category IDs referenced in channels exist in cat_map
    unique_cat_ids = {ch["category_id"] for ch in processed_channels}
    for cid in unique_cat_ids:
        if cid not in cat_map:
            cname = "Uncategorized" if cid == "uncategorized" else f"Group {cid}"
            cat_map[cid] = cname
            categories.append({"id": cid, "title": cname})

    return processed_channels, cat_map


async def process_single_portal(url: str, mac: str) -> Optional[Dict]:
    """
    Process a single portal URL and MAC address pair asynchronously.

    Args:
        url: Portal URL
        mac: MAC address

    Returns:
        Dictionary with portal data or None if failed
    """
    async with StalkerClient(url, mac) as client:
        try:
            logger.info(f"Analyzing portal: {url} ({mac})")
            # Perform handshake first to establish authentication
            handshake_success = await client.handshake()
            if not handshake_success:
                logger.warning(f"Handshake failed for {url} with MAC {mac}")
                return None
            # Now _active_path is set, we can proceed
            exp_info = await client.get_expiration_info()
            if client._active_path is None:
                return None
            expiry = exp_info.expiration or "Unlimited"

            # Fetch channels and categories using helpers
            all_channels = await fetch_all_channels(client)
            categories = await fetch_all_categories(client)

            # Enhance channels with category info and build category map
            processed_channels, cat_map = enhance_channels_with_categories(
                all_channels, categories, url
            )

            # Build unique categories list from cat_map
            unique_categories = [
                {"id": cid, "title": title} for cid, title in cat_map.items() if cid
            ]

            logger.info(
                f"   -> Found {len(processed_channels)} channels and {len(unique_categories)} categories for {url}"
            )
            return {
                "url": url,
                "mac": mac,
                "channel_count": len(processed_channels),
                "categories": unique_categories,
                "channels": processed_channels,
                "expiry": expiry,
            }
        except Exception as e:
            logger.error(f"Error processing portal {url}: {e}")
            return None


@router.post("/api/check")
@limiter.limit(settings.rate_limit_portal_check)
async def check_portals(request: Request, req: CheckRequest):
    """
    Check portals and extract channel information.

    Accepts text containing portal URLs and MAC addresses, crawls URLs if needed,
    and returns channel information via Server-Sent Events.
    """
    input_text = req.text.strip()
    logger.info(f"Checking portals for input of length {len(input_text)}")

    async def event_generator():
        # 1. Try extracting pairs directly from input
        pairs = extract_portal_mac_pairs(input_text)

        # 2. If no pairs found, check if there are URLs to crawl
        if not pairs:
            # Find all URLs in the input
            urls = re.findall(r"https?://\S+", input_text)
            urls = [u.rstrip(".,;)>") for u in urls]  # Clean trailing punctuation

            to_crawl = []
            for u in urls:
                if is_safe_url(u) and not is_portal_url(u):
                    to_crawl.append(u)

            if to_crawl:
                # Limit to first 3 URLs to avoid abuse
                to_crawl = to_crawl[:3]
                yield f"data: {json.dumps({'type': 'status', 'message': f'No pairs found in text. Crawling {len(to_crawl)} URL(s)...'})}\n\n"

                for u in to_crawl:
                    try:
                        yield f"data: {json.dumps({'type': 'status', 'message': f'Crawling {u}...'})}\n\n"
                        # Use a thread for the blocking request
                        response = await asyncio.to_thread(
                            requests.get,
                            u,
                            timeout=settings.request_timeout,
                            headers=PORTAL_HEADERS,
                            verify=settings.verify_ssl,
                        )
                        if response.status_code == 200:
                            # Remove script/style content to avoid false matches from JS/JSON-LD
                            clean_text = re.sub(
                                r"<(?:script|style)[^>]*>.*?</(?:script|style)>",
                                " ",
                                response.text,
                                flags=re.DOTALL | re.IGNORECASE,
                            )
                            # Strip remaining HTML tags and decode HTML entities
                            clean_text = re.sub("<[^<]+?>", " ", clean_text)
                            clean_text = html.unescape(clean_text)
                            found_pairs = extract_portal_mac_pairs(clean_text)
                            if found_pairs:
                                pairs.extend(found_pairs)
                                yield f"data: {json.dumps({'type': 'status', 'message': f'Found {len(found_pairs)} pairs on {u}'})}\n\n"
                    except Exception as e:
                        logger.error(f"Error crawling {u}: {e}")
                        yield f"data: {json.dumps({'type': 'status', 'message': f'Error crawling {u}'})}\n\n"

                # Remove duplicates
                pairs = list(dict.fromkeys(pairs))

        if not pairs:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No Portal/MAC pairs found in the input or crawled sites.'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'results': []})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'start', 'total': len(pairs)})}\n\n"

        # Concurrent processing with progress updates
        semaphore = asyncio.Semaphore(settings.max_concurrent_portal_checks)

        async def check_task(url, mac):
            async with semaphore:
                try:
                    # Process with timeout
                    return await asyncio.wait_for(
                        process_single_portal(url, mac),
                        timeout=settings.stream_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout processing portal: {url}")
                except Exception as e:
                    logger.error(f"Error checking {url}: {e}")
                return None

        # Create tasks for all pairs
        tasks = [check_task(url, mac) for url, mac in pairs]

        completed = 0

        # Use as_completed to yield progress as soon as each check finishes
        for future in asyncio.as_completed(tasks):
            result = await future
            completed += 1
            # Skip servers with no channels
            if result and result.get("channel_count", 0) > 0:
                yield f"data: {json.dumps({'type': 'result', 'result': result})}\n\n"
                del result

            yield f"data: {json.dumps({'type': 'progress', 'current': completed, 'total': len(pairs)})}\n\n"

        yield f"data: {json.dumps({'type': 'complete'})}\n\n"
        tasks.clear()
        gc.collect()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

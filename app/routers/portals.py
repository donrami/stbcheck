"""
Router for portal-related endpoints.
"""

import json
import re
import gc
import asyncio
import logging

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import urllib3

from app.config import settings
from app.models import CheckRequest
from app.services.stalker import StalkerPortal
from app.services.utils import (
    detect_expiry,
    is_portal_url,
    extract_portal_mac_pairs,
    is_safe_url,
    PORTAL_HEADERS,
)

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
router = APIRouter()


def process_single_portal(url, mac):
    """
    Process a single portal URL and MAC address pair.
    
    Performs handshake, retrieves profile, account info, channels, and categories.
    
    Args:
        url: Portal URL
        mac: MAC address
        
    Returns:
        Dictionary with portal data or None if failed
    """
    portal = StalkerPortal(url, mac)
    try:
        logger.info(f"Analyzing portal: {url} ({mac})")
        if portal.handshake():
            profile = portal.get_profile()
            acc_info = portal.get_account_info()
            
            # Debug logging to see what we're actually getting
            # We don't log the full object to avoid flooding logs, just keys and existence
            p_keys = list(profile.keys()) if isinstance(profile, dict) else "Not a dict"
            a_keys = list(acc_info.keys()) if isinstance(acc_info, dict) else "Not a dict"
            logger.info(f"Portal data for {url}: Profile keys={p_keys}, AccInfo keys={a_keys}")

            expiry = detect_expiry(profile) or detect_expiry(acc_info) or "Unlimited"
            
            itv_info = portal.get_itv_info()
            
            channels_raw = None
            if isinstance(itv_info, dict):
                channels_raw = itv_info.get('channels') or itv_info.get('data') or itv_info.get('itv_items')
            
            if not channels_raw:
                channels_raw = portal.get_channels()
            
            all_channels = []
            if isinstance(channels_raw, dict) and 'data' in channels_raw:
                all_channels = channels_raw['data']
            elif isinstance(channels_raw, list):
                all_channels = channels_raw
            
            # Aggregate categories
            genres_raw = portal.get_genres()
            if not genres_raw: genres_raw = portal.get_itv_groups()
            if not genres_raw: genres_raw = portal.get_short_genres()
            if not genres_raw: genres_raw = portal.get_all_itv_groups()
            if not genres_raw: genres_raw = portal.get_categories()
            
            if isinstance(itv_info, dict) and not genres_raw:
                genres_raw = itv_info.get('genres') or itv_info.get('groups') or itv_info.get('itv_groups')
            
            categories = []
            if isinstance(genres_raw, dict) and 'data' in genres_raw:
                categories = genres_raw['data']
            elif isinstance(genres_raw, list):
                categories = genres_raw
            
            cat_map = {}
            for c in categories:
                if isinstance(c, dict):
                    cid = str(c.get('id', ''))
                    ctitle = str(c.get('title') or c.get('name') or c.get('label') or cid)
                    if cid: 
                        cat_map[cid] = ctitle
            
            processed_channels = []
            for c in all_channels:
                if not isinstance(c, dict): 
                    continue
                
                name = str(c.get('name', ''))
                logo = str(c.get('logo', ''))
                if logo and logo not in ['None', 'null', '']:
                    logo = re.sub(r'^s:\d+:', '', logo)
                    if logo.startswith('/'): 
                        logo = url.rstrip('/') + logo
                    elif not logo.startswith('http'): 
                        logo = url.rstrip('/') + '/' + logo
                    import base64
                    logo = f"/api/proxy_logo?target={base64.b64encode(logo.encode()).decode()}"
                else:
                    logo = None

                cat_id = "uncategorized"
                for key in ['tv_genre_id', 'category_id', 'genre_id', 'group_id', 'genre', 'itv_group_id']:
                    val = c.get(key)
                    if val is not None and str(val) != '':
                        cat_id = str(val)
                        break
                
                cat_name = None
                for key in ['category_name', 'genre_name', 'group_name', 'genre_title']:
                    val = c.get(key)
                    if val is not None and str(val) != '':
                        cat_name = str(val)
                        break

                if cat_id != "uncategorized" and cat_name:
                    cid_str = str(cat_id)
                    cname_str = str(cat_name)
                    if cid_str not in cat_map:
                        cat_map[cid_str] = cname_str
                        categories.append({"id": cid_str, "title": cname_str})

                processed_channels.append({
                    "id": c.get('id'), 
                    "name": name, 
                    "cmd": c.get('cmd'), 
                    "logo": logo,
                    "category_id": cat_id
                })
            
            # Sync categories found in channels
            unique_ids = {ch['category_id'] for ch in processed_channels}
            for cid in unique_ids:
                if cid not in cat_map:
                    c_name = "Uncategorized" if cid == "uncategorized" else f"Group {cid}"
                    categories.append({"id": cid, "title": c_name})
                    cat_map[cid] = c_name

            # Filter and unique
            unique_categories = []
            seen_cat_ids = set()
            for cat in categories:
                cid = str(cat.get('id', ''))
                if cid and cid not in seen_cat_ids:
                    seen_cat_ids.add(cid)
                    unique_categories.append({"id": cid, "title": str(cat.get('title') or cat.get('name', ''))})
            
            logger.info(f"   -> Found {len(processed_channels)} channels and {len(unique_categories)} categories for {url}")
            res = {
                "url": url,
                "mac": mac,
                "channel_count": len(processed_channels),
                "categories": unique_categories,
                "channels": processed_channels,
                "expiry": expiry
            }
            # Explicitly cleanup local large refs before returning
            del processed_channels
            del all_channels
            del categories
            return res
    except Exception as e:
        logger.error(f"Error processing portal {url}: {e}")
    finally:
        portal.session.close()
    return None


@router.post("/api/check")
async def check_portals(req: CheckRequest):
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
            urls = re.findall(r'https?://\S+', input_text)
            urls = [u.rstrip('.,;)>') for u in urls]  # Clean trailing punctuation
            
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
                            verify=False
                        )
                        if response.status_code == 200:
                            # Strip HTML tags for better regex matching
                            clean_text = re.sub('<[^<]+?>', ' ', response.text)
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
                        asyncio.to_thread(process_single_portal, url, mac),
                        timeout=settings.stream_timeout
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
            if result:
                yield f"data: {json.dumps({'type': 'result', 'result': result})}\n\n"
                del result
            
            yield f"data: {json.dumps({'type': 'progress', 'current': completed, 'total': len(pairs)})}\n\n"
        
        yield f"data: {json.dumps({'type': 'complete'})}\n\n"
        tasks.clear()
        gc.collect()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
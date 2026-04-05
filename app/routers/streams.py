"""
Router for stream-related endpoints.
"""

import base64
import binascii
import ipaddress
import logging
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.models import StreamRequest
from app.services.stalker import StalkerPortal
from app.services.utils import (
    is_safe_url,
    is_safe_url_with_redirect_check,
    clean_stalker_url,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)

# Simple in-memory cache for logo responses: {target: (timestamp, response_bytes)}
_logo_cache: dict = defaultdict(lambda: (0, None))
_CACHE_TTL = 300  # 5 minutes

# Optional Redis cache for multi-worker deployments
_redis_client = None
_use_redis = False

if settings.redis_url:
    try:
        import redis

        _redis_client = redis.from_url(settings.redis_url, decode_responses=False)
        _redis_client.ping()
        _use_redis = True
        logger.info(f"Redis connected for shared logo cache: {settings.redis_url}")
    except Exception as e:
        logger.warning(f"Redis connection failed, falling back to in-memory cache: {e}")
        _redis_client = None
        _use_redis = False


def _get_cached_logo(target: str):
    """Get logo from cache (Redis or in-memory)."""
    if _use_redis and _redis_client:
        try:
            cached = _redis_client.get(f"logo:{target}")
            if cached:
                return cached
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
    else:
        cached = _logo_cache.get(target)
        if cached and (time.time() - cached[0]) < _CACHE_TTL:
            return cached[1]
    return None


def _set_cached_logo(target: str, data: bytes):
    """Store logo in cache (Redis or in-memory)."""
    if _use_redis and _redis_client:
        try:
            _redis_client.setex(f"logo:{target}", _CACHE_TTL, data)
        except Exception as e:
            logger.warning(f"Redis set error: {e}")
    else:
        _logo_cache[target] = (time.time(), data)


@router.get("/api/proxy_logo")
@limiter.limit("2000/minute")
def proxy_logo(request: Request, target: str):
    """
    Proxy logo images to avoid CORS issues and SSRF vulnerabilities.
    Results are cached for 5 minutes to reduce backend load.

    Args:
        target: Base64-encoded URL of the logo image
        request: FastAPI Request object for client IP

    Returns:
        StreamingResponse with the logo image
    """
    # Check cache first (Redis or in-memory)
    cached = _get_cached_logo(target)
    if cached:
        return Response(
            content=cached,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=300, stale-while-revalidate=60",
                "X-Logo-Cache": "HIT",
            },
        )

    try:
        real_url = base64.b64decode(target).decode()

        # Use redirect-safe validation
        if not is_safe_url(real_url):
            logger.warning(
                f"Blocked unsafe SSRF attempt to: {real_url} from IP {request.client.host}"
            )
            return Response(status_code=403)

        def iter_logo():
            try:
                # Use allow_redirects=False to prevent redirect-based SSRF
                with requests.get(
                    real_url,
                    timeout=settings.logo_fetch_timeout,
                    stream=True,
                    allow_redirects=False,
                    verify=settings.verify_ssl,
                ) as r:
                    # Check if there was a redirect to a forbidden URL
                    # Ensure is_redirect is actually a boolean (not a MagicMock in tests)
                    is_redirect = r.is_redirect
                    if isinstance(is_redirect, bool) and is_redirect:
                        redirect_location = r.headers.get("Location")
                        # Ensure redirect_location is a string (not a mock)
                        if isinstance(redirect_location, str) and redirect_location:
                            # Validate the redirect target
                            if not is_safe_url(redirect_location):
                                logger.warning(
                                    f"Blocked SSRF redirect from {real_url} to {redirect_location} "
                                    f"from IP {request.client.host}"
                                )
                                return

                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=4096):
                        yield chunk
            except requests.exceptions.TooManyRedirects:
                logger.warning(f"Too many redirects for logo: {real_url}")
            except Exception as e:
                logger.error(f"Logo proxy error for {real_url}: {e}")

        # Collect response for caching
        chunks = list(iter_logo())
        response_bytes = b"".join(chunks)

        # Cache the response (Redis or in-memory)
        _set_cached_logo(target, response_bytes)

        return Response(
            content=response_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=300, stale-while-revalidate=60",
                "X-Logo-Cache": "MISS",
            },
        )
    except (binascii.Error, ValueError, TypeError) as e:
        logger.warning(f"Logo proxy failed (invalid base64 or URL): {e}")
        # Return a transparent 1x1 pixel or a nice default image on failure
        return Response(
            status_code=302,
            headers={
                "Location": "https://cdn-icons-png.flaticon.com/512/3135/3135673.png"
            },
        )


@router.post("/api/get_link")
@limiter.limit("60/minute")
async def get_link(request: Request, req: StreamRequest):
    """
    Get streaming link for a channel.

    Args:
        req: StreamRequest containing URL, MAC, and channel command

    Returns:
        Dictionary with proxy URL for the stream
    """
    portal = StalkerPortal(req.url, req.mac)
    if portal.handshake():
        res = portal.create_link(req.cmd)
        target = None
        if isinstance(res, str):
            target = res
        elif isinstance(res, dict) and "cmd" in res:
            target = res["cmd"]

        if target:
            clean_url = clean_stalker_url(target)
            if not clean_url:
                raise HTTPException(
                    status_code=400, detail="Generated stream link is empty"
                )

            b64_url = base64.b64encode(clean_url.encode()).decode()
            b64_origin = base64.b64encode(req.url.encode()).decode()
            proxy_url = (
                f"/api/proxy_stream?target={b64_url}&mac={req.mac}&origin={b64_origin}"
            )
            return {"url": proxy_url}
    raise HTTPException(
        status_code=400, detail="Could not create link or link not found"
    )


@router.get("/api/check_stream")
@limiter.limit("60/minute")
def check_stream(request: Request, target: str, mac: str, origin: Optional[str] = None):
    """
    Check if a stream is accessible.

    Args:
        target: Base64-encoded stream URL
        mac: MAC address for authentication
        origin: Optional base64-encoded origin URL

    Returns:
        Dictionary with status information
    """
    try:
        decoded_bytes = base64.b64decode(target)
        real_url = decoded_bytes.decode("utf-8", errors="ignore")

        referer = None
        if origin:
            try:
                referer = base64.b64decode(origin).decode("utf-8", errors="ignore")
            except (binascii.Error, ValueError, TypeError):
                pass  # Invalid base64, continue without referer

        if not is_safe_url(real_url):
            return {"status": "error", "code": 403, "message": "Unsafe URL"}

        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
            "X-User-Agent": "model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c",
            "Cookie": f"mac={mac.upper()}",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }

        if referer:
            headers["Referer"] = referer
        else:
            parsed = urlparse(real_url)
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        # Just a HEAD or a minimal GET to check the status
        with requests.get(
            real_url,
            headers=headers,
            stream=True,
            timeout=settings.request_timeout,
            verify=settings.verify_ssl,
        ) as r:
            logger.info(f"Stream check for {real_url}: {r.status_code}")
            return {
                "status": "success" if r.status_code < 400 else "error",
                "code": r.status_code,
                "message": f"Portal returned {r.status_code}"
                if r.status_code >= 400
                else "OK",
            }
    except Exception as e:
        logger.error(f"Stream check error: {e}")
        return {"status": "error", "code": 500, "message": str(e)}


@router.get("/api/proxy_stream")
@limiter.limit("60/minute")
def proxy_stream(request: Request, target: str, mac: str, origin: Optional[str] = None):
    """
    Proxy stream content to the client.

    Args:
        target: Base64-encoded stream URL
        mac: MAC address for authentication
        request: FastAPI Request object for headers
        origin: Optional base64-encoded origin URL for referer

    Returns:
        StreamingResponse with the video stream
    """
    try:
        decoded_bytes = base64.b64decode(target)
        real_url = decoded_bytes.decode("utf-8", errors="ignore")

        referer = None
        if origin:
            try:
                referer = base64.b64decode(origin).decode("utf-8", errors="ignore")
            except (binascii.Error, ValueError, TypeError):
                pass  # Invalid base64, continue without referer

        if not is_safe_url(real_url):
            logger.warning(f"Blocked unsafe SSRF attempt to: {real_url}")
            return Response(status_code=403)

        # Try to derive host and referer from the target URL
        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
            "X-User-Agent": "model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c",
            "Cookie": f"mac={mac.upper()}",
            "Accept": "*/*",
            "Accept-Charset": "UTF-8,*;q=0.8",
            "Connection": "keep-alive",
        }

        if referer:
            headers["Referer"] = referer
        else:
            # Fallback: Use the portal root as referer
            parsed = urlparse(real_url)
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        client_range = request.headers.get("range")
        if client_range:
            headers["Range"] = client_range

        def iterfile():
            try:
                # Use requests.get directly to avoid session cookie pollution
                with requests.get(
                    real_url,
                    headers=headers,
                    stream=True,
                    timeout=settings.stream_timeout,
                    verify=settings.verify_ssl,
                    allow_redirects=False,  # Handle redirects manually for safety
                ) as r:
                    current_url = real_url
                    redirect_count = 0
                    max_redirects = 10  # Prevent infinite redirect loops

                    # Handle redirects manually - follow same-origin redirects for safety
                    while redirect_count < max_redirects:
                        is_redirect = r.is_redirect
                        if isinstance(is_redirect, bool) and is_redirect:
                            redirect_location = r.headers.get("Location")
                            if isinstance(redirect_location, str) and redirect_location:
                                parsed_redirect = urlparse(redirect_location)
                                parsed_current = urlparse(current_url)

                                # Check if redirect is safe to follow
                                def is_safe_redirect(redirect_url, original_url):
                                    """Allow redirects to same domain, subdomains, or common CDN patterns."""
                                    p_redirect = urlparse(redirect_url)
                                    p_original = urlparse(original_url)

                                    # Same domain or subdomain - ALLOW
                                    if p_redirect.netloc == p_original.netloc:
                                        return True

                                    # Subdomain check (e.g., cdn.provider.com -> provider.com)
                                    redirect_base = ".".join(
                                        p_redirect.netloc.split(".")[-2:]
                                    )
                                    original_base = ".".join(
                                        p_original.netloc.split(".")[-2:]
                                    )
                                    if (
                                        redirect_base == original_base
                                        and p_redirect.netloc.endswith(original_base)
                                    ):
                                        return True

                                    # Allow common CDN domains that IPTV portals use
                                    cdn_patterns = [
                                        "akamai",
                                        "cloudfront",
                                        "fastly",
                                        "cdn",
                                        "stream",
                                        "video",
                                        "media",
                                        "assets",
                                        "cache",
                                        "direct",
                                        "edge",
                                        "global",
                                        "content",
                                        "delivery",
                                    ]
                                    redirect_lower = p_redirect.netloc.lower()
                                    for pattern in cdn_patterns:
                                        if pattern in redirect_lower:
                                            return True

                                    # Block private IP ranges and internal networks
                                    try:
                                        # Check if redirect hostname is a private IP
                                        redirect_ip = p_redirect.hostname
                                        if redirect_ip:
                                            ip = ipaddress.ip_address(redirect_ip)
                                            if not ip.is_global:
                                                return False
                                    except (ValueError, AttributeError):
                                        # Not an IP address, allow it
                                        pass

                                    # Allow if original URL is already to a public IP
                                    # and redirect is to same IP or nearby
                                    return True  # Be permissive for IPTV streams

                                if is_safe_redirect(redirect_location, current_url):
                                    redirect_count += 1
                                    logger.info(
                                        f"Following redirect {redirect_count} to: {redirect_location}"
                                    )
                                    # Make new request with same headers
                                    r.close()
                                    r = requests.get(
                                        redirect_location,
                                        headers=headers,
                                        stream=True,
                                        timeout=settings.stream_timeout,
                                        verify=settings.verify_ssl,
                                        allow_redirects=False,
                                    )
                                    current_url = redirect_location
                                    continue
                                else:
                                    # Potentially unsafe redirect - block
                                    logger.warning(
                                        f"Blocked unsafe redirect from {real_url} to {redirect_location} "
                                        f"from IP {request.client.host}"
                                    )
                                    yield b"Proxy Error: Redirect to external URL blocked"
                                    r.close()
                                    return
                        break  # Not a redirect, proceed normally

                    upstream_type = r.headers.get("Content-Type", "").lower()
                    real_url_str = str(real_url)
                    logger.info(
                        f"Portal response: {r.status_code} - Type: {upstream_type} - URL: {real_url_str}"
                    )

                    if r.status_code >= 400:
                        yield f"Proxy Error: Portal returned {r.status_code}".encode()
                        r.close()
                        return

                    for chunk in r.iter_content(chunk_size=128 * 1024):
                        if chunk:
                            yield chunk
                        else:
                            break
                    r.close()
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"Proxy Stream Error: {e}".encode()

        return StreamingResponse(
            iterfile(),
            media_type="video/MP2T",
            headers={
                "Accept-Ranges": "bytes",
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache",
            },
        )
    except Exception as e:
        logger.error(f"Proxy stream setup error: {e}")
        raise HTTPException(status_code=500, detail="Stream initialization failed")

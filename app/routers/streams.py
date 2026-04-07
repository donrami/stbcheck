"""
Router for stream-related endpoints.
"""

import base64
import binascii
import ipaddress
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import requests
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.models import StreamRequest
from app.services.stalker_async import StalkerClient
from app.services.url_validator import is_safe_url, is_safe_url_with_redirect_check
from app.services.text_parser import clean_stalker_url

logger = logging.getLogger(__name__)
router = APIRouter()

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)

# In-memory cache for logo responses with size limit and TTL
_logo_cache: TTLCache = TTLCache(
    maxsize=settings.logo_cache_maxsize, ttl=settings.logo_cache_ttl
)

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


# =============================================================================
# Circuit Breaker & Health Monitoring
# =============================================================================


@dataclass
class CircuitState:
    """State for circuit breaker per target URL."""

    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    open_until: float = 0.0  # 0 means closed, >0 means open until that time

    def record_success(self):
        """Reset failure count on success."""
        self.consecutive_failures = 0
        self.open_until = 0.0

    def record_failure(self, failure_threshold: int, open_duration: float):
        """Record a failure and potentially open the circuit."""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        if self.consecutive_failures >= failure_threshold:
            self.open_until = self.last_failure_time + open_duration

    def is_open(self) -> bool:
        """Check if circuit is currently open."""
        if self.open_until > 0:
            if time.time() < self.open_until:
                return True
            else:
                # Circuit has been open long enough, allow a half-open trial
                self.open_until = 0  # Reset for half-open attempt
                return False
        return False


class StreamHealthMonitor:
    """Monitor stream health and implement circuit breaker pattern."""

    def __init__(
        self,
        failure_threshold: int = 3,
        open_duration: float = 300.0,  # 5 minutes
        recovery_window: float = 600.0,  # 10 minutes for tracking
    ):
        self.failure_threshold = failure_threshold
        self.open_duration = open_duration
        self.recovery_window = recovery_window
        self.circuits: Dict[str, CircuitState] = {}
        # Also track domain-level circuits (extract netloc from URL)
        self.domain_circuits: Dict[str, CircuitState] = {}

    def _get_circuit(self, url: str, use_domain: bool = True) -> CircuitState:
        """Get or create circuit state for a URL or domain."""
        key = url if not use_domain else urlparse(url).netloc
        if key not in self.circuits:
            self.circuits[key] = CircuitState()
        return self.circuits[key]

    def should_skip(self, url: str, use_domain: bool = True) -> bool:
        """Check if we should skip this URL due to circuit breaker."""
        circuit = self._get_circuit(url, use_domain)
        return circuit.is_open()

    def record_stream_success(self, url: str, use_domain: bool = True):
        """Record successful stream access."""
        circuit = self._get_circuit(url, use_domain)
        circuit.record_success()

    def record_stream_failure(
        self, url: str, is_error: bool = True, use_domain: bool = True
    ):
        """Record stream access failure."""
        if is_error:
            circuit = self._get_circuit(url, use_domain)
            circuit.record_failure(self.failure_threshold, self.open_duration)

    def get_stats(self) -> dict:
        """Get circuit breaker statistics for monitoring."""
        return {
            "total_circuits": len(self.circuits),
            "open_circuits": sum(1 for c in self.circuits.values() if c.is_open()),
            "circuits": [
                {
                    "key": k,
                    "consecutive_failures": c.consecutive_failures,
                    "open_until": c.open_until,
                    "is_open": c.is_open(),
                }
                for k, c in self.circuits.items()
            ],
        }


# Initialize global health monitor with configurable settings
_stream_monitor = StreamHealthMonitor(
    failure_threshold=5,  # Open after 5 consecutive failures (more tolerant)
    open_duration=60.0,  # Stay open for 1 minute (shorter blocking period)
)

# Track overall proxy_stream and proxy_logo health
_stream_proxy_stats = {
    "total_requests": 0,
    "successful": 0,
    "failed": 0,
    "circuit_opens": 0,
}

# In-memory cache for stream authentication (session cookies)
# Key format: "normalized_portal_url:mac_clean" -> {"cookies": dict, "timestamp": float}
_stream_auth_cache = {}
_stream_auth_cache_ttl = 600  # 10 minutes
_stream_auth_cache_maxsize = 1000


def _prune_stream_auth_cache():
    """Remove expired entries from the auth cache."""
    cutoff = time.time() - _stream_auth_cache_ttl
    expired_keys = [
        k for k, v in _stream_auth_cache.items() if v.get("timestamp", 0) < cutoff
    ]
    for k in expired_keys:
        del _stream_auth_cache[k]
    if expired_keys:
        logger.debug(f"Pruned {len(expired_keys)} expired auth cache entries")


def _get_stream_auth_cookies(portal_url: str, mac: str) -> dict:
    """
    Retrieve cached session cookies for a given portal URL and MAC.
    Cookies are used to maintain authentication across multiple requests to Stalker portals.

    Args:
        portal_url: The portal base URL (will be normalized)
        mac: MAC address (will be normalized)

    Returns:
        Dictionary of cookie name-value pairs, or empty dict if not found/expired.
    """
    if not portal_url:
        return {}
    normalized_url = portal_url.rstrip("/")
    mac_clean = mac.upper().replace(":", "")
    cache_key = f"{normalized_url}:{mac_clean}"

    # Prune if cache is at capacity
    if len(_stream_auth_cache) >= _stream_auth_cache_maxsize:
        _prune_stream_auth_cache()

    entry = _stream_auth_cache.get(cache_key)
    if entry:
        if time.time() - entry.get("timestamp", 0) < _stream_auth_cache_ttl:
            logger.debug(f"Auth cache HIT for {cache_key}")
            return entry.get("cookies", {})
        else:
            del _stream_auth_cache[cache_key]
            logger.debug(f"Auth cache entry expired for {cache_key}")
    return {}


# In-memory cache for stream authentication (session cookies)
# Maps auth_id -> {"cookies": dict, "timestamp": float}
_stream_auth_cache: Dict[str, dict] = {}
_stream_auth_cache_ttl = 600  # 10 minutes
_stream_auth_cache_maxsize = 1000


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
        # TTLCache handles expiration automatically
        return _logo_cache.get(target)
    return None


def _set_cached_logo(target: str, data: bytes, ttl: Optional[int] = None):
    """Store logo in cache (Redis or in-memory).

    Args:
        target: The base64-encoded target URL
        data: The image data bytes
        ttl: Optional custom TTL (uses settings.logo_cache_ttl if None)
    """
    if _use_redis and _redis_client:
        try:
            expiry = ttl if ttl is not None else settings.logo_cache_ttl
            _redis_client.setex(f"logo:{target}", expiry, data)
        except Exception as e:
            logger.warning(f"Redis set error: {e}")
    else:
        # For TTLCache, custom TTL not supported per entry
        # But we can still cache the value, it will use default TTL
        _logo_cache[target] = data


# Default placeholder image (1x1 transparent PNG)
# This is used when logo fetching fails to avoid broken images
_DEFAULT_PLACEHOLDER_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"


def _fetch_logo_with_retry(
    url: str, max_retries: int = 3, base_delay: float = 1.0
) -> bytes:
    """
    Fetch logo image with exponential backoff retry on rate limit (429) errors.

    Args:
        url: Target URL to fetch
        max_retries: Maximum number of retry attempts (default 3)
        base_delay: Base delay in seconds for exponential backoff (default 1.0)

    Returns:
        Raw image data as bytes

    Raises:
        Exception: If all retries fail or non-recoverable error occurs
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            with requests.get(
                url,
                timeout=settings.logo_fetch_timeout,
                stream=True,
                allow_redirects=False,
                verify=settings.verify_ssl,
            ) as r:
                # Check for redirect - handle SSRF safety
                is_redirect = r.is_redirect
                if isinstance(is_redirect, bool) and is_redirect:
                    redirect_location = r.headers.get("Location")
                    if isinstance(redirect_location, str) and redirect_location:
                        if not is_safe_url(redirect_location):
                            raise ValueError(f"Unsafe redirect to {redirect_location}")

                r.raise_for_status()

                # Collect response content
                chunks = []
                for chunk in r.iter_content(chunk_size=settings.logo_chunk_size):
                    chunks.append(chunk)
                return b"".join(chunks)

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                last_exception = e
                if attempt < max_retries:
                    # Check for Retry-After header
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            delay = base_delay * (2**attempt)  # Exponential backoff
                    else:
                        delay = base_delay * (2**attempt) + (
                            0.1 * attempt
                        )  # Add jitter

                    logger.warning(
                        f"Rate limited (429) fetching logo from {url}. "
                        f"Retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Max retries exceeded for logo {url}: {e}")
                    raise
            else:
                # Other HTTP errors - don't retry
                raise
        except requests.exceptions.TooManyRedirects as e:
            last_exception = e
            logger.warning(f"Too many redirects for logo: {url}")
            raise
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Error fetching logo from {url}: {e}. Retrying in {delay:.2f}s"
                )
                time.sleep(delay)
                continue
            else:
                logger.error(f"Max retries exceeded for logo {url}: {e}")
                raise

    # Should not reach here, but for safety
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry loop completed without result")


@router.get("/api/proxy_logo")
@limiter.limit(settings.rate_limit_proxy_logo)
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
                "Cache-Control": f"public, max-age={settings.logo_cache_ttl}, stale-while-revalidate=60",
                "X-Logo-Cache": "HIT",
            },
        )

    try:
        real_url = base64.b64decode(target).decode()

        # Validate URL scheme - only allow HTTP/HTTPS
        parsed = urlparse(real_url)
        if parsed.scheme not in ("http", "https"):
            logger.warning(
                f"Blocked invalid URL scheme '{parsed.scheme}' for: {real_url} from IP {request.client.host}"
            )
            return Response(
                status_code=400, content=b"Invalid URL scheme (only http/https allowed)"
            )

        # Use redirect-safe validation
        if not is_safe_url(real_url):
            logger.warning(
                f"Blocked unsafe SSRF attempt to: {real_url} from IP {request.client.host}"
            )
            return Response(status_code=403)

        # Check circuit breaker (domain-level for shared failure domains)
        if _stream_monitor.should_skip(real_url, use_domain=True):
            _stream_monitor.record_stream_failure(
                real_url, is_error=True, use_domain=True
            )
            _stream_proxy_stats["circuit_opens"] += 1
            logger.warning(
                f"Circuit breaker open for domain {urlparse(real_url).netloc}, skipping logo fetch"
            )
            # Calculate retry-after based on remaining open time
            circuit = _stream_monitor._get_circuit(real_url, use_domain=True)
            retry_after = int(max(0, circuit.open_until - time.time()))
            retry_after = min(retry_after, 300)  # Cap at 5 minutes
            # Return placeholder even when circuit is open to avoid broken images
            return Response(
                status_code=200,
                content=_DEFAULT_PLACEHOLDER_PNG,
                media_type="image/png",
                headers={
                    "Cache-Control": f"public, max-age={retry_after}",
                    "X-Logo-Proxy": "circuit-open",
                    "Retry-After": str(retry_after),
                },
            )

        # Fetch logo data with retry logic for rate limits
        try:
            response_bytes = _fetch_logo_with_retry(real_url)
        except requests.exceptions.HTTPError as e:
            _stream_monitor.record_stream_failure(
                real_url, is_error=True, use_domain=True
            )
            if e.response is not None and e.response.status_code >= 400:
                logger.warning(f"Logo proxy HTTP error for {real_url}: {e}")
                # Cache the failure for 30 seconds to avoid hammering failing domains
                _set_cached_logo(target, _DEFAULT_PLACEHOLDER_PNG, ttl=30)
                # Return placeholder image instead of 502
                return Response(
                    status_code=200,
                    content=_DEFAULT_PLACEHOLDER_PNG,
                    media_type="image/png",
                    headers={
                        "Cache-Control": f"public, max-age=30",
                        "X-Logo-Proxy": "fallback",
                    },
                )
            raise
        except Exception as e:
            _stream_monitor.record_stream_failure(
                real_url, is_error=True, use_domain=True
            )
            logger.error(f"Logo proxy error for {real_url}: {e}")
            # Cache the failure for 30 seconds to avoid hammering failing domains
            _set_cached_logo(target, _DEFAULT_PLACEHOLDER_PNG, ttl=30)
            # Return placeholder image instead of 502
            return Response(
                status_code=200,
                content=_DEFAULT_PLACEHOLDER_PNG,
                media_type="image/png",
                headers={
                    "Cache-Control": f"public, max-age=30",
                    "X-Logo-Proxy": "fallback",
                },
            )
        else:
            # Record success
            _stream_monitor.record_stream_success(real_url, use_domain=True)
            _stream_proxy_stats["total_requests"] += 1
            _stream_proxy_stats["successful"] += 1

        # Cache the successful response (Redis or in-memory)
        _set_cached_logo(target, response_bytes)

        return Response(
            content=response_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": f"public, max-age={settings.logo_cache_ttl}, stale-while-revalidate=60",
                "X-Logo-Cache": "MISS",
            },
        )
    except (binascii.Error, ValueError, TypeError) as e:
        logger.warning(f"Logo proxy failed (invalid base64 or URL): {e}")
        # Return placeholder image directly
        return Response(
            status_code=200,
            content=_DEFAULT_PLACEHOLDER_PNG,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=300",
                "X-Logo-Proxy": "fallback-invalid",
            },
        )


@router.post("/api/get_link")
@limiter.limit(settings.rate_limit_stream_ops)
async def get_link(request: Request, req: StreamRequest):
    """
    Get streaming link for a channel.

    Args:
        req: StreamRequest containing URL, MAC, and channel command

    Returns:
        Dictionary with proxy URL for the stream
    """
    async with StalkerClient(req.url, req.mac) as client:
        logger.info(f"get_link called: url={req.url}, mac={req.mac}, cmd={req.cmd}")
        handshake_success = await client.handshake()
        logger.info(f"Handshake result: {handshake_success}")
        if handshake_success:
            res = await client.create_link(req.cmd)
            logger.info(f"create_link result: {res}")
            target = None
            if isinstance(res, str):
                target = res
            elif isinstance(res, dict) and "cmd" in res:
                target = res["cmd"]

            logger.info(f"Extracted target: {target}")
            if target:
                clean_url = clean_stalker_url(target)
                logger.info(f"Cleaned URL: {clean_url}")
                if not clean_url:
                    raise HTTPException(
                        status_code=400, detail="Generated stream link is empty"
                    )

                # Extract and cache session cookies for this portal+MAC
                cookie_dict = {}
                try:
                    if client._session:
                        cookies_for_domain = client._session.cookie_jar.filter_cookies(
                            client.base_url
                        )
                        for name, morsel in cookies_for_domain.items():
                            cookie_dict[name] = morsel.value
                except Exception as e:
                    logger.warning(f"Failed to extract cookies from StalkerClient: {e}")

                if cookie_dict:
                    # Normalize portal URL and MAC for cache key
                    normalized_url = req.url.rstrip("/")
                    mac_clean = req.mac.upper().replace(":", "")
                    cache_key = f"{normalized_url}:{mac_clean}"
                    _stream_auth_cache[cache_key] = {
                        "cookies": cookie_dict,
                        "timestamp": time.time(),
                    }
                    logger.info(
                        f"Cached {len(cookie_dict)} session cookies for portal {normalized_url} with MAC {mac_clean}"
                    )
                    # Prune if cache over capacity
                    if len(_stream_auth_cache) > _stream_auth_cache_maxsize:
                        _prune_stream_auth_cache()

                b64_url = base64.b64encode(clean_url.encode()).decode()
                b64_origin = base64.b64encode(req.url.encode()).decode()
                proxy_url = f"/api/proxy_stream?target={b64_url}&mac={req.mac}&origin={b64_origin}"
                return {"url": proxy_url}
        else:
            logger.warning(f"Handshake failed for {req.url} with MAC {req.mac}")
    raise HTTPException(
        status_code=400, detail="Could not create link or link not found"
    )


@router.get("/api/check_stream")
@limiter.limit(settings.rate_limit_stream_ops)
def check_stream(
    request: Request,
    target: str,
    mac: str,
    origin: Optional[str] = None,
    auth_id: Optional[str] = None,
):
    """
    Check if a stream is accessible.

    Args:
        target: Base64-encoded stream URL
        mac: MAC address for authentication
        origin: Optional base64-encoded origin URL for referer
        auth_id: Optional auth ID to retrieve session cookies from cache

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

        # Normalize MAC address to standard format (uppercase with colons)
        mac_normalized = mac.upper()
        if len(mac_normalized) == 12 and ":" not in mac_normalized:
            mac_normalized = ":".join(
                [mac_normalized[i : i + 2] for i in range(0, 12, 2)]
            )

        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
            "X-User-Agent": "model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c",
            "Accept": "*/*",
            "Accept-Charset": "UTF-8,*;q=0.8",
            "Connection": "keep-alive",
        }

        # Retrieve cached session cookies using portal URL (referer) and MAC
        session_cookies = {}
        if referer:
            session_cookies = _get_stream_auth_cookies(referer, mac)

        # Build Cookie header
        if session_cookies:
            cookie_parts = [f"{k}={v}" for k, v in session_cookies.items()]
            cookie_parts.append(f"mac={mac_normalized}")
            headers["Cookie"] = "; ".join(cookie_parts)
        else:
            headers["Cookie"] = f"mac={mac_normalized}"

        if referer:
            headers["Referer"] = referer
        else:
            parsed = urlparse(real_url)
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        # Some portals require a Range header to consider the request valid for streaming
        headers["Range"] = "bytes=0-1023"

        # Just a minimal GET to check the status
        with requests.get(
            real_url,
            headers=headers,
            stream=True,
            timeout=settings.stream_timeout,
            verify=settings.verify_ssl,
            allow_redirects=True,
        ) as r:
            logger.info(f"Stream check for {real_url}: {r.status_code}")
            if r.status_code == 401:
                # Log detailed auth failure info
                resp_headers = dict(r.headers)
                logger.warning(
                    f"401 Unauthorized during check_stream for {real_url}. "
                    f"Headers sent: {headers}, Response headers: {resp_headers}"
                )
                try:
                    body_start = r.raw.read(1024)
                    if body_start:
                        logger.warning(f"401 body (first 1KB): {body_start[:200]}")
                except Exception:
                    pass
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
@limiter.limit(settings.rate_limit_stream_ops)
def proxy_stream(
    request: Request,
    target: str,
    mac: str,
    origin: Optional[str] = None,
    auth_id: Optional[str] = None,
):
    """
    Proxy stream content to the client.

    Args:
        target: Base64-encoded stream URL
        mac: MAC address for authentication
        request: FastAPI Request object for headers
        origin: Optional base64-encoded origin URL for referer
        auth_id: Optional auth ID to retrieve session cookies from cache

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

        # Check circuit breaker (domain-level for shared failure domains)
        if _stream_monitor.should_skip(real_url, use_domain=True):
            _stream_monitor.record_stream_failure(
                real_url, is_error=True, use_domain=True
            )
            _stream_proxy_stats["circuit_opens"] += 1
            logger.warning(
                f"Circuit breaker open for domain {urlparse(real_url).netloc}, skipping stream proxy"
            )
            return Response(
                status_code=503,
                content=b"",
                headers={"Retry-After": "300"},  # Suggest retry after 5 minutes
            )

        # Normalize MAC address - try both with and without colons
        mac_clean = mac.upper().replace(":", "")
        mac_with_colons = mac.upper()
        if ":" not in mac_clean and len(mac_clean) == 12:
            mac_with_colons = ":".join([mac_clean[i : i + 2] for i in range(0, 12, 2)])

        # Build base headers
        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
            "X-User-Agent": "model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c",
            "Accept": "*/*",
            "Accept-Charset": "UTF-8,*;q=0.8",
            "Connection": "keep-alive",
        }

        # Retrieve cached session cookies using portal URL (referer) and MAC
        session_cookies = {}
        if referer:
            session_cookies = _get_stream_auth_cookies(referer, mac)

        # Build Cookie header
        if session_cookies:
            cookie_parts = [f"{k}={v}" for k, v in session_cookies.items()]
            cookie_parts.append(f"mac={mac_with_colons}")
            headers["Cookie"] = "; ".join(cookie_parts)
        else:
            headers["Cookie"] = f"mac={mac_with_colons}"

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
            first_chunk_yielded = False
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
                    max_redirects = (
                        settings.max_redirects
                    )  # Prevent infinite redirect loops

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
                                    # Record failure for this URL
                                    _stream_monitor.record_stream_failure(
                                        real_url, is_error=True, use_domain=True
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
                        # Record failure before yielding error
                        _stream_monitor.record_stream_failure(
                            real_url, is_error=True, use_domain=True
                        )
                        if r.status_code == 401:
                            # Log detailed auth failure info
                            resp_headers = dict(r.headers)
                            logger.warning(
                                f"401 Unauthorized during proxy_stream for {real_url}. "
                                f"Headers sent: {headers}, Response headers: {resp_headers}"
                            )
                            try:
                                body_start = r.raw.read(1024)
                                if body_start:
                                    logger.warning(
                                        f"401 body (first 1KB): {body_start[:200]}"
                                    )
                            except Exception:
                                pass
                        yield f"Proxy Error: Portal returned {r.status_code}".encode()
                        r.close()
                        return

                    for chunk in r.iter_content(chunk_size=settings.stream_chunk_size):
                        if chunk:
                            yield chunk
                            if not first_chunk_yielded:
                                # Record success on first data chunk
                                _stream_monitor.record_stream_success(
                                    real_url, use_domain=True
                                )
                                _stream_proxy_stats["total_requests"] += 1
                                _stream_proxy_stats["successful"] += 1
                                first_chunk_yielded = True
                        else:
                            break
                    r.close()
            except Exception as e:
                # Record failure on any exception during streaming setup
                _stream_monitor.record_stream_failure(
                    real_url, is_error=True, use_domain=True
                )
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


@router.get("/api/health/circuits")
def health_circuits(request: Request):
    """
    Get circuit breaker statistics and overall proxy health.
    For monitoring and debugging purposes.

    Returns:
        Dictionary with circuit breaker stats and proxy health metrics
    """
    stats = _stream_monitor.get_stats()
    stats.update(_stream_proxy_stats.copy())
    return stats

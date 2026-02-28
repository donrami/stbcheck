"""
Router for stream-related endpoints.
"""

import base64
import binascii
import logging
from typing import Optional
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models import StreamRequest
from app.services.stalker import StalkerPortal
from app.services.utils import is_safe_url, clean_stalker_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/proxy_logo")
def proxy_logo(target: str):
    """
    Proxy logo images to avoid CORS issues and SSRF vulnerabilities.
    
    Args:
        target: Base64-encoded URL of the logo image
        
    Returns:
        StreamingResponse with the logo image
    """
    try:
        real_url = base64.b64decode(target).decode()
        if not is_safe_url(real_url):
            logger.warning(f"Blocked unsafe SSRF attempt to: {real_url}")
            return Response(status_code=403)
            
        def iter_logo():
            try:
                with requests.get(real_url, timeout=settings.logo_fetch_timeout, stream=True) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=4096):
                        yield chunk
            except Exception as e:
                logger.error(f"Logo proxy error for {real_url}: {e}")

        return StreamingResponse(iter_logo(), media_type="image/png")
    except (binascii.Error, ValueError, TypeError) as e:
        logger.warning(f"Logo proxy failed (invalid base64 or URL): {e}")
        # Return a transparent 1x1 pixel or a nice default image on failure
        return Response(
            status_code=302, 
            headers={"Location": "https://cdn-icons-png.flaticon.com/512/3135/3135673.png"}
        )


@router.post("/api/get_link")
async def get_link(req: StreamRequest):
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
        elif isinstance(res, dict) and 'cmd' in res: 
            target = res['cmd']
        
        if target:
            clean_url = clean_stalker_url(target)
            if not clean_url:
                raise HTTPException(status_code=400, detail="Generated stream link is empty")
                
            b64_url = base64.b64encode(clean_url.encode()).decode()
            b64_origin = base64.b64encode(req.url.encode()).decode()
            proxy_url = f"/api/proxy_stream?target={b64_url}&mac={req.mac}&origin={b64_origin}"
            return {"url": proxy_url}
    raise HTTPException(status_code=400, detail="Could not create link or link not found")


@router.get("/api/check_stream")
def check_stream(target: str, mac: str, origin: Optional[str] = None):
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
        real_url = decoded_bytes.decode('utf-8', errors='ignore')
        
        referer = None
        if origin:
            try:
                referer = base64.b64decode(origin).decode('utf-8', errors='ignore')
            except (binascii.Error, ValueError, TypeError):
                pass  # Invalid base64, continue without referer
            
        if not is_safe_url(real_url):
            return {"status": "error", "code": 403, "message": "Unsafe URL"}
            
        headers = {
            'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
            'X-User-Agent': 'model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c',
            'Cookie': f'mac={mac.upper()}',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }
        
        if referer:
            headers['Referer'] = referer
        else:
            parsed = urlparse(real_url)
            headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"

        # Just a HEAD or a minimal GET to check the status
        with requests.get(
            real_url, 
            headers=headers, 
            stream=True, 
            timeout=settings.request_timeout, 
            verify=False
        ) as r:
            logger.info(f"Stream check for {real_url}: {r.status_code}")
            return {
                "status": "success" if r.status_code < 400 else "error",
                "code": r.status_code,
                "message": f"Portal returned {r.status_code}" if r.status_code >= 400 else "OK"
            }
    except Exception as e:
        logger.error(f"Stream check error: {e}")
        return {"status": "error", "code": 500, "message": str(e)}


@router.get("/api/proxy_stream")
def proxy_stream(target: str, mac: str, request: Request, origin: Optional[str] = None):
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
        real_url = decoded_bytes.decode('utf-8', errors='ignore')
        
        referer = None
        if origin:
            try:
                referer = base64.b64decode(origin).decode('utf-8', errors='ignore')
            except (binascii.Error, ValueError, TypeError):
                pass  # Invalid base64, continue without referer
            
        if not is_safe_url(real_url):
            logger.warning(f"Blocked unsafe SSRF attempt to: {real_url}")
            return Response(status_code=403)
            
        # Try to derive host and referer from the target URL
        headers = {
            'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
            'X-User-Agent': 'model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c',
            'Cookie': f'mac={mac.upper()}',
            'Accept': '*/*',
            'Accept-Charset': 'UTF-8,*;q=0.8',
            'Connection': 'keep-alive'
        }
        
        if referer:
            headers['Referer'] = referer
        else:
            # Fallback: Use the portal root as referer
            parsed = urlparse(real_url)
            headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"

        client_range = request.headers.get('range')
        if client_range:
            headers['Range'] = client_range

        def iterfile():
            try:
                # Use requests.get directly to avoid session cookie pollution
                # Added verify=False to handle portals with SSL issues
                with requests.get(
                    real_url, 
                    headers=headers, 
                    stream=True, 
                    timeout=settings.stream_timeout, 
                    verify=False
                ) as r:
                    upstream_type = r.headers.get('Content-Type', '').lower()
                    real_url_str = str(real_url)
                    logger.info(f"Portal response: {r.status_code} - Type: {upstream_type} - URL: {real_url_str}")
                    
                    if r.status_code >= 400:
                        yield f"Proxy Error: Portal returned {r.status_code}".encode()
                        return

                    for chunk in r.iter_content(chunk_size=128*1024):
                        if chunk:
                            yield chunk
                        else:
                            break
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"Proxy Stream Error: {e}".encode()

        return StreamingResponse(
            iterfile(), 
            media_type='video/MP2T',
            headers={
                "Accept-Ranges": "bytes",
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache"
            }
        )
    except Exception as e:
        logger.error(f"Proxy stream setup error: {e}")
        raise HTTPException(status_code=500, detail="Stream initialization failed")
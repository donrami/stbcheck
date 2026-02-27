import requests
import re
import json
import base64
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import gc
import ipaddress
from urllib.parse import urlparse

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Global Session Pool for better resource management
session_pool = requests.Session()
session_pool.headers.update({
    'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
    'Connection': 'keep-alive'
})

app = FastAPI()

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class StalkerPortal:
    def __init__(self, portal_url, mac_address):
        self.base_url = portal_url.rstrip('/')
        self.mac = mac_address.upper()
        self.session = session_pool # Use global session
        self.token = None
        self.active_path = None
        
        self.headers = {
            'X-User-Agent': 'model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c',
            'Cookie': f'mac={self.mac}',
            'Accept': '*/*',
        }

    def _clean_json(self, text):
        if not text: return ""
        text = text.strip()
        if text.startswith('/*-secure-') and text.endswith('*/'):
            text = text[10:-2]
        js_match = re.search(r'on_success\([^,]+,\s*(\{.*\}|\[.*\])\s*\)', text, re.DOTALL)
        if js_match:
            text = js_match.group(1)
        return text

    def _request(self, params, path=None):
        target_path = path or self.active_path
        if not target_path: return None
        try:
            full_params = {'JsHttpRequest': '1-xml', **params}
            headers = {**self.headers}
            if self.token: headers['Authorization'] = f'Bearer {self.token}'
            
            response = self.session.get(target_path, params=full_params, headers=headers, timeout=10)
            if response.status_code == 404: return 404
            
            # Use chunks for large parsing if possible, but requests .json() is usually okay for RAM if not huge
            try:
                data = response.json()
            except:
                cleaned = self._clean_json(response.text)
                try:
                    data = json.loads(cleaned)
                except:
                    return None

            if isinstance(data, dict):
                if 'js' in data: data = data['js']
                if isinstance(data, dict) and 'result' in data:
                    if isinstance(data['result'], (dict, list)): data = data['result']
            return data
        except Exception as e:
            logger.error(f"Request error for {self.base_url}: {e}")
            return None

    def handshake(self):
        paths_to_try = [f"{self.base_url}/server/load.php", f"{self.base_url}/portal.php", self.base_url]
        for path in paths_to_try:
            res = self._request({'type': 'stb', 'action': 'handshake'}, path=path)
            if res == 404: continue
            if res:
                self.token = res.get('token') if isinstance(res, dict) else res
                if self.token:
                    self.active_path = path
                    return True
        return False

    def get_channels(self):
        return self._request({'type': 'itv', 'action': 'get_all_channels'})

    def get_genres(self):
        return self._request({'type': 'itv', 'action': 'get_genres'})

    def get_itv_groups(self):
        return self._request({'type': 'itv', 'action': 'get_itv_groups'})

    def get_short_genres(self):
        return self._request({'type': 'itv', 'action': 'get_short_genres'})

    def get_all_itv_groups(self):
        return self._request({'type': 'itv', 'action': 'get_all_itv_groups'})

    def get_categories(self):
        return self._request({'type': 'itv', 'action': 'get_categories'})

    def get_itv_info(self):
        return self._request({'type': 'itv', 'action': 'get_itv_info'})

    def create_link(self, cmd):
        return self._request({'type': 'itv', 'action': 'create_link', 'cmd': cmd, 'series': '0', 'forced_storage': '0', 'disable_ad': '0', 'download': '0', 'force_ch_link_check': '0'})

    def get_profile(self):
        return self._request({'type': 'stb', 'action': 'get_profile', 'stb_type': 'MAG250', 'sn': '1234567890123'})

    def get_account_info(self):
        return self._request({'type': 'stb', 'action': 'get_account_info'})

def detect_expiry(data):
    if not isinstance(data, dict):
        return None
    keys = [
        'expire_date', 'end_date', 'max_view_date', 
        'expire_billing_date', 'tariff_expired_date',
        'date_end', 'exp_date'
    ]
    for key in keys:
        val = data.get(key)
        if val and str(val).strip() not in ["", "0000-00-00", "0000-00-00 00:00:00", "null", "None"]:
            return str(val)
    return None

class CheckRequest(BaseModel):
    text: str

class StreamRequest(BaseModel):
    url: str
    mac: str
    cmd: str

class VerifyRequest(BaseModel):
    url: str
    mac: str

def is_safe_url(url_str):
    try:
        parsed = urlparse(url_str)
        if parsed.scheme not in ('http', 'https'):
            return False
        
        hostname = parsed.hostname
        if not hostname:
            return False
            
        # Check if hostname is an IP
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                return False
        except ValueError:
            # It's a domain, potentially check against localhost
            if hostname.lower() in ('localhost', 'localhost.localdomain'):
                return False
        
        return True
    except Exception:
        return False

def clean_stalker_url(raw_url):
    if not raw_url: return None
    u = str(raw_url).strip(" '\"")
    u = re.sub(r'^(ffmpeg|ffrt|solution)\s+', '', u)
    return u

@app.post("/api/check")
async def check_portals(req: CheckRequest):
    logger.info(f"Checking portals for input of length {len(req.text)}")
    pairs = []
    # Improved patterns and block splitting
    url_pattern = r'(?:PORTAL|Panel|Server)\s*[:➤\-]\s*(https?://\S+)'
    mac_pattern = r'(?:MAC|Mac)\s*[:➤\-]\s*([0-9A-Fa-f:]{17})'
    
    blocks = re.split(r'\n\s*\n|╭─•|├─•|╰─•|🛰|📍|🌍|✅|📆|📡', req.text)
    for block in blocks:
        u_match = re.search(url_pattern, block, re.IGNORECASE)
        m_match = re.search(mac_pattern, block, re.IGNORECASE)
        if u_match and m_match:
            pairs.append((u_match.group(1).rstrip('/'), m_match.group(1).upper()))
    
    if not pairs:
        urls = re.findall(url_pattern, req.text, re.IGNORECASE)
        macs = re.findall(mac_pattern, req.text, re.IGNORECASE)
        pairs = list(zip([u.rstrip('/') for u in urls], macs))
    
    # Remove duplicates
    pairs = list(dict.fromkeys(pairs))

    results = []

    try:
        for url, mac in pairs:
            logger.info(f"Analyzing portal: {url} ({mac})")
            portal = StalkerPortal(url, mac)
            if portal.handshake():
                profile = portal.get_profile()
                acc_info = portal.get_account_info()
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
                
                # Cleanup raw data immediately
                del channels_raw
                
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
                
                del genres_raw
                del itv_info
                
                cat_map = {}
                for c in categories:
                    if isinstance(c, dict):
                        cid = str(c.get('id', ''))
                        ctitle = str(c.get('title') or c.get('name') or c.get('label') or cid)
                        if cid: cat_map[cid] = ctitle
                
                processed_channels = []
                for c in all_channels:
                    if not isinstance(c, dict): continue
                    
                    name = str(c.get('name', ''))
                    logo = str(c.get('logo', ''))
                    if logo and logo not in ['None', 'null', '']:
                        logo = re.sub(r'^s:\d+:', '', logo)
                        if logo.startswith('/'): logo = url.rstrip('/') + logo
                        elif not logo.startswith('http'): logo = url.rstrip('/') + '/' + logo
                        logo = f"/api/proxy_logo?target={base64.b64encode(logo.encode()).decode()}"
                    else:
                        logo = None

                    cat_id = "uncategorized"
                    for key in ['tv_genre_id', 'category_id', 'genre_id', 'group_id', 'genre']:
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

                    # Small memory optimization: only keep what's needed
                    processed_channels.append({
                        "id": c.get('id'), 
                        "name": name, 
                        "cmd": c.get('cmd'), 
                        "logo": logo,
                        "category_id": cat_id
                    })
                
                # Cleanup
                del all_channels
                
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
                
                results.append({
                    "url": url,
                    "mac": mac,
                    "channel_count": len(processed_channels),
                    "categories": unique_categories,
                    "channels": processed_channels,
                    "expiry": expiry
                })
                logger.info(f"   -> Found {len(processed_channels)} channels and {len(unique_categories)} categories")
    finally:
        gc.collect() # Force cleanup after heavy portal processing
        
    return results

@app.get("/api/proxy_logo")
def proxy_logo(target: str):
    try:
        real_url = base64.b64decode(target).decode()
        if not is_safe_url(real_url):
            logger.warning(f"Blocked unsafe SSRF attempt to: {real_url}")
            return Response(status_code=403)
            
        # Fast check if it's a valid logo
        r = requests.get(real_url, timeout=3, stream=True)
        r.raise_for_status()
        return StreamingResponse(r.iter_content(chunk_size=1024), media_type=r.headers.get('Content-Type', 'image/png'))
    except:
        # Return a transparent 1x1 pixel or a nice default image on failure
        # For now, let's redirect to a reliable default icon
        return Response(status_code=302, headers={"Location": "https://cdn-icons-png.flaticon.com/512/3135/3135673.png"})

@app.post("/api/get_link")
async def get_link(req: StreamRequest):
    portal = StalkerPortal(req.url, req.mac)
    if portal.handshake():
        res = portal.create_link(req.cmd)
        target = None
        if isinstance(res, str): target = res
        elif isinstance(res, dict) and 'cmd' in res: target = res['cmd']
        
        if target:
            clean_url = clean_stalker_url(target)
            if not clean_url:
                raise HTTPException(status_code=400, detail="Generated stream link is empty")
                
            b64_url = base64.b64encode(clean_url.encode()).decode()
            proxy_url = f"/api/proxy_stream?target={b64_url}&mac={req.mac}"
            return {"url": proxy_url}
    raise HTTPException(status_code=400, detail="Could not create link or link not found")

@app.get("/api/proxy_stream")
def proxy_stream(target: str, mac: str, request: Request):
    try:
        real_url = base64.b64decode(target).decode()
        if not is_safe_url(real_url):
            logger.warning(f"Blocked unsafe SSRF attempt to: {real_url}")
            return Response(status_code=403)
            
        headers = {
            'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
            'Cookie': f'mac={mac.upper()}',
            'Accept': '*/*',
            'Connection': 'keep-alive',
        }

        client_range = request.headers.get('range')
        if client_range:
            headers['Range'] = client_range

        def iterfile():
            # Use the global session pool for the stream as well
            try:
                # Setting stream=True is critical for memory
                with session_pool.get(real_url, headers=headers, stream=True, timeout=15) as r:
                    # Propagate 206 Partial Content or other successful statuses
                    for chunk in r.iter_content(chunk_size=64*1024): # 64KB chunks are often better for low latency
                        if chunk:
                            yield chunk
                        else:
                            break
            except Exception as e:
                logger.error(f"Streaming error: {e}")

        # Minimize overhead by using a fast HEAD check with specific timeout
        content_type = 'video/MP2T'
        try:
            with session_pool.head(real_url, headers=headers, timeout=3) as head:
                content_type = head.headers.get('Content-Type', content_type)
        except:
            pass

        return StreamingResponse(
            iterfile(), 
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache",
                "X-Content-Type-Options": "nosniff"
            }
        )
    except Exception as e:
        logger.error(f"Proxy stream setup error: {e}")
        raise HTTPException(status_code=500, detail="Stream initialization failed")

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

VERIFIED_FILE = "verified_servers.json"

@app.post("/api/verify")
async def verify_server(req: VerifyRequest):
    try:
        verified = []
        try:
            with open(VERIFIED_FILE, "r") as f:
                verified = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        # Check if already exists
        exists = any(v['url'] == req.url and v['mac'] == req.mac for v in verified)
        if not exists:
            verified.append({"url": req.url, "mac": req.mac})
            try:
                with open(VERIFIED_FILE, "w") as f:
                    json.dump(verified, f, indent=4)
            except Exception as e:
                logger.warning(f"Could not save verified servers to file (stateless environment?): {e}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error verifying server: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/verified")
async def get_verified():
    try:
        try:
            with open(VERIFIED_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    except Exception as e:
        logger.error(f"Error getting verified servers: {e}")
        return []

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("index.html", "r") as f:
        return f.read()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

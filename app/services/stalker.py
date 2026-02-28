"""
StalkerPortal client for interacting with IPTV portals.
"""

import json
import re
import logging
import requests

from app.config import settings

logger = logging.getLogger(__name__)

# Default headers for portal communication
PORTAL_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
    'Connection': 'keep-alive'
}


class StalkerPortal:
    """Client for interacting with Stalker/Ministra IPTV portals."""
    
    def __init__(self, portal_url, mac_address):
        self.base_url = portal_url.rstrip('/')
        self.mac = mac_address.upper()
        self.session = requests.Session()
        self.session.headers.update(PORTAL_HEADERS)
        self.token = None
        self.active_path = None
        
        self.headers = {
            'X-User-Agent': 'model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c',
            'Cookie': f'mac={self.mac}',
            'Accept': '*/*',
        }

    def _clean_json(self, text):
        """Clean JSON response from portal wrappers."""
        if not text: 
            return ""
        text = text.strip()
        if text.startswith('/*-secure-') and text.endswith('*/'):
            text = text[10:-2]
        js_match = re.search(r'on_success\([^,]+,\s*(\{.*\}|\[.*\])\s*\)', text, re.DOTALL)
        if js_match:
            text = js_match.group(1)
        return text

    def _request(self, params, path=None):
        """Make a request to the portal."""
        target_path = path or self.active_path
        if not target_path: 
            return None
        try:
            full_params = {'JsHttpRequest': '1-xml', **params}
            headers = {**self.headers}
            if self.token: 
                headers['Authorization'] = f'Bearer {self.token}'
            
            response = self.session.get(
                target_path, 
                params=full_params, 
                headers=headers, 
                timeout=settings.request_timeout
            )
            if response.status_code == 404: 
                return 404
            
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError):
                cleaned = self._clean_json(response.text)
                try:
                    data = json.loads(cleaned)
                except (json.JSONDecodeError, ValueError):
                    return None

            if isinstance(data, dict):
                if 'js' in data: 
                    data = data['js']
                if isinstance(data, dict) and 'result' in data:
                    if isinstance(data['result'], (dict, list)): 
                        data = data['result']
            return data
        except Exception as e:
            logger.error(f"Request error for {self.base_url}: {e}")
            return None

    def handshake(self):
        """Perform handshake with the portal to get auth token."""
        paths_to_try = [
            f"{self.base_url}/server/load.php", 
            f"{self.base_url}/portal.php", 
            self.base_url
        ]
        for path in paths_to_try:
            res = self._request({'type': 'stb', 'action': 'handshake'}, path=path)
            if res == 404: 
                continue
            if res:
                self.token = res.get('token') if isinstance(res, dict) else res
                if self.token:
                    self.active_path = path
                    return True
        return False

    def get_channels(self):
        """Get all channels from the portal."""
        return self._request({'type': 'itv', 'action': 'get_all_channels'})

    def get_genres(self):
        """Get genres/categories from the portal."""
        return self._request({'type': 'itv', 'action': 'get_genres'})

    def get_itv_groups(self):
        """Get ITV groups from the portal."""
        return self._request({'type': 'itv', 'action': 'get_itv_groups'})

    def get_short_genres(self):
        """Get short genres from the portal."""
        return self._request({'type': 'itv', 'action': 'get_short_genres'})

    def get_all_itv_groups(self):
        """Get all ITV groups from the portal."""
        return self._request({'type': 'itv', 'action': 'get_all_itv_groups'})

    def get_categories(self):
        """Get categories from the portal."""
        return self._request({'type': 'itv', 'action': 'get_categories'})

    def get_itv_info(self):
        """Get ITV info from the portal."""
        return self._request({'type': 'itv', 'action': 'get_itv_info'})

    def create_link(self, cmd):
        """Create a streaming link for a channel."""
        return self._request({
            'type': 'itv', 
            'action': 'create_link', 
            'cmd': cmd, 
            'series': '0', 
            'forced_storage': '0', 
            'disable_ad': '0', 
            'download': '0', 
            'force_ch_link_check': '0'
        })

    def get_profile(self):
        """Get STB profile from the portal."""
        return self._request({
            'type': 'stb', 
            'action': 'get_profile', 
            'stb_type': 'MAG250', 
            'sn': '1234567890123'
        })

    def get_account_info(self):
        """Get account info from the portal."""
        res = self._request({'type': 'stb', 'action': 'get_account_info'})
        if not res or res == 404:
            res = self._request({'type': 'stb', 'action': 'get_main_info'})
        return res
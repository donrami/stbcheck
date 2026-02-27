import requests
import json
import sys
import re
from datetime import datetime

import gc

# Global Session
session_pool = requests.Session()
session_pool.headers.update({
    'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
    'Connection': 'keep-alive'
})

class StalkerPortal:
    def __init__(self, portal_url, mac_address):
        # Base cleanup
        self.base_url = portal_url.rstrip('/')
        self.mac = mac_address.upper()
        self.session = session_pool
        self.token = None
        self.active_path = None
        
        # Standard MAG250 Headers
        self.headers = {
            'X-User-Agent': 'model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c',
            'Cookie': f'mac={self.mac}',
            'Accept': '*/*',
        }

    def _request(self, params, path=None):
        target_path = path or self.active_path
        if not target_path:
            return None
            
        try:
            full_params = {'JsHttpRequest': '1-xml', **params}
            if self.token:
                self.headers['Authorization'] = f'Bearer {self.token}'
            
            response = self.session.get(target_path, params=full_params, headers=self.headers, timeout=10)
            if response.status_code == 404:
                return 404
            
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, dict):
                if 'js' in data: data = data['js']
                if isinstance(data, dict) and 'result' in data:
                    if isinstance(data['result'], (dict, list)):
                        data = data['result']
            return data
        except Exception:
            return None

    def handshake(self):
        # Try different common endpoints
        paths_to_try = [
            f"{self.base_url}/server/load.php",
            f"{self.base_url}/portal.php",
            self.base_url if self.base_url.endswith('.php') else f"{self.base_url}/"
        ]
        
        for path in paths_to_try:
            res = self._request({'type': 'stb', 'action': 'handshake'}, path=path)
            if res == 404:
                continue
            
            if res and (isinstance(res, (dict, str))):
                if isinstance(res, dict):
                    self.token = res.get('token')
                else:
                    self.token = res
                
                if self.token:
                    self.active_path = path
                    return True
        return False

    def get_profile(self):
        return self._request({'type': 'stb', 'action': 'get_profile', 'stb_type': 'MAG250', 'sn': '1234567890123'})

    def get_account_info(self):
        # Fallback for some portals
        return self._request({'type': 'stb', 'action': 'get_account_info'})

    def get_channels(self):
        return self._request({'type': 'itv', 'action': 'get_all_channels'})

def parse_bulk_input(text):
    """
    Tries to extract (URL, MAC) pairs using a flexible approach.
    Supports:
    - PORTAL : http://...
    - MAC : 00:1A...
    - Panel ➤ http://...
    - Mac ➤ 00:1A...
    """
    pairs = []
    
    # Improved patterns and block splitting
    url_pattern = r'(?:PORTAL|Panel|Server)\s*[:➤\-]\s*(https?://\S+)'
    mac_pattern = r'(?:MAC|Mac)\s*[:➤\-]\s*([0-9A-Fa-f:]{17})'

    # Try block-based parsing first to keep pairs together
    # Split by decorative separators or double newlines
    blocks = re.split(r'\n\s*\n|╭─•|├─•|╰─•|🛰|📍|🌍|✅|📆|📡', text)
    for block in blocks:
        u_match = re.search(url_pattern, block, re.IGNORECASE)
        m_match = re.search(mac_pattern, block, re.IGNORECASE)
        if u_match and m_match:
            u = u_match.group(1).rstrip('/')
            m = m_match.group(1).upper()
            pairs.append((u, m))
    
    # If no pairs found via blocks, fall back to matching all and zipping
    if not pairs:
        urls = re.findall(url_pattern, text, re.IGNORECASE)
        macs = re.findall(mac_pattern, text, re.IGNORECASE)
        # Clean up URLs
        urls = [u.rstrip('/') for u in urls]
        pairs = list(zip(urls, macs))
        
    return pairs

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

def main():
    print("=== Stalker Portal Bulk Checker ===")
    
    # Check if we should read from file or stdin
    input_text = ""
    if len(sys.argv) > 1 and sys.argv[1].endswith('.txt'):
        try:
            with open(sys.argv[1], 'r') as f:
                input_text = f.read()
        except Exception as e:
            print(f"Error reading file: {e}")
            return
    else:
        print("Tip: You can save the list to 'input.txt' and run: python3 stalker_checker.py input.txt")
        print("Or paste the text below (Ctrl+D when finished):")
        input_text = sys.stdin.read()

    pairs = parse_bulk_input(input_text)
    if not pairs:
        print("[!] No Portal/MAC pairs found in input.")
        return

    print(f"[*] Found {len(pairs)} combos to check.\n")
    results = []

    for i, (url, mac) in enumerate(pairs, 1):
        print(f"[{i}/{len(pairs)}] Checking: {mac} @ {url}")
        portal = StalkerPortal(url, mac)
        
        if portal.handshake():
            profile = portal.get_profile()
            acc_info = portal.get_account_info()
            channels_data = portal.get_channels()
            
            # Try to find expiry in profile or account info
            expiry = detect_expiry(profile) or detect_expiry(acc_info) or "Unlimited"
            
            status = "Unknown"
            if profile and isinstance(profile, dict):
                status = profile.get('status', '1')
            
            channel_count = 0
            if channels_data:
                if isinstance(channels_data, dict) and 'data' in channels_data:
                    channel_count = len(channels_data['data'])
                elif isinstance(channels_data, list):
                    channel_count = len(channels_data)
            
            print(f"    -> [SUCCESS] Channels: {channel_count} | Expiry: {expiry} | Status: {status}")
            results.append({
                'url': url,
                'mac': mac,
                'channels': channel_count,
                'expiry': expiry
            })
            del profile
            del acc_info
            del channels_data
        else:
            print("    -> [FAILED] Handshake failed.")
        
        gc.collect()

    # Sort and show top 3
    results.sort(key=lambda x: x['channels'], reverse=True)
    
    print("\n" + "="*40)
    print("🏆 TOP 3 PORTALS BY CHANNEL COUNT 🏆")
    print("="*40)
    
    for i, res in enumerate(results[:3], 1):
        print(f"{i}. {res['url']} ({res['mac']})")
        print(f"   Channels: {res['channels']}")
        print(f"   Expiry:   {res['expiry']}")
        print("-" * 40)

if __name__ == "__main__":
    main()

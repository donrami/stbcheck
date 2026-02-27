import requests
import re
import json
import base64

class StalkerPortal:
    def __init__(self, portal_url, mac_address):
        self.base_url = portal_url.rstrip('/')
        self.mac = mac_address.upper()
        self.session = requests.Session()
        self.token = None
        self.active_path = None
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
            'X-User-Agent': 'model=MAG250;version=218;sig=6fb2447331356ecca928394477c0500e2630cc3c',
            'Cookie': f'mac={self.mac}',
            'Accept': '*/*',
            'Connection': 'keep-alive'
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
            if self.token: self.headers['Authorization'] = f'Bearer {self.token}'
            response = self.session.get(target_path, params=full_params, headers=self.headers, timeout=10)
            print(f"[DEBUG] Request {params['action']} -> Status {response.status_code}")
            
            try:
                data = response.json()
            except:
                cleaned = self._clean_json(response.text)
                try:
                    data = json.loads(cleaned)
                except:
                    print(f"[DEBUG] Failed to parse JSON for {params['action']}")
                    # print(f"[DEBUG] Raw response: {response.text[:200]}...")
                    return None

            if isinstance(data, dict):
                if 'js' in data: data = data['js']
                if isinstance(data, dict) and 'result' in data:
                    if isinstance(data['result'], (dict, list)): data = data['result']
            return data
        except Exception as e:
            print(f"[DEBUG] Request Error: {e}")
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

    def get_actions(self):
        actions = [
            'get_genres', 'get_itv_groups', 'get_short_genres', 
            'get_all_itv_groups', 'get_itv_info', 'get_categories'
        ]
        results = {}
        for action in actions:
            res = self._request({'type': 'itv', 'action': action})
            results[action] = res
        return results

    def get_channels(self):
        return self._request({'type': 'itv', 'action': 'get_all_channels'})

portal_url = "http://dgt-voetsek.xyz:8080/c"
mac = "00:1A:79:A3:16:BB"

portal = StalkerPortal(portal_url, mac)
if portal.handshake():
    print("[+] Handshake Success!")
    actions = portal.get_actions()
    for action, res in actions.items():
        if res:
            count = len(res) if isinstance(res, (list, dict)) else "N/A"
            sample = str(res)[:200]
            print(f"[*] Action '{action}': Found {count} items. Sample: {sample}")
        else:
            print(f"[!] Action '{action}': Failed/Empty")
            
    channels = portal.get_channels()
    if channels:
        ch_list = []
        if isinstance(channels, dict) and 'data' in channels: ch_list = channels['data']
        elif isinstance(channels, list): ch_list = channels
        
        if ch_list:
            print(f"[+] Found {len(ch_list)} channels.")
            print(f"[*] Sample channel keys: {ch_list[0].keys()}")
            print(f"[*] Sample channel data: {ch_list[0]}")
else:
    print("[-] Handshake Failed.")

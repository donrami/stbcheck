"""
Utility functions for portal detection, URL validation, and text parsing.
"""

import re
import ipaddress
import base64
import logging
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)

# Default headers for portal communication
PORTAL_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
    'Connection': 'keep-alive'
}


def detect_expiry(data, depth=0):
    """
    Recursively search for expiry date in portal response data.
    
    Args:
        data: Dictionary containing portal response data
        depth: Current recursion depth (max 4)
        
    Returns:
        Expiry date string if found, None otherwise
    """
    if not isinstance(data, dict) or depth > 4:
        return None
    
    # Priority keys for expiry dates
    primary_keys = [
        'expire_date', 'end_date', 'max_view_date', 
        'expire_billing_date', 'tariff_expired_date',
        'date_end', 'exp_date', 'expDate', 'expired', 'expires',
        'expiry_date', 'access_end', 'end_date_time', 'valid_until',
        'end', 'to', 'active_until'
    ]
    
    # 1. Check primary keys
    for key in primary_keys:
        val = data.get(key)
        if val is not None:
            val_str = str(val).strip().lower()
            if val_str not in ["", "0", "0000-00-00", "0000-00-00 00:00:00", "null", "none", "false", "unlimited"]:
                return str(val)
    
    # 2. Aggressive search: Check ANY key that contains date/expire/end keywords
    for k, v in data.items():
        if v is None: 
            continue
        
        v_str = str(v).strip()
        if not v_str: 
            continue
        
        # If key suggests a date/expiry and value isn't a known "empty" placeholder
        k_low = str(k).lower()
        if any(x in k_low for x in ['expire', 'end_date', 'valid_until', 'exp_date', 'access_end']):
            if v_str.lower() not in ["0", "0000-00-00", "0000-00-00 00:00:00", "null", "none", "false"]:
                # If it looks like a date (YYYY-MM-DD) or is a timestamp
                if '-' in v_str or (v_str.isdigit() and len(v_str) >= 10):
                    return v_str

    # 3. Check common sub-objects (recursive)
    for sub in ['account_info', 'stb_account', 'active_sub', 'billing', 'profile', 'payment', 'tariff', 'subscription', 'services']:
        sub_data = data.get(sub)
        if isinstance(sub_data, dict):
            res = detect_expiry(sub_data, depth + 1)
            if res:
                return res
        elif isinstance(sub_data, list) and len(sub_data) > 0:
            for item in sub_data:
                if isinstance(item, dict):
                    res = detect_expiry(item, depth + 1)
                    if res:
                        return res
                
    return None


def is_safe_url(url_str):
    """
    Validate URL safety to prevent SSRF attacks.
    
    Args:
        url_str: URL string to validate
        
    Returns:
        True if URL is safe, False otherwise
    """
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


def is_portal_url(url):
    """
    Check if a URL appears to be a Stalker/Ministra portal URL.
    
    Args:
        url: URL string to check
        
    Returns:
        True if URL looks like a portal URL, False otherwise
    """
    u = url.lower().rstrip('/')
    return u.endswith('/c') or '/c/' in u or '/portal.php' in u or '/server/load.php' in u


def extract_portal_mac_pairs(text):
    """
    Extract portal URL and MAC address pairs from text.
    
    Handles various formats including emojis, arrows, and labels.
    
    Args:
        text: Text containing portal URLs and MAC addresses
        
    Returns:
        List of tuples (url, mac_address)
    """
    # Improved patterns to handle emojis, different arrows, and generic labels
    url_pattern = r'(?:PORTAL|Panel|Server|Host|URL|🛰|╭─•)\s*[:➤\- ]+\s*(https?://\S+)'
    mac_pattern = r'(?:MAC|Mac|ID|✅|├─•)\s*[:➤\- ]+\s*([0-9A-Fa-f:]{17}|(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2})'
    
    pairs = []
    
    url_matches = list(re.finditer(url_pattern, text, re.IGNORECASE))
    mac_matches = list(re.finditer(mac_pattern, text, re.IGNORECASE))
    
    if url_matches and mac_matches:
        for u_idx, u_match in enumerate(url_matches):
            u_start = u_match.start()
            url = u_match.group(1).rstrip('/')
            block_start = u_start
            block_end = url_matches[u_idx + 1].start() if u_idx + 1 < len(url_matches) else len(text)
            look_back = 200
            
            found_for_this_url = False
            for m_match in mac_matches:
                m_start = m_match.start()
                if (m_start >= block_start and m_start < block_end) or (m_start < block_start and m_start >= max(0, block_start - look_back)):
                    mac = m_match.group(1).upper().replace('-', ':')
                    pairs.append((url, mac))
                    found_for_this_url = True
            
            if not found_for_this_url:
                best_mac = None
                min_dist = 500
                for m_match in mac_matches:
                    dist = abs(m_match.start() - u_start)
                    if dist < min_dist:
                        best_mac = m_match.group(1).upper().replace('-', ':')
                        min_dist = dist
                if best_mac:
                    pairs.append((url, best_mac))
    
    # Generic fallback for simple lists (URL MAC on same line)
    if not pairs:
        generic_pattern = r'(https?://\S+)\s+((?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2})'
        generic_matches = re.findall(generic_pattern, text, re.IGNORECASE)
        for u, m in generic_matches:
            pairs.append((u.rstrip('/'), m.upper().replace('-', ':')))

    if not pairs:
        urls = [m.group(1).rstrip('/') for m in url_matches]
        macs = [m.group(1).upper().replace('-', ':') for m in mac_matches]
        pairs = list(zip(urls, macs))
    
    # Remove duplicates while preserving order
    return list(dict.fromkeys(pairs))


def clean_stalker_url(raw_url):
    """
    Clean a Stalker URL by removing prefixes like 'ffmpeg', 'ffrt', 'solution'.
    
    Args:
        raw_url: Raw URL string that may contain prefixes
        
    Returns:
        Cleaned URL string or None if input is invalid
    """
    if not raw_url: 
        return None
    u = str(raw_url).strip(" '\"")
    u = re.sub(r'^(ffmpeg|ffrt|solution)\s+', '', u)
    return u
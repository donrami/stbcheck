"""
Standalone CLI: bulk-check Portal/MAC pairs from a file or stdin.

Usage:
    python stalker_checker.py input.txt
    cat list.txt | python stalker_checker.py
"""

import asyncio
import sys

from app.services.stalker_async import check_single_portal
from app.services.text_parser import extract_portal_mac_pairs


def main() -> None:
    print("=== Stalker Portal Bulk Checker ===")

    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1], "r") as f:
                input_text = f.read()
        except OSError as e:
            print(f"Error reading file: {e}")
            return
    else:
        print(
            "Tip: save the list to 'input.txt' and run: "
            "python stalker_checker.py input.txt\n"
            "Or paste text below (Ctrl+D to finish):"
        )
        input_text = sys.stdin.read()

    pairs = extract_portal_mac_pairs(input_text)
    if not pairs:
        print("[!] No Portal/MAC pairs found in input.")
        return

    print(f"[*] Found {len(pairs)} combos to check.\n")

    async def run_all():
        for i, (url, mac) in enumerate(pairs, 1):
            print(f"[{i}/{len(pairs)}] Checking: {mac} @ {url}")
            result = await check_single_portal(url, mac)
            if result["error"]:
                print(f"    ERROR: {result['error']}")
                continue
            print(f"    Status: {result['status']}  Expiry: {result['expiration']}")

    asyncio.run(run_all())


if __name__ == "__main__":
    main()

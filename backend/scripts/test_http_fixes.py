"""Quick test of calculate and poe.ninja fixes via HTTP."""
import json
import sys
import urllib.request
import urllib.parse
import base64
import zlib


POB_CODE_FILE = r"c:\dev\workspace\home-of-exile\examples\keepers\phantasm-summoner\pob.txt"
BASE_URL = "http://localhost:8000"


def read_pob_code() -> str:
    with open(POB_CODE_FILE, encoding='utf-8') as f:
        return f.read().strip()


def post_json(url: str, data: dict) -> dict:
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def main():
    pob_code = read_pob_code()
    print(f"PoB code loaded, length: {len(pob_code)}")

    # Test 1: /api/v1/calculate
    print("\n=== Test 1: /api/v1/calculate ===")
    try:
        result = post_json(f"{BASE_URL}/api/v1/calculate", {"build_code": pob_code})
        stats = result.get("result", result)  # endpoint returns {"result": {...}}
        print(f"  dps: {stats.get('dps', 0)}")
        print(f"  total_dps: {stats.get('total_dps', 0)}")
        print(f"  life: {stats.get('life', 0)}")
        print(f"  energy_shield: {stats.get('energy_shield', 0)}")
        if stats.get('dps', 0) > 0:
            print("  ✓ DPS is non-zero (minion DPS fallback working)")
        else:
            print("  ✗ DPS is still 0")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test 2: poe.ninja direct
    print("\n=== Test 2: poe.ninja API ===")
    try:
        poe_ninja_url = "https://poe.ninja/poe1/api/economy/stash/current/item/overview?league=Keepers&type=UniqueWeapon"
        data = get_json(poe_ninja_url)
        lines = data.get("lines", [])
        print(f"  Items returned: {len(lines)}")
        if lines:
            print(f"  First item: {lines[0].get('name')} = {lines[0].get('chaosValue')} chaos")
            print("  ✓ poe.ninja URL fix working")
        else:
            print("  ✗ No items returned")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\nDone.")


main()

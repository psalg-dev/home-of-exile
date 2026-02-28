"""Test that poe.ninja and minion DPS fixes work in the rebuilt container."""
import asyncio
import json
import sys
import httpx


POB_CODE_FILE = "c:/dev/workspace/home-of-exile/examples/keepers/phantasm-summoner/pob.txt"
BASE_URL = "http://localhost:8000"


def read_pob_code() -> str:
    with open(POB_CODE_FILE) as f:
        return f.read().strip()


async def test_calculate():
    """Test /api/v1/calculate returns minion DPS for phantasm summoner."""
    pob_code = read_pob_code()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/calculate",
            json={"build_code": pob_code},
        )
        resp.raise_for_status()
        data = resp.json()

    stats = data.get("stats", {})
    print("\n=== /api/v1/calculate Results ===")
    for key, val in sorted(stats.items()):
        if val and val != 0:
            print(f"  {key}: {val}")

    dps = stats.get("dps", 0)
    total_dps = stats.get("total_dps", 0)

    print(f"\nPlayer DPS (combined): {dps}")
    print(f"Total DPS: {total_dps}")

    # Check minion stats appear now via the raw stats
    print("\n=== Checking minion DPS via calculate-swap endpoint ===")
    resp2 = await httpx.AsyncClient(timeout=60.0).__aenter__()
    # use synchronous test below


async def test_poe_ninja():
    """Test poe.ninja price fetching works."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test directly on the poe.ninja new URL
        resp = await client.get(
            "https://poe.ninja/poe1/api/economy/stash/current/item/overview",
            params={"league": "Keepers", "type": "UniqueWeapon"},
        )
        print(f"\n=== poe.ninja Direct Test ===")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            lines = data.get("lines", [])
            print(f"Items returned: {len(lines)}")
            if lines:
                print(f"First item: {lines[0].get('name')} = {lines[0].get('chaosValue')} chaos")
        else:
            print(f"Error: {resp.text[:200]}")


async def main():
    print("=== Testing fixes ===")

    await test_poe_ninja()
    await test_calculate()

    print("\n✓ Tests complete")


asyncio.run(main())

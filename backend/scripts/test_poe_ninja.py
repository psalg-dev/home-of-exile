"""Test poe.ninja client in container."""
import asyncio
import sys
sys.path.insert(0, '/app')
from app.services.poe_ninja import PoeNinjaClient

async def test():
    client = PoeNinjaClient()
    prices = await client.get_item_prices('Keepers')
    await client.close()
    if prices:
        items = list(prices.items())[:3]
        print(f'Got {len(prices)} prices. First 3:')
        for name, p in items:
            print(f'  {name}: {p["chaosValue"]} chaos')
    else:
        print('No prices returned - poe.ninja may be failing')
        
    # Also test currency
    client2 = PoeNinjaClient()
    currencies = await client2.get_currency_prices('Keepers')
    await client2.close()
    print(f'Currency prices: {len(currencies)} entries')
    for k, v in list(currencies.items())[:3]:
        print(f'  {k}: {v} chaos')

asyncio.run(test())

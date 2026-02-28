"""
Patch BuildOps.lua in the running container to add minion DPS stats,
then test that they appear for the phantasm summoner build.
"""
import asyncio
import base64
import sys
import zlib
import json
import os
import logging

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/app')

from app.services.luajit_pool import LuaJITWorker, _DEFAULT_STAT_FIELDS


def decode_pob_code(code: str) -> str:
    code = code.strip()
    code = code.replace('-', '+').replace('_', '/')
    padding = (4 - len(code) % 4) % 4
    code += '=' * padding
    compressed = base64.b64decode(code)
    return zlib.decompress(compressed).decode('utf-8')


MINION_PATCH = '''\
  -- Augment with minion output stats for summoner/minion builds
  -- Map virtual field names -> actual field names in env.minion.output
  do
    local minionFieldMap = {
      MinionTotalDPS = "TotalDPS",
      MinionFullDPS = "FullDPS",
      MinionCombinedDPS = "CombinedDPS",
      MinionAverageDamage = "AverageDamage",
      MinionLife = "Life",
      MinionEnergyShield = "EnergyShield",
    }
    local mainEnv = build and build.calcsTab and build.calcsTab.mainEnv
    if mainEnv and mainEnv.minion and mainEnv.minion.output then
      local mo = mainEnv.minion.output
      for _, k in ipairs(wanted) do
        local real = minionFieldMap[k]
        if real and type(mo[real]) ~= "nil" then
          result[k] = mo[real]
        end
      end
    end
  end
'''


async def main():
    with open('/tmp/phantasm.txt') as f:
        raw = f.read().strip()
    xml = decode_pob_code(raw)
    print(f"XML length: {len(xml)}")

    # Read current BuildOps.lua
    with open('/pob/src/API/BuildOps.lua') as f:
        content = f.read()

    # Find insertion point: just before "-- include some metadata if available"
    marker = '  -- include some metadata if available'
    if marker not in content:
        print("ERROR: could not find insertion point in BuildOps.lua")
        return

    if 'MinionTotalDPS' in content:
        print("Patch already applied.")
    else:
        new_content = content.replace(marker, MINION_PATCH + marker)
        with open('/pob/src/API/BuildOps.lua', 'w') as f:
            f.write(new_content)
        print("Patch applied to BuildOps.lua")

    # Now start a worker and test
    worker = LuaJITWorker(0, '/pob/src', 'luajit')
    await worker.start()
    print("Worker started")

    resp = await worker._call('load_build_xml', {'xml': xml})
    print(f"load_build_xml: ok={resp.get('ok')}")

    test_fields = _DEFAULT_STAT_FIELDS + [
        'MinionTotalDPS', 'MinionFullDPS', 'MinionCombinedDPS',
        'MinionAverageDamage', 'MinionLife', 'MinionEnergyShield',
        'ActiveMinionLimit',
    ]
    stats_resp = await worker._call('get_stats', {'fields': test_fields})
    stats = stats_resp.get('stats', {})

    print("\n=== Stats for Phantasm Summoner ===")
    for field in test_fields:
        val = stats.get(field)
        if val is not None:
            print(f"  {field}: {val}")
    print()

    # DPS check
    tDPS = stats.get('TotalDPS', 0)
    mDPS = stats.get('MinionTotalDPS', 0)
    print(f"Player TotalDPS: {tDPS}")
    print(f"Minion TotalDPS: {mDPS}")
    if mDPS and mDPS > 0:
        print("SUCCESS: Minion DPS is non-zero!")
    else:
        print("NOTE: Minion TotalDPS is 0 or not found (may need mainEnv.minion to be set)")

    await worker.stop()


asyncio.run(main())

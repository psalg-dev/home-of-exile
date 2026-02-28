"""Quick diagnostic script to discover what stat keys are available in the
PoB output object for the phantasm summoner (minion) build."""

import asyncio
import json
import sys

sys.path.insert(0, "/app")

from app.services.luajit_pool import LuaJITWorker

CANDIDATES = [
    # standard player stats
    "Life", "EnergyShield", "TotalDPS", "FullDPS", "CombinedDPS", "AverageDamage",
    # common minion naming patterns
    "MinionLife", "MinionCount", "ActiveMinionLimit", "TotalMinionCount",
    "MinionFullDPS", "MinionTotalDPS", "MinionCombinedDPS", "MinionAverageDamage",
    # dot-notation
    "Minion.FullDPS", "Minion.TotalDPS", "Minion.CombinedDPS",
    "Minion.AverageDamage", "Minion.Life",
]


async def test() -> None:
    xml = open("/tmp/phantasm_build.xml").read()
    worker = LuaJITWorker(worker_id=99, pob_src_dir="/pob/src", luajit_cmd="luajit")
    await worker.start()
    print("Worker started")
    
    await worker._call("load_build_xml", {"xml": xml})
    print("Build loaded")
    
    resp = await worker._call("get_stats", {"fields": CANDIDATES})
    stats = resp.get("stats", {})
    print("\n=== Stats returned ===")
    for k, v in sorted(stats.items()):
        if k != "_meta":
            print(f"  {k}: {v}")
    print("\n_meta:", stats.get("_meta"))
    
    await worker.stop()


asyncio.run(test())

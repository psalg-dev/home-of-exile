"""Test calculate_with_swap for the phantasm summoner build."""
import asyncio
import json
import sys
import time

sys.path.insert(0, "/app")

from app.services.luajit_pool import LuaJITWorker

ITEM_TEXT = """Hrimnor's Resolve
Sallow Mask
Quality: 20
Sockets: R-R-R-G
Item Level: 86
+30 to Strength
+25% to Cold Resistance
30% increased Damage over Time
Covered in Frost cannot be Frozen
"""


async def test() -> None:
    xml = open("/tmp/phantasm_build.xml").read()
    worker = LuaJITWorker(worker_id=99, pob_src_dir="/pob/src", luajit_cmd="luajit")
    await worker.start()
    print("Worker started")

    start = time.time()
    try:
        result = await worker.calculate_with_swap(xml, ITEM_TEXT, "Helmet")
        elapsed = time.time() - start
        print(f"Swap calculated in {elapsed:.2f}s")
        print("Baseline TotalDPS:", result["baseline"].get("TotalDPS"))
        print("Modified TotalDPS:", result["modified"].get("TotalDPS"))
        print("Baseline Life:", result["baseline"].get("Life"))
        print("Modified Life:", result["modified"].get("Life"))
        print("Worker still ready:", worker.is_ready)
    except Exception as e:
        elapsed = time.time() - start
        print(f"ERROR after {elapsed:.2f}s: {type(e).__name__}: {e}")

    await worker.stop()


asyncio.run(test())

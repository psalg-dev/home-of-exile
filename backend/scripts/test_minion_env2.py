"""Diagnostic: test what minion DPS fields are accessible from the LuaJIT env."""
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


async def main():
    with open('/tmp/phantasm.txt') as f:
        raw = f.read().strip()

    xml = decode_pob_code(raw)
    print(f"XML decoded OK, length={len(xml)}")

    worker = LuaJITWorker(0, '/pob/src', 'luajit')
    await worker.start()
    print("Worker started")

    # Load build
    resp = await worker._call('load_build_xml', {'xml': xml})
    print(f"load_build_xml ok={resp.get('ok')} err={resp.get('error')}")

    # Get default stats to confirm DPS is 0
    stats_resp = await worker._call('get_stats', {'fields': _DEFAULT_STAT_FIELDS})
    stats = stats_resp.get('stats', {})
    print(f"Default stats: TotalDPS={stats.get('TotalDPS')}, FullDPS={stats.get('FullDPS')}, CombinedDPS={stats.get('CombinedDPS')}")

    # Try various ways to access minion output via the Server.lua 'eval' action (if it exists)
    eval_resp = await worker._call('eval', {'code': 'return {test=1}'})
    print(f"eval supported: {eval_resp.get('ok')}, error: {eval_resp.get('error')}")

    # Try 'get_stats' with special field names that might resolve minion env
    test_fields = ['ActiveMinionLimit', 'MinionTotalDPS', 'MinionFullDPS', 'MinionCombinedDPS']
    test_resp = await worker._call('get_stats', {'fields': test_fields})
    print(f"test_fields stats: {test_resp.get('stats')}")

    # Check if calcsTab has an 'env' or 'mainEnv' field via get_build_info
    info_resp = await worker._call('get_build_info', {})
    print(f"build_info: {info_resp}")

    # Check what actions the server supports
    list_resp = await worker._call('list_actions', {})
    print(f"list_actions: {list_resp}")

    await worker.stop()
    print("Done")


asyncio.run(main())

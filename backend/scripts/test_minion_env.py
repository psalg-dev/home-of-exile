"""Diagnostic: test what minion DPS fields are accessible from LuaJIT."""
import asyncio
import base64
import sys
import zlib

sys.path.insert(0, '/app')

from app.services.luajit_pool import LuaJITWorker


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
    print(f"XML decoded, length: {len(xml)}")

    worker = LuaJITWorker(0, '/pob/src')
    await worker.start()

    # Load the build
    resp = await worker._rpc({'action': 'load_build', 'params': {'xml': xml}})
    print(f"Load build: {resp.get('ok')}")

    # Try to access minion env via a raw Lua eval
    resp2 = await worker._rpc({
        'action': 'eval',
        'params': {'code': '''
local result = {}
if build and build.calcsTab then
  -- Try mainEnv
  local env = build.calcsTab.mainEnv
  if env then
    result.hasMainEnv = true
    if env.minion then
      result.hasMinion = true
      local mo = env.minion.output
      if mo then
        result.hasMinionOutput = true
        result.MinionTotalDPS = mo.TotalDPS
        result.MinionFullDPS = mo.FullDPS
        result.MinionCombinedDPS = mo.CombinedDPS
        result.MinionAverageDamage = mo.AverageDamage
      end
    end
  else
    result.hasMainEnv = false
    -- list available calcsTab fields
    local ct_fields = {}
    for k, _ in pairs(build.calcsTab) do
      table.insert(ct_fields, k)
    end
    table.sort(ct_fields)
    result.calcsTabFields = ct_fields
  end
end
return result
'''}
    })
    print(f"Eval response: {resp2}")

    await worker.stop()


asyncio.run(main())

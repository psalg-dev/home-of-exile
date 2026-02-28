-- Quick test: verify build.calcsTab.mainEnv.minion.output.TotalDPS
-- for the phantasm summoner build
-- Usage: luajit test_minion_check.lua <pob_xml_file>

local arg = arg or {}
local xmlFile = arg[1] or '/tmp/phantasm_decoded.xml'

-- Bootstrap PoB
package.path = '/pob/src/?.lua;/pob/src/?/init.lua;' .. package.path

-- Minimal PoB init (same as HeadlessWrapper.lua in api-stdio mode)
dofile('/pob/src/HeadlessWrapper.lua')

-- Actually, we need to use the full PoB headless API
-- Let's just test via the JSON-RPC protocol by spawning a process and checking

print("This script needs to be run differently - use python test instead")

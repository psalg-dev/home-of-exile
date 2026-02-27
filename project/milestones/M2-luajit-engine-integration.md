# M2: LuaJIT Engine Integration

**Timeline:** Week 2
**Phase:** 1 (Engine-Only MVP)
**Priority:** P0 — MVP Blocker
**PRD Reference:** Technical Architecture (Phase 1), NFR-1 (Performance)

---

## Objective

Integrate the Path of Building calculation engine as a headless LuaJIT subprocess managed by the backend, enabling server-side DPS/EHP calculations for any imported build.

---

## Deliverables

### D2.1: HeadlessWrapper.lua Setup

- [ ] Clone PathOfBuildingCommunity fork into backend Docker image
- [ ] Integrate or adapt `HeadlessWrapper.lua` from [pob-mcp](https://github.com/ianderse/pob-mcp)
- [ ] Verify HeadlessWrapper accepts a PoB XML build via stdin and returns calculated stats via stdout
- [ ] Define JSON protocol for engine communication:
  - **Request:** `{ "action": "calculate", "buildXml": "..." }`
  - **Response:** `{ "stats": { "dps": ..., "life": ..., "es": ..., "resistances": {...} }, "error": null }`

### D2.2: LuaJIT Pool Manager

- [ ] Implement `LuaJITPoolManager` (Python)
  - Spawn 2-4 persistent LuaJIT subprocesses on startup
  - Communicate via stdin/stdout JSON lines
  - Route calculation requests to idle workers (round-robin or shortest-queue)
  - Restart crashed workers automatically
  - Configurable pool size via environment variable (`LUAJIT_POOL_SIZE`)
- [ ] Implement request timeout (15 seconds max per calculation)
- [ ] Health-check: verify workers respond to ping before routing requests

### D2.3: Calculation API Endpoint

- [ ] `POST /api/v1/calculate`
  - **Input:** `BuildData` JSON (from M1 parser output)
  - **Process:** Convert `BuildData` → PoB XML → send to LuaJIT worker → parse response
  - **Output:** `CalculationResult` with full stat breakdown
- [ ] Validate input (reject malformed data before sending to engine)
- [ ] Return structured errors if engine fails or times out

### D2.4: Item Swap Calculation

- [ ] `POST /api/v1/calculate-swap`
  - **Input:** `BuildData` + `{ slot: ItemSlot, newItem: Item }`
  - **Process:** Modify build XML to swap item in specified slot → recalculate → return deltas
  - **Output:** `SwapResult` with delta values (ΔDPS, ΔLife, ΔES, ΔResistances)
- [ ] Support swapping: equipment, gems, and support gems
- [ ] Batch endpoint: accept array of swaps, calculate in parallel across pool

### D2.5: Docker Configuration

- [ ] Extend backend Dockerfile to include:
  - LuaJIT runtime
  - PathOfBuildingCommunity Lua source files
  - HeadlessWrapper.lua
- [ ] Multi-stage build to keep image size reasonable
- [ ] Update Docker Compose to mount PoB data volumes
- [ ] Document engine version pinning strategy

---

## Data Structures

```python
# Python models
class CalculationResult(BaseModel):
    dps: float
    total_dps: float
    life: int
    energy_shield: int
    fire_res: int
    cold_res: int
    lightning_res: int
    chaos_res: int
    armour: int
    evasion: int
    block_chance: float
    spell_block: float

class SwapResult(BaseModel):
    slot: str
    new_item_name: str
    baseline: CalculationResult
    modified: CalculationResult
    deltas: dict[str, float]  # stat_name → delta value
```

---

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| 1 | LuaJIT worker starts and responds to ping within 5 seconds | Integration test |
| 2 | `POST /api/v1/calculate` returns stats for a valid build | Integration test |
| 3 | Calculated DPS matches PoB desktop within ±2% | Manual comparison (5 builds) |
| 4 | Calculated life/ES matches PoB desktop within ±1% | Manual comparison (5 builds) |
| 5 | Pool manager handles concurrent requests (4 simultaneous) | Load test |
| 6 | Crashed worker is restarted automatically within 3 seconds | Fault injection test |
| 7 | Request exceeding 15s timeout returns HTTP 504 | Integration test |
| 8 | `POST /api/v1/calculate-swap` returns correct deltas for an item swap | Integration test |
| 9 | Batch swap endpoint calculates 10 swaps in < 15 seconds | Performance test |
| 10 | Docker image builds successfully with LuaJIT + PoB | CI pipeline |

---

## Dependencies

- **Upstream:** M1 (BuildData types, Docker Compose, FastAPI skeleton)
- **External:** PathOfBuildingCommunity fork (MIT), LuaJIT runtime
- **Key Reference:** [pob-mcp](https://github.com/ianderse/pob-mcp), [pob_wrapper](https://github.com/coldino/pob_wrapper)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| HeadlessWrapper.lua may not support all PoB features | Start with pob-mcp's wrapper; extend as needed; document unsupported features |
| LuaJIT memory leaks on long-running processes | Recycle workers every N calculations (configurable) |
| PoB engine startup time could be slow | Pre-warm pool on server boot; keep workers persistent |
| XML manipulation for item swaps is fragile | Build a robust XML builder with tests for each slot type |

---

## Definition of Done

- LuaJIT pool runs inside Docker alongside FastAPI
- `/api/v1/calculate` returns accurate stats for any valid PoB build
- `/api/v1/calculate-swap` returns correct deltas for item/gem swaps
- ±2% DPS accuracy validated against PoB desktop on at least 5 diverse builds
- Pool handles concurrent load without deadlocks or crashes

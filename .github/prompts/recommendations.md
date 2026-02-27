# Home of Exile — Architecture Recommendations (Rev 3)

> Analysis date: 2026-02-27
> Based on: [app.md](app.md), [research.md](research.md), and deep research (2 rounds)

---

## Preamble: Key Research Findings

The original [research.md](research.md) concluded with **Hybrid A+B** (Rule Engine + LLM). After two
rounds of deeper research, several findings shift the calculus:

1. **Server-side headless PoB already exists.** [pob-mcp](https://github.com/ianderse/pob-mcp)
   runs PoB's Lua calculation engine as a LuaJIT subprocess via `HeadlessWrapper.lua`,
   communicating over stdio or TCP. This eliminates the need for WASM entirely — the
   full PoB engine can run server-side on native LuaJIT with zero compilation step.
   [pob_wrapper](https://github.com/coldino/pob_wrapper) provides a similar Python-driven
   subprocess approach. Both prove headless server-side PoB is a solved problem.

2. **The PoB engine can ground LLM output.** pob-mcp demonstrates this pattern:
   it's an MCP server that lets an LLM interact with PoB's calculation engine.
   Its 44-tool API includes `lua_load_build`, `lua_get_stats`, `add_item`,
   `view_equipment`, `compare_skill_setups`, and `what_if_analysis`. The PoB engine
   can serve as both the recommendation generator AND the hallucination guardrail —
   every LLM claim can be verified against engine output.

3. **No working competitor exists.** [PoePal](https://poepal.com/build-analyzer) attempted the same
   concept (PoB import → analysis → optimization suggestions) but appears to be a dead
   project with a non-functional UI. The core idea validates market demand, but the
   gap remains **wide open** — there is no working tool that does this today.

4. **LLM limitations are well-documented.** LLMs cannot calculate DPS, frequently
   invent items, and conflate "more" vs "increased" multipliers. Qualitative-only
   recommendations are a hard sell to PoE's numbers-obsessed playerbase. But when
   grounded by engine output, the LLM's job reduces to **explanation and synthesis**
   — a task LLMs excel at.

5. **pob-web is production-ready.** [pob.cool](https://pob.cool/) runs the full PoB Lua engine in the
   browser via WASM/Emscripten with 100% calculation compatibility. However, server-side
   LuaJIT is superior for our use case (see comparison below).

6. **app.md requirements not addressed in research.md:**
   - Exactly **5 actionable recommendations** per analysis (not generic "top-N")
   - Must respect **character attributes** (str/dex/int) and **level requirements**
   - **Thumbs up/down feedback loop** that improves recommendations over time
   - **League-awareness** — must stay current when patches drop
   - **Resource aggregation** (secondary purpose, entirely absent from research.md)

---

## Why Server-Side LuaJIT (Not WASM)

The original research proposed browser-side WASM (Approach C). Server-side LuaJIT is
superior for this use case:

| Concern | WASM (browser) | LuaJIT (server) |
|---------|---------------|-----------------|
| Bundle size | 10-15 MB download per user | Zero client impact |
| Parallelism | Limited to Web Workers (2-4) | Scale horizontally with containers |
| Startup time | WASM compilation on each visit | Persistent process, instant |
| Integration | Must extract calc engine from pob-web UI | HeadlessWrapper.lua already exists |
| Proven approach | pob.cool (browser PoB viewer) | pob-mcp, pob_wrapper (headless calc) |
| LLM integration | Requires round-trip to server anyway | Same process / local call |

**pob-mcp** ([github](https://github.com/ianderse/pob-mcp)) already provides:
- `HeadlessWrapper.lua` on the `api-stdio` branch of a PoB fork
- stdio or TCP communication with the Lua process
- 44 tools including: `lua_load_build`, `lua_get_stats`, `add_item`, `view_equipment`,
  `compare_skill_setups`, `what_if_analysis`, `item_recommendations`
- LuaJIT runs natively on Linux (Docker Alpine images available)

---

## Shared Foundation: Server-Side PoB Engine

Both recommendations share a common core. The PoB engine IS the foundation — it
replaces hand-authored rules by encoding 10,000+ game mechanics natively.

### Core Architecture

```
PoB code → POST to API server
    │
    ▼
[Server: LuaJIT PoB Engine]
    ├─ lua_load_build(xml) → baseline stats
    │   {DPS, EHP, life, resists, hit_chance, mana, etc.}
    │
    ├─ For each gear slot:
    │   ├─ Fetch candidates from poe.ninja (archetype common items + priced uniques)
    │   ├─ add_item(candidate) → recalculate → record deltas
    │   └─ Revert
    │
    ├─ For gem links:
    │   ├─ compare_skill_setups(current vs. alternatives)
    │   └─ Record DPS deltas per swap
    │
    ├─ For passives:
    │   ├─ what_if_analysis(add/remove notable nodes)
    │   └─ Record stat deltas
    │
    ├─ Rank all candidates by: Σ(weighted_deltas) / price
    │
    └─ Produce structured result:
        [{slot, current_item, suggested_item, ΔDPS, ΔEHP, Δresists, price, score}]
```

### Shared Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + Vite (TypeScript) |
| PoB parsing | Browser-side: pako + fast-xml-parser (for preview/validation) |
| API server | Python FastAPI or Node.js |
| PoB engine | LuaJIT subprocess (HeadlessWrapper.lua via stdio/TCP) |
| Engine pool | 2-4 persistent LuaJIT processes behind a round-robin dispatcher |
| Candidate source | poe.ninja items + archetype data (cached) |
| Game data | RePoE JSON (attribute/level validation, item metadata) |
| Feedback store | PostgreSQL |
| Deployment | Docker: API container + LuaJIT sidecar container |

---

## Requirement Alignment

| app.md Requirement | Rec 1 (Engine Only) | Rec 2 (Engine + LLM) |
|----|:---:|:---:|
| 5 actionable recommendations | Strong | Strong |
| Respects attributes/level | Strong | Strong |
| Feedback loop | Medium | Medium-Strong |
| League-aware / patch-resilient | Strong | Strong |
| Resource aggregation | Orthogonal | Orthogonal |
| Beginner-friendliness | Medium | Strong |

---

## Recommendation 1 — Server-Side PoB Simulation (Engine Only)

**Core idea**: Run PoB's Lua calculation engine server-side via LuaJIT. Simulate
item/gem/passive swaps against a candidate pool, measure real DPS/EHP deltas, rank
by power-gain-per-divine. Deliver structured, quantitative recommendations with
template-based explanations.

This is the **foundation** that Recommendation 2 builds on. Ship this first.

### How It Works

```
        ... shared engine pipeline (above) ...
            │
            ▼
[Frontend: 5 Recommendation Cards]
    Each shows: stat deltas + item name + price + trade link
    Explanation: template-based strings
```

### Template-Based Explanations

Instead of LLM-generated prose, use parameterized templates:

```typescript
const templates = {
  gear_upgrade: "{item} in your {slot} adds {dps_delta} DPS and {ehp_delta} EHP. " +
                "At ~{price} divines, that's {efficiency} DPS per divine spent.",
  gem_swap:     "Replacing {old_gem} with {new_gem} adds {dps_delta} DPS to your " +
                "{skill_name} setup.",
  passive_node: "Allocating {node_name} adds {dps_delta} DPS. " +
                "Path: {path_description}.",
  resist_fix:   "Your {element} resistance is {current}% (cap: 75%). " +
                "{item} in your {slot} would cap it while adding {dps_delta} DPS."
};
```

### Feedback Loop Design

| Signal | Storage | Use |
|--------|---------|-----|
| Thumbs up/down per recommendation | `(archetype, slot, item_name, deltas, vote, league)` | Adjust candidate ranking weights |
| Implicit signal: user clicked trade link | `(rec_id, clicked)` | Boost actionable recommendations |
| League versioning | All data tagged with league | Auto-expire stale feedback |

### Pros

- **Highest accuracy**: uses the same calculation engine as Path of Building
- **Zero ongoing API cost**: no LLM calls
- **Fastest response**: 3-8 seconds (no LLM round-trip)
- **Simplest architecture**: API server + LuaJIT, nothing else
- **Fully deterministic**: same input → same output every time
- **No degraded mode needed**: the primary mode IS the only mode
- **Works for ALL builds**: engine handles any build, meta or niche
- **No hand-authored rules**: the PoB engine IS the rule engine
- **League-aware**: update PoB fork server-side → all users get new mechanics instantly

### Cons

- **No natural language nuance**: template strings can't explain WHY an upgrade
  matters in context (e.g., "this fixes your accuracy problem which is causing 12%
  of your attacks to miss" — the engine knows the numbers but templates can't reason)
- **Less beginner-friendly**: raw numbers without explanation favor experienced players
- **Rigid output format**: can't adapt explanation style to different player skill levels
- **Harder to communicate complex tradeoffs**: "this item adds DPS but drops your
  cold resistance below cap" requires conditional template logic that grows complex

### Effort: **6-8 weeks**

---

## Recommendation 2 — Engine-Grounded LLM (PoB Engine + GPT)

**Core idea**: Same server-side PoB engine as Recommendation 1, but feed the structured,
quantitative results into an OpenAI GPT model as grounded context. The LLM explains
and synthesizes, but every number and item reference is engine-verified. The PoB engine
acts as both the recommendation generator AND the hallucination guardrail.

This is an **additive layer** on top of Recommendation 1. The engine output schema
does not change — the LLM receives the same structured JSON and produces natural-language
explanations.

### Why OpenAI GPT

| Concern | Notes |
|---------|-------|
| Model selection | GPT-4o or GPT-4o-mini; mini for cost efficiency, full for quality |
| Structured output | OpenAI's `response_format: { type: "json_schema" }` enforces output shape at the API level — stronger guarantee than prompt-only enforcement |
| Cost | GPT-4o-mini: ~$0.002-0.01/analysis; GPT-4o: ~$0.01-0.04/analysis |
| Latency | GPT-4o-mini: ~0.5-1s; GPT-4o: ~1-3s |
| Provider lock-in | Minimal — the LLM is a thin explanation layer over engine data. The structured input/output contract is model-agnostic; swapping providers requires only prompt adaptation, not architectural changes |

The LLM choice is deliberately a **late-binding decision**. Since the LLM receives
fully structured engine output and returns structured JSON, switching between OpenAI,
Anthropic, or any other provider is a configuration change, not a rewrite. The
architecture should abstract the LLM call behind a provider interface.

### How It Works

```
        ... shared engine pipeline (above) ...
            │
            ▼
[Server: OpenAI API call]
    System: "You are an expert PoE advisor. You will receive engine-verified
             upgrade data. Explain each upgrade in beginner-friendly terms.
             Do NOT invent numbers — use only the provided deltas.
             Do NOT reference items not in the provided list."
    User:   structured engine output + build summary + player level
    response_format: JSON schema enforcing
        [{priority, title, explanation, stat_impact, trade_link}]
            │
            ▼
[Frontend: 5 Recommendation Cards]
    Each shows: LLM explanation + engine-verified numbers + trade link + price
```

### The Grounding Guarantee

This architecture creates a **verifiable chain of custody** for every recommendation:

```
Engine calculates → Structured JSON → LLM explains → Output includes both

Player sees:
┌─────────────────────────────────────────────────────────┐
│ ⬆ Upgrade: Helmet → Starkonja's Head                   │
│                                                         │
│ "Starkonja's gives you a big boost to both damage and   │
│  survivability. The evasion rating and life are major    │
│  defensive upgrades, while the attack speed and crit     │
│  directly scale your Lightning Arrow DPS."               │
│                                                         │
│  DPS: +312,847  │  EHP: +4,200  │  Life: +89           │  ← from engine
│  Cost: ~2 div   │  Efficiency: 156k DPS/div             │  ← from poe.ninja
│                                                         │
│  [Search on Trade] [View on Wiki]  [👍] [👎]            │
└─────────────────────────────────────────────────────────┘
```

The LLM cannot hallucinate a DPS number because the numbers come from the engine.
The LLM cannot invent an item because the item list comes from poe.ninja.
The LLM's job is strictly **explanation and synthesis** — a task LLMs excel at.

If the LLM output contradicts the engine data (e.g., claims higher DPS than calculated),
a simple post-processing validation step can flag or reject it.

### Additional Feedback Signals (Beyond Rec 1)

| Signal | Storage | Use |
|--------|---------|-----|
| "Wrong explanation" flag | `(rec_id, user_comment)` | Improve few-shot examples in system prompt |
| Explanation quality rating | `(rec_id, clarity_score)` | A/B test prompt variations |

### Degraded Mode

If the OpenAI API is unavailable or for cost reduction, the system falls back to Rec 1
automatically — structured cards showing stat deltas, item names, and prices with
template explanations. The engine output is self-sufficient; the LLM is an
enhancement, not a dependency.

### Additional Stack (On Top of Shared Foundation)

| Layer | Technology |
|-------|-----------|
| LLM | OpenAI GPT-4o / GPT-4o-mini via `openai` SDK |
| Output enforcement | `response_format: { type: "json_schema" }` for structured output |
| Provider abstraction | Thin interface wrapping LLM call — swap provider without architectural change |
| Validation | Post-processing step: verify LLM output against engine JSON |
| Prompt store | Versioned prompt templates with league-specific context |

### Pros (In Addition to All Rec 1 Pros)

- **Quantitative AND explainable**: engine numbers + LLM prose — best of both worlds
- **Near-zero hallucination**: every claim is grounded in engine output
- **Beginner-friendly**: natural language explanations help new players understand WHY
- **Context-aware explanations**: LLM can reason about interactions (e.g., "this item
  caps your cold resistance which is currently leaving you vulnerable to freeze")
- **Graceful degradation**: falls back to Rec 1 if LLM is unavailable
- **Structured output enforcement**: OpenAI's JSON schema mode guarantees valid output shape
- **Cost-efficient**: GPT-4o-mini at ~$0.002-0.01/analysis keeps costs near zero
- **Provider-agnostic design**: LLM layer is swappable without rearchitecting

### Cons (In Addition to Rec 1 Cons)

- **Server cost**: OpenAI API call adds ~$0.002-0.04/analysis depending on model choice
- **Additional latency**: +0.5-3 seconds for the LLM round-trip
- **OpenAI API dependency**: needs degraded mode (Rec 1 fallback) when API is down
- **Prompt maintenance**: system prompt needs tuning as game mechanics evolve

### Effort: **+2 weeks on top of Rec 1** (total ~8-10 weeks)

---

## Comparative Analysis

### Scoring Matrix (1-5 scale)

| Criterion | Weight | Rec 1 (Engine Only) | Rec 2 (Engine + GPT) |
|-----------|--------|:---:|:---:|
| Accuracy of recommendations | 25% | 5 | 5 |
| Works for all builds | 15% | 5 | 5 |
| Time to MVP | 15% | 4 | 3 |
| League resilience | 10% | 4 | 4 |
| Feedback loop quality | 10% | 3 | 4 |
| Operational cost | 5% | 5 | 3 |
| Competitive differentiation | 10% | 4 | 5 |
| Beginner-friendliness | 10% | 2 | 5 |
| **Weighted total** | | **4.10** | **4.30** |

### Relationship Between Recommendations

```
┌───────────────────────────────────────────────────────────┐
│                   Recommendation 2                        │
│                  (Engine + GPT)                            │
│                                                           │
│   ┌───────────────────────────────────────────────────┐   │
│   │            Recommendation 1                       │   │
│   │           (Engine Only)                            │   │
│   │                                                   │   │
│   │  ┌─────────────────────────────────────────────┐  │   │
│   │  │         Shared Foundation                   │  │   │
│   │  │  PoB parser · LuaJIT engine · poe.ninja     │  │   │
│   │  │  candidate pool · feedback store · API      │  │   │
│   │  └─────────────────────────────────────────────┘  │   │
│   │                                                   │   │
│   │  + Template-based explanations                    │   │
│   │  + Frontend recommendation cards                  │   │
│   └───────────────────────────────────────────────────┘   │
│                                                           │
│   + Claude explanation layer                              │
│   + Post-processing validation                            │
│   + Degraded-mode fallback to Rec 1                       │
│   + Prompt versioning & few-shot management               │
└───────────────────────────────────────────────────────────┘
```

Rec 1 is a strict subset of Rec 2. Building Rec 1 first is not throwaway work —
it becomes the foundation and fallback for Rec 2.

---

## Build Plan

### Phase 1 — Shared Foundation (Weeks 1-4)

| Week | Deliverable |
|------|-------------|
| 1 | PoB code parser (TypeScript, browser-side): base64url → inflate → XML → typed struct. RePoE game data ingestion as static JSON. |
| 2 | LuaJIT engine integration: HeadlessWrapper.lua setup, stdio/TCP communication protocol, Docker container for LuaJIT sidecar. `lua_load_build` + `lua_get_stats` working end-to-end. |
| 3 | Candidate pool pipeline: poe.ninja item fetcher (cached hourly), candidate generation heuristics per slot, attribute/level feasibility filter using RePoE data. |
| 4 | Simulation loop: iterate candidates per slot, swap → recalculate → record deltas → revert. Ranking algorithm. API endpoint returning structured JSON. |

### Phase 2 — Recommendation 1: Ship It (Weeks 5-6)

| Week | Deliverable |
|------|-------------|
| 5 | Frontend: PoB code paste interface, build summary display, 5 recommendation cards with template-based explanations, trade site deep links, poe.ninja price display. |
| 6 | Feedback system: thumbs up/down storage, ranking weight adjustment. Integration tests for full pipeline. Deploy: Vercel (frontend) + Docker on Railway/Render (API + LuaJIT). |

### Phase 3 — Recommendation 2: Add LLM Layer (Weeks 7-8)

| Week | Deliverable |
|------|-------------|
| 7 | OpenAI integration: system prompt design, structured JSON schema output via `response_format`, post-processing validation (LLM output vs. engine data). Provider abstraction interface. Degraded-mode fallback to Rec 1 templates. |
| 8 | Prompt tuning, A/B framework for template vs. LLM explanations, GPT-4o vs. GPT-4o-mini cost/quality comparison, "wrong explanation" feedback signal, deploy. |

---

## Nice-to-Have: Meta-Driven Differential Analysis

A complementary feature (not a core recommendation) that uses poe.ninja's builds
data to show players how their build compares to the meta. This is independent of
the engine-based recommendations and can be added as an additional view.

### When This Adds Value

- **League-launch cold start**: When the PoB engine has no candidates yet (poe.ninja
  item prices are sparse in the first 24-48h), meta comparison still works because
  poe.ninja build snapshots populate quickly from ladder data.
- **"Am I on track?" view**: Players want to see where they stand relative to top
  builds of their archetype — even when they don't need specific upgrade advice.
- **Archetype discovery**: Helps players identify what build archetype they're closest
  to, which can inform upgrade direction.

### How It Works

```
PoB code → decode → build JSON
    │
    ├─ Classify archetype: (main_skill + ascendancy)
    │   e.g. "Lightning Arrow Deadeye"
    │
    ├─ Fetch poe.ninja archetype snapshot
    │   Top 200 characters with same skill+class
    │   → aggregate: common uniques, gem links, keystones, stat ranges
    │
    ├─ Compute differential
    │   For each gear slot:
    │     What does the player have vs. what do 70%+ of top builds use?
    │   For gem links:
    │     Which support gems differ?
    │   For passives:
    │     Which keystones/notables are they missing?
    │   For stats:
    │     Where does the player fall below the archetype median?
    │
    └─ Display as comparison view (not replacement for engine recs)
```

### Limitations

- **Only works for meta builds**: off-meta or experimental builds have no archetype
- **poe.ninja builds API is undocumented**: endpoint shape may change without notice
- **Popularity ≠ optimal**: top builds reflect meta consensus, not best budget advice
- **No quantitative impact**: shows "what" but not "how much DPS/EHP it would add"

### Effort: **~3 weeks** (can be built in parallel, shares PoB parser and poe.ninja cache)

---

## Resource Aggregation (Secondary Purpose)

This is orthogonal to the recommendation engine and should be a separate section of the
app. Recommended scope for MVP:

| Resource | Integration | Notes |
|----------|------------|-------|
| [poewiki.net](https://www.poewiki.net) | Link to relevant wiki pages for recommended items/gems | Deep link by item name |
| [poedb.tw](https://poedb.tw) | Link to mod databases for crafting context | Deep link by base type |
| [poe.ninja](https://poe.ninja) | Embedded price charts for recommended items | iframe or API-driven |
| [pob.cool](https://pob.cool) | "Open in pob.cool" button for the user's build | Pass PoB code via URL |
| [PoB Community Fork](https://pathofbuilding.community/) | Download link + instructions | Static content |
| **Fandom PoE Wiki** | **BLACKLISTED per app.md** | Do not link |

---

## Key References

- [pob-mcp](https://github.com/ianderse/pob-mcp) — 44-tool MCP server for headless PoB via LuaJIT (key enabler)
- [pob_wrapper](https://github.com/coldino/pob_wrapper) — Python subprocess wrapper for headless PoB
- [pob-web / pob.cool](https://github.com/atty303/pob-web) — PoB compiled to WASM, production-deployed (browser alternative)
- [PoePal Build Analyzer](https://poepal.com/build-analyzer) — Defunct prior art (same concept, non-functional)
- [poe.ninja API docs (community)](https://github.com/Davenads/poeninjaAPI-2025) — Endpoint documentation
- [poe.ninja API docs (ayberkgezer)](https://github.com/ayberkgezer/poe.ninja-API-Document) — Additional endpoint docs
- [RePoE](https://github.com/brather1ng/RePoE) — Game data JSON exports
- [5k-mirrors poe-ninja-api](https://github.com/5k-mirrors/misc-poe-tools/blob/master/doc/poe-ninja-api.md) — Builds API specifics
- [poe-ninja-api-manager (npm)](https://www.npmjs.com/package/poe-ninja-api-manager) — Node.js wrapper
- [PathOfBuildingCommunity](https://github.com/PathOfBuildingCommunity/PathOfBuilding) — MIT licensed
- [LuaJIT Docker images](https://hub.docker.com/r/akorn/luajit/) — Alpine-based LuaJIT containers
- [LuaJIT Performance](https://luajit.org/performance.html) — Benchmark data
- [Reducing hallucination via RAG + structured output](https://arxiv.org/html/2404.08189v1) — Academic grounding for the approach

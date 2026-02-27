# PoE Build Recommendation Engine — Research & Architecture Analysis

> Research date: 2026-02-27

---

## Background

Path of Exile 1 has the most complex character build system of any ARPG. Players struggle to
identify what to upgrade next on their character. The goal is a **webapp** where players paste a
Path of Building (PoB) export code and receive ranked, actionable upgrade recommendations.

---

## PoB Export Format

The export code uses a 3-step pipeline:

1. **Compress**: Deflate (zlib) the XML build document
2. **Encode**: Base64 with URL-safe substitutions (`+` → `-`, `/` → `_`)
3. **Decode in reverse**: Replace `-`/`_`, Base64-decode, inflate → XML

The XML structure:

| Section | Contents |
|---------|----------|
| `<Build>` | Class, ascendancy, level, calculated stats (life, DPS, etc.) |
| `<Spec>` | Passive tree node allocations (comma-separated hash list) |
| `<Items>` | All equipped items and item sets |
| `<Skills>` | Gem setups (active + support gems, links) |
| `<Config>` | Combat config (boss type, flasks active, etc.) |
| `<Notes>` | Free-text user notes |

### Existing Parsers

| Language | Library | Notes |
|----------|---------|-------|
| Python | [`ppoelzl/PathOfBuildingAPI`](https://github.com/ppoelzl/PathOfBuildingAPI) | `pip install pobapi`, extracts stats, skills, items |
| Python | [`coldino/pob_wrapper`](https://github.com/coldino/pob_wrapper) | Drives PoB as a subprocess for full engine access |
| JavaScript | None off-the-shelf | Easy to implement: pako (inflate) + fast-xml-parser |
| Any | [pob-mcp](https://github.com/ianderse/pob-mcp) | 44-tool MCP bridge to PoB's Lua calculation engine |

**PoB Community Fork**: MIT licensed at
[PathOfBuildingCommunity/PathOfBuilding](https://github.com/PathOfBuildingCommunity/PathOfBuilding).
The actual Lua calculation engine can be compiled to WASM via
[atty303/pob-web](https://github.com/atty303/pob-web) for browser use.

---

## Available Data Sources

| Source | What it provides | Format | Update cadence |
|--------|-----------------|--------|----------------|
| [`brather1ng/RePoE`](https://github.com/brather1ng/RePoE) | Item mods, base items, gems, stats — full game data export | JSON files | Community-maintained per patch |
| GGG passive tree export | All passive nodes, connections, stats | JSON | Official, per league |
| [`poe.ninja`](https://poe.ninja) | Item/currency prices, top meta build snapshots | REST API | Real-time per league |
| [`poedb.tw`](https://poedb.tw) | Item DB, mod DB, skill DB | JSON API | Per patch |
| [`poewiki.net`](https://www.poewiki.net) | Mechanics docs, item descriptions | Cargo/MediaWiki API | Community-maintained |
| GGG official API | Character data, trade listings | REST + OAuth | Real-time, rate-limited to 4 req/s |

**Key gap**: No existing tool combines PoB parsing + upgrade gap analysis + trade pricing into
structured recommendations. PoB's own "Power Report" covers passive nodes only; nothing exists
for gear or gem upgrade recommendations at this depth.

---

## Approach A — LLM-as-Brain (RAG + Claude)

**Concept**: Parse PoB code → semantic knowledge base over game data → Claude reasons over
both to generate natural-language recommendations.

**Stack**: React/Next.js · Python FastAPI · Claude API · Vector DB (Chroma/Pinecone) · RePoE JSON

### Flow

```
PoB code → decode XML → build JSON
     ↓
Vector DB: retrieve relevant mods/mechanics for the build's main skill
     ↓
Claude prompt: current build + retrieved context → ranked recommendations
     ↓
Optional: poe.ninja price lookup for mentioned items
```

### Pros
- Fastest to build (2–4 weeks)
- Handles niche/unusual builds gracefully — no rules needed for edge cases
- Natural language output is polished and explanatory
- Low maintenance: LLM adapts across patches without rule updates

### Cons
- LLM can hallucinate game mechanics (mitigated by RAG + structured prompting)
- No quantitative DPS math — recommendations are qualitative
- Ongoing API cost (~$0.01–0.05 per analysis with Claude Sonnet)
- Quality tied to prompt engineering and RAG retrieval quality

**Effort**: Medium · 2–4 weeks MVP

---

## Approach B — Rule-Based Expert System

**Concept**: Encode ~50–100 expert rules as deterministic checks against well-defined thresholds.
Parse build → evaluate rules → output tiered checklist.

**Stack**: React/Next.js · Python or Node.js · RePoE JSON · curated threshold config

### Example Rules

| Rule | Condition | Recommendation |
|------|-----------|----------------|
| Life floor | Max life < 4000 at level 80+ | Prioritise life on gear / passive tree |
| Uncapped resistances | Any resist < 75% | Cap `{element}` resistance (currently `{value}%`) |
| Missing movement skill | No movement skill gem active | Add Flame Dash / Whirling Blades / etc. |
| Gem link quality | Main skill < 5L | Upgrade to 5-link or 6-link |
| Accuracy rating | Hit chance < 95% | Add accuracy on gear or Precision aura |
| Mana sustain | Unreserved mana < 300 | Review aura reservations or add mana regen |

Rules are tiered: **Critical** (game-breaking) → **Important** → **Nice-to-have**.

### Pros
- Deterministic and fully explainable — no AI surprises
- Zero ongoing cost
- Ruleset can be open-sourced and community-improved
- Execution < 100 ms

### Cons
- Rules require deep expert knowledge to author correctly
- High maintenance burden after major patches
- Cannot reason about complex interactions (e.g., how a specific unique changes thresholds)
- Brittle for builds that violate common assumptions

**Effort**: High upfront knowledge engineering · 3–6 weeks for a meaningful ruleset

---

## Approach C — Headless PoB Simulation Engine

**Concept**: Run PoB's actual Lua calculation engine in the browser (via WASM). Simulate item
swaps from a curated pool, measure DPS/EHP deltas, price with poe.ninja, rank by
power-gain-per-currency.

**Stack**: React/Next.js · [pob-web WASM](https://github.com/atty303/pob-web) · RePoE JSON · poe.ninja API

### Flow

```
PoB code → pob-web (WASM) → baseline DPS + EHP
     ↓
For each gear slot:
  → enumerate candidate upgrades from item pool
  → swap into engine → record delta DPS / delta EHP
     ↓
Score = Δstat / item_price_in_div
Sort descending → return top-N upgrade recommendations
```

### Pros
- **Highest accuracy**: uses the same calculation engine as PoB — no approximations
- Fully quantitative: "This Stygian Vise adds 847k DPS and costs 2 divine"
- Works automatically for all builds regardless of complexity or mechanics
- No domain knowledge encoding required

### Cons
- pob-web is 8–15 MB WASM; complex to integrate on a server
- Must maintain a curated item candidate pool per slot
- Simulation of many item swaps can be slow (needs batching / web workers)
- pob-web may lag 1–2 weeks behind PoB Community Fork after patches

**Effort**: High · 4–8 weeks · Significant integration complexity

---

## Final Recommendation: Hybrid A + B

**Rule engine as backbone, Claude for explanation quality.**

Start with Approach B's deterministic rule checks for the high-confidence, universal problems.
Feed those structured results into Claude (Approach A) for ranked, personalized, natural-language
output. Save the WASM simulation engine (Approach C) for a v2 milestone.

### Why This Combination

| Concern | How it's addressed |
|---------|-------------------|
| Hallucination risk | Claude receives structured rule output, not a cold reasoning task |
| Maintenance | Rules cover stable universal checks; LLM absorbs edge-case nuance |
| Accuracy | Rules are ground-truth for common cases; LLM fills gaps |
| Cost | ~$0.01–0.02/query (most work is done by the cheap rule engine) |
| Time to ship | 3–5 weeks vs 8+ weeks for full simulation |

### Recommended Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | React + Vite (TypeScript) | SPA, fast, no SSR complexity |
| PoB parsing | In-browser JS: pako + fast-xml-parser | No backend roundtrip needed |
| Backend | Python FastAPI | Simple async, great ecosystem for data work |
| Rule engine | Python (plain functions + config YAML) | Testable, community-editable |
| LLM | Claude Sonnet (claude-sonnet-4-6) | Best quality/cost ratio |
| Game data | RePoE JSON (static assets, bundled) | No DB needed for MVP |
| Pricing | poe.ninja API (cached hourly server-side) | Avoid CORS, control rate limits |

### Architecture

```
User pastes PoB code
        │
        ▼
[Browser: JS PoB decoder]
  base64url → inflate → XML → build JSON
  {class, level, passives[], gear[], gems[], stats{}}
        │
        ├─────────────────────────────────┐
        ▼                                 ▼
[Backend: Rule Engine]           [poe.ninja price cache]
  ~60 rules evaluated              (refreshed hourly)
  → [{severity, category,
      flag, context}]
        │
        ▼
[Backend: Claude API call]
  System: expert PoE advisor + RePoE game context
  User:   flagged issues + build summary + prices
  Output: JSON [{priority, title, explanation,
                  estimated_impact, trade_link}]
        │
        ▼
[Frontend: Recommendation Cards]
  Sorted by priority
  Each card: issue · recommendation · impact ·
             trade site deep link · wiki reference
```

---

## MVP Build Plan

### Week 1 — Data Pipeline
- Write TypeScript PoB code parser (browser-side): base64url → inflate → XML → typed struct
- Download and structure RePoE game data (mods, base items, gems) as static JSON
- Write poe.ninja price-fetcher with hourly server-side cache

### Week 2 — Rule Engine
- Implement ~30 core rules: resistance caps, life floor, gem links, accuracy, mana, movement skill
- Write unit tests for each rule against known builds
- Structure rule output schema for LLM consumption

### Week 3 — LLM Integration
- Design system prompt: expert PoE advisor persona with injected RePoE context
- Define structured output schema (JSON with priority, title, explanation, impact, trade_link)
- Wire Claude API call: rule outputs + build summary → recommendations

### Week 4 — Frontend
- Build PoB code paste interface (textarea + decode button)
- Design recommendation card components (severity colour coding, trade links)
- Add poe.ninja trade deep-links for suggested item types

### Week 5 — Polish + Launch
- Add cost-effectiveness display (estimated price from poe.ninja)
- Write integration tests for parse → rule → LLM pipeline
- Deploy: Vercel (frontend) + Railway or Render (FastAPI backend)

---

## Future Milestones

| Version | Feature |
|---------|---------|
| v2 | Passive tree analysis: pob-web WASM for quantitative DPS delta per node |
| v2 | poe.ninja archetype comparison: "your EHP is bottom 30% for your build type" |
| v3 | Headless PoB simulation (Approach C): simulate item swaps for concrete numbers |
| v3 | Crafting paths: Craft of Exile integration for suggested crafting strategies |
| v3 | Build history: track recommendations over time as character improves |

---

## Project Structure

```
poe-recommender/
├── frontend/
│   ├── src/
│   │   ├── lib/
│   │   │   └── pobParser.ts          # PoB code decoder (base64 → inflate → XML)
│   │   ├── components/
│   │   │   ├── PobInput.tsx          # Code paste UI
│   │   │   ├── RecommendationCard.tsx
│   │   │   └── BuildSummary.tsx
│   │   ├── types/
│   │   │   └── build.ts              # TypeScript types for parsed build data
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── app/
│   │   ├── rules/
│   │   │   ├── __init__.py
│   │   │   ├── resistances.py
│   │   │   ├── survivability.py
│   │   │   ├── gem_links.py
│   │   │   └── thresholds.yaml       # Configurable threshold values
│   │   ├── llm/
│   │   │   ├── claude_client.py      # Anthropic SDK wrapper
│   │   │   └── prompts.py            # System + user prompt templates
│   │   ├── data/
│   │   │   ├── repoe/                # RePoE JSON files (static)
│   │   │   └── prices.py             # poe.ninja cache layer
│   │   ├── models.py                 # Pydantic request/response schemas
│   │   └── main.py                   # FastAPI entry point
│   ├── tests/
│   │   └── test_rules.py
│   └── requirements.txt
└── data-pipeline/
    └── fetch_repoe.py                # One-time data ingestion script
```

---

## Key References

- [PathOfBuildingCommunity/PathOfBuilding](https://github.com/PathOfBuildingCommunity/PathOfBuilding) — MIT licensed
- [ppoelzl/PathOfBuildingAPI](https://github.com/ppoelzl/PathOfBuildingAPI) — Python PoB parser
- [brather1ng/RePoE](https://github.com/brather1ng/RePoE) — Game data JSON exports
- [atty303/pob-web](https://github.com/atty303/pob-web) — PoB compiled to WASM
- [poe.ninja API](https://poe.ninja) — Economy data and meta build snapshots
- [DeepWiki: PoB Import/Export](https://deepwiki.com/PathOfBuildingCommunity/PathOfBuilding/5.5-import-and-export)

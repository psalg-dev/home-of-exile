# Product Requirements Document: Home of Exile

**Version:** 1.0  
**Date:** February 27, 2026  
**Status:** Draft

---

## Executive Summary

**Home of Exile** is a web application designed to help Path of Exile players optimize their character builds through data-driven, actionable recommendations. Players import their Path of Building (PoB) character data and receive exactly 5 prioritized upgrade suggestions backed by quantitative analysis and clear explanations.

The application addresses a critical pain point in Path of Exile's notoriously complex build system: players struggle to identify which upgrades will provide the most value for their current progression stage. By combining the PoB calculation engine with modern recommendation algorithms, Home of Exile bridges the gap between beginner confusion and expert-level optimization.

---

## Product Vision & Goals

### Vision Statement

Empower Path of Exile players of all skill levels to make informed character progression decisions through accurate, actionable, and contextually appropriate upgrade recommendations.

### Primary Goals

1. **Reduce build optimization friction** — Help players identify their next 5 best upgrades in under 10 seconds
2. **Democratize expert knowledge** — Make top-tier optimization accessible to beginners and veterans alike
3. **Maintain accuracy across leagues** — Stay current with game updates without manual rule maintenance
4. **Build player trust** — Deliver quantitatively verifiable recommendations that players can act on immediately

### Secondary Goals

1. **Aggregate scattered resources** — Provide a centralized hub for PoE-related tools and documentation
2. **Learn from player feedback** — Continuously improve recommendations through thumbs-up/down signals

---

## Target Audience

### Primary Users

| Segment | Characteristics | Pain Points |
|---------|----------------|-------------|
| **New Players** (Levels 1-70) | First league, overwhelmed by complexity | Don't know what stats to prioritize; can't assess upgrade value |
| **Mid-Progression** (Levels 70-90) | Understand basics, optimizing for endgame | Analysis paralysis with too many upgrade options; budget constraints |
| **Experienced Players** (Levels 90-100) | Min-maxing for specific content | Need marginal gain analysis; want cost-efficiency data |

### Out of Scope (For MVP)

- SSF (Solo Self-Found) players — recommendations assume trade league access
- Build creators theorycrafting from scratch — tool is for optimization, not creation
- Console players — GGG API and PoB are PC-focused

---

## Feature Requirements

### FR-1: Path of Building Import

**Priority:** P0 (MVP Blocker)

**Description:** Users can paste a PoB export code and have it parsed into structured build data.

**Acceptance Criteria:**
- Accepts base64url-encoded PoB export codes
- Successfully decodes (inflate + XML parse) all valid PoB codes from Community Fork v2.40+
- Extracts: character class, ascendancy, level, passive tree, equipped items, gem links, calculated stats (life, DPS, resistances, etc.)
- Displays build summary (character name, level, main skill, life/ES pool, DPS)
- Handles parsing errors gracefully with clear error messages

**Technical Notes:**
- Browser-side parsing using pako (deflate) + fast-xml-parser
- No server round-trip needed for parsing

---

### FR-2: Recommendation Engine

**Priority:** P0 (MVP Blocker)

**Description:** Generate exactly 5 actionable, prioritized upgrade recommendations based on character analysis.

**Acceptance Criteria:**
- Returns exactly 5 recommendations sorted by priority
- Each recommendation includes:
  - **What to change** (item slot, gem, passive nodes)
  - **Specific suggestion** (item name, gem name, keystones)
  - **Quantitative impact** (ΔDPS, ΔEHP, Δresistances, Δlife)
  - **Cost** (price in divine orbs from poe.ninja)
  - **Efficiency score** (stat gain per divine spent)
  - **Explanation** (why this upgrade matters)
  - **Trade link** (direct link to poe.trade or official trade site)
- Respects character constraints:
  - **Attribute requirements** (str/dex/int) for suggested items
  - **Level requirements** (cannot suggest items player cannot equip)
  - **Socket requirements** (considers available links)
- League-aware: pulls item data from current active league

**Recommendations Must Cover:**
1. Critical issues (uncapped resistances, low life pool)
2. Power multipliers (DPS upgrades, gem link improvements)
3. Defensive gaps (low block/dodge, missing defensive layers)
4. Quality-of-life (movement skills, mana sustain)
5. Cost-efficient upgrades (best value for currency spent)

---

### FR-3: Recommendation Feedback Loop

**Priority:** P1 (High)

**Description:** Users can rate recommendations to improve future suggestions.

**Acceptance Criteria:**
- Each recommendation has thumbs-up 👍 and thumbs-down 👎 buttons
- Feedback is stored with context: `(archetype, slot, item, deltas, vote, league)`
- Implicit signals tracked: trade link clicks
- Feedback influences future recommendation ranking weights
- League-tagged data auto-expires when a new league starts

**Technical Notes:**
- PostgreSQL storage
- Batch analysis of feedback to adjust archetype-specific weights weekly

---

### FR-4: Resource Aggregation

**Priority:** P2 (Nice-to-Have)

**Description:** Centralized links to authoritative PoE resources.

**Acceptance Criteria:**
- Context-aware deep links for recommended items:
  - **poewiki.net** — Item/mechanic documentation
  - **poedb.tw** — Mod database for crafting context
  - **poe.ninja** — Price graphs for recommended items
  - **pob.cool** — "Open in pob.cool" button with PoB code via URL
- Static resource hub page with categorized links to:
  - Path of Building Community Fork download
  - RePoE GitHub
  - poe.ninja build explorer
  - Trading tools (official trade, Awakened PoE Trade)

**Blacklist:**
- **Fandom PoE Wiki** — Do not link (per app.md specification)

---

### FR-5: League-Awareness

**Priority:** P1 (High)

**Description:** Recommendations stay current when new leagues/patches release.

**Acceptance Criteria:**
- League selector in UI (dropdown: current league, previous league, Standard)
- poe.ninja price data fetched per selected league
- PoB engine updated server-side within 48 hours of new league launch
- Feedback data segregated by league (3.27, 3.28, etc.)
- Recommendations reflect new uniques/skills introduced in current league

**Technical Notes:**
- PoB engine update process: pull latest Community Fork commit, rebuild Docker image, redeploy
- poe.ninja API cache refreshed hourly per league

---

## Non-Functional Requirements

### NFR-1: Performance

| Metric | Target |
|--------|--------|
| PoB code parsing (client-side) | < 1 second |
| Recommendation generation (server-side) | < 8 seconds (P50), < 15 seconds (P95) |
| Page load time | < 2 seconds |
| API response time | < 500ms for cached data |

### NFR-2: Accuracy

- Recommendation DPS/EHP calculations must match Path of Building Community Fork within ±2%
- Suggested items must be equippable by the character (100% attribute/level validation)
- Price data must be current within 1 hour of poe.ninja snapshot

### NFR-3: Scalability

- Support 100 concurrent recommendation requests
- Handle 10,000 recommendations/day with current architecture
- Horizontal scaling path for LuaJIT engine pool

### NFR-4: Reliability

- 99% uptime SLA (excludes scheduled maintenance)
- Graceful degradation: if LLM API is down, fall back to template-based explanations
- Rate limiting: max 10 recommendations per IP per hour (prevent abuse)

### NFR-5: Maintainability

- Update PoB engine version server-side without client changes
- RePoE game data ingestion via automated script (triggered on patch days)
- No hard-coded game mechanics (all data-driven via RePoE/PoB engine)

---

## Technical Architecture

### Recommended Approach: Engine-Grounded LLM (Phased)

#### Phase 1: Engine-Only (Weeks 1-6) — MVP

**Core Components:**

```
[Browser]
  └─ PoB Parser (pako + fast-xml-parser)
      └─ POST /analyze → API Server

[API Server: Python FastAPI]
  ├─ LuaJIT Pool Manager (2-4 persistent processes)
  │   └─ HeadlessWrapper.lua (PoB calculation engine)
  ├─ Candidate Generator
  │   ├─ poe.ninja item fetcher (cached hourly)
  │   ├─ RePoE attribute/level validator
  │   └─ Archetype heuristics
  ├─ Simulation Loop
  │   └─ For each slot: swap item → calculate deltas → rank
  └─ Template-Based Explainer
      └─ Returns 5 structured recommendations

[PostgreSQL]
  └─ Feedback storage (votes, clicks, league context)
```

**Tech Stack:**

| Layer | Technology |
|-------|-----------|
| Frontend | React + Vite (TypeScript) |
| API Server | Python FastAPI |
| PoB Engine | LuaJIT subprocess (HeadlessWrapper.lua via stdio) |
| Game Data | RePoE JSON (static files) |
| Pricing | poe.ninja API (cached hourly) |
| Feedback Store | PostgreSQL |
| Deployment | Vercel (frontend) + Docker on Render/Railway (backend) |

**Why LuaJIT (Server-Side) Not WASM (Browser-Side)?**

| Concern | WASM | LuaJIT |
|---------|------|--------|
| Bundle size | 10-15 MB download per user | Zero client impact |
| Parallelism | Limited to Web Workers (2-4) | Scale horizontally |
| Startup time | WASM compilation on each visit | Persistent process |
| Integration | Extract calc engine from pob-web | HeadlessWrapper.lua exists ([pob-mcp](https://github.com/ianderse/pob-mcp)) |
| LLM integration | Requires server round-trip anyway | Same process |

**Template-Based Explanations (Phase 1):**

```typescript
const templates = {
  gear_upgrade: "{item} in your {slot} adds {dps_delta} DPS and {ehp_delta} EHP. At ~{price} divines, that's {efficiency} DPS per divine spent.",
  gem_swap: "Replacing {old_gem} with {new_gem} adds {dps_delta} DPS to your {skill_name} setup.",
  resist_fix: "Your {element} resistance is {current}% (cap: 75%). {item} would cap it while adding {dps_delta} DPS."
};
```

#### Phase 2: LLM Layer (Weeks 7-8) — Enhancement

**Additional Components:**

```
[API Server]
  └─ LLM Service (OpenAI GPT-4o-mini)
      ├─ Receives: structured engine output + build summary
      ├─ System prompt: "You are a PoE expert. Explain upgrades using only provided numbers."
      ├─ Output: JSON schema enforced via `response_format`
      └─ Validation: LLM output vs. engine data (reject hallucinations)
```

**Pros:** Natural language explanations, beginner-friendly, context-aware reasoning  
**Cons:** +$0.002-0.01/analysis, +0.5-1s latency  
**Fallback:** If OpenAI API unavailable, revert to Phase 1 templates

---

## User Flows

### Primary Flow: Get Recommendations

1. User opens Home of Exile
2. User copies PoB code from Path of Building
3. User pastes code into input field
4. User clicks "Analyze Build"
5. **[Loading: 5-8 seconds]** — "Analyzing your build..."
6. System displays:
   - Build summary card (character name, level, main skill, life, DPS)
   - 5 recommendation cards (sorted by priority)
7. User reads recommendation #1:
   - "Upgrade: Helmet → Starkonja's Head"
   - "Adds 312k DPS, +4,200 EHP, +89 Life"
   - "Cost: ~2 divine orbs (156k DPS per divine)"
   - Explanation paragraph
   - [Search on Trade] button
8. User clicks [Search on Trade] → opens poe.trade with pre-filled search
9. User clicks 👍 on recommendation

### Secondary Flow: Resource Lookup

1. User scrolls to "Resources" section
2. User sees curated links: poewiki.net, poedb.tw, poe.ninja, pob.cool
3. User clicks poe.ninja link for "Starkonja's Head"
4. Opens poe.ninja price graph in new tab

---

## Success Metrics

### Primary KPIs

| Metric | Target (3 months post-launch) | Measurement |
|--------|-------------------------------|-------------|
| **Recommendation accuracy** | 90%+ thumbs-up rate | PostgreSQL feedback table |
| **Trade link click-through** | 60%+ of recommendations | Implicit signal tracking |
| **Repeat usage** | 40% of users return within 7 days | Cookie-based user ID |
| **Analysis completion time** | < 8 seconds (P50) | Server logs |

### Secondary KPIs

| Metric | Target | Measurement |
|--------|--------|-------------|
| Recommendations per day | 500+ | API analytics |
| User feedback submissions | 20% of analyses | PostgreSQL |
| Resource hub page views | 10% of total traffic | Google Analytics |

### Qualitative Success

- "This tool helped me identify gaps I didn't know existed" — user interview goal
- Featured on /r/pathofexile with positive reception
- Community contributors submit feedback/improvements on GitHub

---

## Dependencies & Constraints

### External Dependencies

| Dependency | Risk Level | Mitigation |
|------------|-----------|------------|
| **poe.ninja API** | Medium | Cache data hourly; degrade gracefully if API down |
| **Path of Building Community Fork** | Low | MIT licensed, stable release cycle |
| **RePoE game data** | Low | Community-maintained, but can fork if abandoned |
| **OpenAI API (Phase 2)** | Medium | Template fallback mode if API unavailable |

### Technical Constraints

- **GGG rate limits:** Official trade API limited to 4 req/s — use poe.ninja for pricing instead
- **PoB format changes:** Community Fork maintains backward compatibility; minimal risk
- **League cadence:** New leagues every 3-4 months require PoB engine updates within 48 hours

### Business Constraints

- **No monetization (MVP):** Focus on building user base, not revenue
- **Community-first:** Open-source recommendation algorithm to build trust
- **Fandom wiki blacklist:** Per app.md, must exclude fandom.com/pathofexile links

---

## Roadmap & Timeline

### Phase 1: Engine-Only MVP (Weeks 1-6)

| Week | Deliverable |
|------|-------------|
| 1 | PoB parser (TS), RePoE data ingestion, poe.ninja price cache |
| 2 | LuaJIT engine integration (HeadlessWrapper.lua, Docker setup) |
| 3 | Candidate pool pipeline (poe.ninja items, attribute/level validation) |
| 4 | Simulation loop (item swaps, DPS/EHP delta calculations, ranking) |
| 5 | Frontend (PoB input UI, build summary, 5 recommendation cards, trade links) |
| 6 | Feedback system (thumbs-up/down), integration tests, deploy |

**MVP Launch:** End of Week 6

### Phase 2: LLM Enhancement (Weeks 7-8)

| Week | Deliverable |
|------|-------------|
| 7 | OpenAI API integration, prompt engineering, JSON schema output, validation |
| 8 | A/B test (templates vs. LLM), "wrong explanation" feedback signal, deploy |

**Enhanced Release:** End of Week 8

### Phase 3: Advanced Features (Future)

| Feature | Effort | Priority |
|---------|--------|----------|
| **Meta archetype comparison** (poe.ninja builds API) | 3 weeks | P2 |
| **Passive tree analysis** (quantitative DPS per node) | 4 weeks | P1 |
| **Crafting path suggestions** (Craft of Exile integration) | 6 weeks | P3 |
| **Build history tracking** (track progression over time) | 4 weeks | P2 |
| **SSF mode** (recommendations without trade access) | 5 weeks | P3 |

---

## Open Questions & Risks

### Open Questions

1. **Should we support Standard league?** — Most players play Challenge leagues; Standard support adds complexity for minimal user benefit. **Decision:** Challenge leagues only for MVP.

2. **How granular should feedback be?** — Thumbs-up/down is simple; star ratings (1-5) provide more signal but lower response rate. **Decision:** Start with thumbs-up/down; consider star ratings in Phase 3.

3. **Should recommendations explain why alternatives were rejected?** — Could help player learning but adds UI complexity. **Decision:** Not for MVP; consider as "Advanced View" toggle in Phase 3.

4. **How to handle PoB code versioning?** — Older PoB exports may use different XML schemas. **Decision:** Support Community Fork v2.35+ (covers ~95% of active players); display warning for older versions.

### Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **poe.ninja API changes/shuts down** | Medium | High | Maintain fallback item database; consider caching 30 days of data |
| **PoB Community Fork breaking change** | Low | High | Pin LuaJIT engine to specific fork commit; test updates in staging |
| **High server costs (LLM usage)** | Medium | Medium | Use GPT-4o-mini (<$0.01/call); implement template fallback |
| **Low user adoption** | Medium | Critical | Market on /r/pathofexile, PoE Discord, YouTube creators |
| **Recommendation quality poor** | Low | Critical | Extensive testing with diverse builds; alpha test with 50 players |
| **Legal/licensing issues** | Very Low | Medium | All dependencies are MIT/Apache licensed; no GGG IP used |

---

## Appendix: Key Research References

### Technical Resources

- **[pob-mcp](https://github.com/ianderse/pob-mcp)** — 44-tool MCP server for headless PoB via LuaJIT (key enabler)
- **[pob_wrapper](https://github.com/coldino/pob_wrapper)** — Python subprocess wrapper for headless PoB
- **[pob-web / pob.cool](https://github.com/atty303/pob-web)** — PoB compiled to WASM (browser alternative)
- **[PathOfBuildingCommunity](https://github.com/PathOfBuildingCommunity/PathOfBuilding)** — MIT licensed PoB fork
- **[RePoE](https://github.com/brather1ng/RePoE)** — Game data JSON exports
- **[poe.ninja API docs](https://github.com/Davenads/poeninjaAPI-2025)** — Community-documented endpoints

### Competitive Analysis

- **[PoePal Build Analyzer](https://poepal.com/build-analyzer)** — Defunct prior art (same concept, non-functional UI) — validates demand but shows execution risk

### Source Documents

- [app.md](app.md) — Original product specification
- [research.md](research.md) — Initial architecture research
- [recommendations.md](recommendations.md) — Deep-dive architectural recommendations (Rev 3)

---

## Approval & Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Product Owner | ___________ | ___________ | _____ |
| Tech Lead | ___________ | ___________ | _____ |
| Engineering Manager | ___________ | ___________ | _____ |

---

**Document Status:** Draft  
**Next Review Date:** TBD  
**Version History:**
- v1.0 (2026-02-27): Initial PRD created from app.md, research.md, recommendations.md

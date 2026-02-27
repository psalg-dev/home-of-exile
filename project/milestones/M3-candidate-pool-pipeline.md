# M3: Candidate Pool Pipeline

**Timeline:** Week 3
**Phase:** 1 (Engine-Only MVP)
**Priority:** P0 — MVP Blocker
**PRD Reference:** FR-2 (Recommendation Engine), FR-5 (League-Awareness)

---

## Objective

Build the pipeline that generates a pool of candidate upgrades for each equipment slot, filtered by character constraints (attributes, level, sockets) and enriched with pricing data.

---

## Deliverables

### D3.1: Archetype Detection

- [ ] Implement `detect_archetype(build: BuildData) -> Archetype`
  - Classify build by primary damage type: physical, fire, cold, lightning, chaos, minion, totem, trap/mine
  - Classify by defense style: life-based, ES-based, hybrid, low-life, CI
  - Classify by playstyle: melee, ranged, caster, summoner
  - Use gem tags, passive tree keystones, and equipped items as signals
- [ ] Output: `Archetype` struct with `damage_type`, `defense_style`, `playstyle`
- [ ] Archetype drives which item mods are considered "relevant" for candidate scoring

### D3.2: Candidate Item Generator

- [ ] Implement `generate_candidates(build: BuildData, slot: ItemSlot, archetype: Archetype) -> list[CandidateItem]`
- [ ] Source candidate items from:
  - **poe.ninja unique items** — filtered by slot, sorted by popularity
  - **poe.ninja rare item archetypes** — top-tier rares for the slot
  - **RePoE base items** — for identifying viable base types
- [ ] Filter candidates by hard constraints:
  - Level requirement ≤ character level
  - Attribute requirements ≤ character attributes (str/dex/int)
  - Item class matches slot (e.g., no wand in body armour slot)
- [ ] Soft-filter by archetype relevance:
  - Score candidate mods against archetype priorities
  - Discard candidates with 0 relevant mods
- [ ] Limit to top 20 candidates per slot (performance cap)

### D3.3: Candidate Gem Generator

- [ ] Implement `generate_gem_candidates(build: BuildData, skill_group: SkillGroup) -> list[CandidateGem]`
- [ ] For each support gem slot in the main skill:
  - Query RePoE for all support gems matching the skill's tags
  - Filter by level requirement ≤ character level
  - Filter by attribute requirements ≤ character attributes
  - Exclude already-equipped support gems
- [ ] For main skill alternatives:
  - Suggest top meta skills for the archetype (from poe.ninja builds data)
  - Limit to 5 alternatives

### D3.4: Pricing Enrichment

- [ ] Attach poe.ninja price data to each candidate:
  - `price_divine: float | null` — price in divine orbs
  - `price_confidence: 'high' | 'medium' | 'low'` — based on listing volume
  - `price_trend: 'rising' | 'stable' | 'falling'` — 7-day trend
- [ ] For rare items without exact match, estimate price by base + key mods
- [ ] Handle unpriced items: mark as `price_divine = null`, do not exclude

### D3.5: Constraint Validator

- [ ] Implement `validate_constraints(build: BuildData, candidate: CandidateItem) -> ValidationResult`
  - Check str/dex/int requirements against character stats
  - Check level requirement against character level
  - Check socket/link compatibility (does the build need a 6-link?)
  - Flag but don't discard borderline cases (e.g., 2 str short — flag as "needs +str elsewhere")
- [ ] Return `ValidationResult` with `valid: bool`, `warnings: list[str]`

---

## Data Structures

```python
class Archetype(BaseModel):
    damage_type: str       # physical, fire, cold, lightning, chaos, minion, totem, trap
    defense_style: str     # life, es, hybrid, lowlife, ci
    playstyle: str         # melee, ranged, caster, summoner

class CandidateItem(BaseModel):
    name: str
    base_name: str
    slot: str
    rarity: str
    level_req: int
    attr_req: dict[str, int]
    key_mods: list[str]
    price_divine: float | None
    price_confidence: str
    relevance_score: float     # 0.0 - 1.0 archetype match
    source: str                # "poe.ninja_unique", "poe.ninja_rare", "repoe"

class CandidateGem(BaseModel):
    name: str
    level_req: int
    attr_req: dict[str, int]
    tags: list[str]
    is_support: bool
    price_divine: float | None
```

---

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| 1 | Archetype detection correctly classifies a physical melee build | Unit test |
| 2 | Archetype detection correctly classifies a cold caster build | Unit test |
| 3 | Archetype detection correctly classifies a minion summoner build | Unit test |
| 4 | Candidate generator returns ≤ 20 items per slot | Unit test |
| 5 | All returned candidates pass level requirement check | Unit test |
| 6 | All returned candidates pass attribute requirement check | Unit test |
| 7 | Candidates include pricing data from poe.ninja | Integration test |
| 8 | Gem candidates exclude already-equipped gems | Unit test |
| 9 | Constraint validator flags items requiring attributes the build lacks | Unit test |
| 10 | Pipeline runs for all 10 equipment slots in < 3 seconds (cached prices) | Performance test |

---

## Dependencies

- **Upstream:** M1 (BuildData, RePoE data, PoeNinjaClient), M2 (CalculationResult types)
- **External:** poe.ninja API (item data + builds data)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Archetype detection misclassifies hybrid builds | Use multiple signals (gems + tree + items); allow manual override in future |
| poe.ninja rare item data insufficient for pricing | Fall back to base item + mod tier estimation |
| Too many candidates slow down simulation loop (M4) | Hard cap at 20 per slot; pre-rank by relevance |
| New league items not yet in poe.ninja | Graceful handling: new items appear as unpriced candidates |

---

## Definition of Done

- Archetype detection works for the 8 defined damage types and 5 defense styles
- Candidate pipeline produces filtered, priced candidates for all equipment slots and gem links
- All candidates respect character constraints (level, attributes)
- Pipeline is fast enough (< 3s) to not bottleneck the simulation loop

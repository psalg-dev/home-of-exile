# M4: Simulation Loop & Ranking

**Timeline:** Week 4
**Phase:** 1 (Engine-Only MVP)
**Priority:** P0 — MVP Blocker
**PRD Reference:** FR-2 (Recommendation Engine)

---

## Objective

Implement the core simulation loop that evaluates each candidate upgrade against the player's current build using the LuaJIT engine, calculates stat deltas, ranks by efficiency, and outputs the final 5 recommendations.

---

## Deliverables

### D4.1: Simulation Loop

- [ ] Implement `simulate_upgrades(build: BuildData, candidates: dict[str, list[CandidateItem]], archetype: Archetype) -> list[SimulationResult]`
- [ ] For each equipment slot:
  - Take top-N candidates from M3 pipeline
  - For each candidate: call `/api/v1/calculate-swap` (M2) to get stat deltas
  - Store `SimulationResult` per candidate
- [ ] For each gem slot:
  - Swap each candidate gem into the build
  - Recalculate DPS/EHP deltas
- [ ] Parallelize across LuaJIT pool workers (batch swap endpoint)
- [ ] Performance target: simulate all candidates (up to 200 swaps) in < 8 seconds

### D4.2: Scoring & Ranking Algorithm

- [ ] Implement `score_recommendation(sim: SimulationResult, archetype: Archetype) -> float`
- [ ] Scoring formula components:
  - **Critical fix bonus** (weight: 5.0) — uncapped resistances, dangerously low life
  - **DPS delta** (weight: 1.0, normalized) — raw damage improvement
  - **EHP delta** (weight: 0.8, normalized) — effective HP improvement
  - **Cost efficiency** (weight: 1.2) — stat gain per divine orb spent
  - **Archetype relevance** (weight: 0.5) — how well the upgrade fits the build style
- [ ] Weights configurable per archetype (e.g., defense-heavy builds weight EHP higher)
- [ ] Handle unpriced items: use median slot price as estimate; flag as "price uncertain"

### D4.3: Critical Issue Detection

- [ ] Implement `detect_critical_issues(build: BuildData) -> list[CriticalIssue]`
- [ ] Detect and flag:
  - **Uncapped elemental resistances** — any res below 75%
  - **Low life pool** — life < expected for level (heuristic table)
  - **Missing movement skill** — no gem with "Movement" tag
  - **Dead gem links** — support gems not supporting any active skill
  - **Wasted passive points** — unallocated points
- [ ] Critical issues get priority boost in ranking (always appear first in recommendations)

### D4.4: Recommendation Builder

- [ ] Implement `build_recommendations(simulations: list[SimulationResult], issues: list[CriticalIssue]) -> list[Recommendation]`
- [ ] Select top 5 recommendations by score, ensuring diversity:
  - Maximum 2 recommendations for the same slot
  - At least 1 defensive recommendation (if build has defensive gaps)
  - At least 1 cost-efficient option (< 1 divine)
- [ ] For each recommendation, generate:
  - Category: `critical_fix`, `power_upgrade`, `defense_upgrade`, `qol`, `efficiency`
  - Template-based explanation (using templates from PRD)
  - Trade site URL (pre-filled search for the specific item)
  - Deep links: poewiki.net item page, poe.ninja price page

### D4.5: Trade Link Generator

- [ ] Implement `generate_trade_link(item: CandidateItem, league: str) -> str`
- [ ] Generate official trade site URL (`pathofexile.com/trade`) with pre-filled:
  - Item name (for uniques)
  - Base type + key mods (for rares)
  - League parameter
- [ ] For gems: link to gem trade search

---

## Data Structures

```python
class SimulationResult(BaseModel):
    slot: str
    candidate: CandidateItem | CandidateGem
    baseline_stats: CalculationResult
    modified_stats: CalculationResult
    deltas: dict[str, float]
    price_divine: float | None

class CriticalIssue(BaseModel):
    category: str              # "uncapped_res", "low_life", "no_movement", "dead_link", "wasted_points"
    severity: str              # "critical", "warning"
    description: str
    affected_stat: str
    current_value: float
    target_value: float

class Recommendation(BaseModel):
    rank: int                  # 1-5
    category: str              # critical_fix, power_upgrade, defense_upgrade, qol, efficiency
    slot: str
    current_item: str
    suggested_item: str
    deltas: dict[str, float]
    price_divine: float | None
    efficiency_score: float | None  # DPS gain per divine
    explanation: str
    trade_url: str
    wiki_url: str | None
    ninja_url: str | None
    score: float
```

---

## Template-Based Explanations

```python
TEMPLATES = {
    "gear_upgrade": (
        "{suggested_item} in your {slot} adds {dps_delta:+,.0f} DPS and {ehp_delta:+,.0f} EHP. "
        "At ~{price:.1f} divine(s), that's {efficiency:,.0f} DPS per divine spent."
    ),
    "gem_swap": (
        "Replacing {current_item} with {suggested_item} adds {dps_delta:+,.0f} DPS "
        "to your {main_skill} setup."
    ),
    "resist_fix": (
        "Your {element} resistance is {current_value:.0f}% (cap: 75%). "
        "{suggested_item} would cap it while adding {dps_delta:+,.0f} DPS."
    ),
    "life_fix": (
        "Your life pool ({current_value:,.0f}) is low for level {level}. "
        "{suggested_item} adds {life_delta:+,.0f} life and {dps_delta:+,.0f} DPS."
    ),
    "efficiency": (
        "{suggested_item} is a budget option at ~{price:.1f} divine(s), "
        "adding {dps_delta:+,.0f} DPS — best value upgrade available."
    ),
}
```

---

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| 1 | Simulation loop processes all candidates for a build in < 8 seconds (P50) | Performance test |
| 2 | Simulation loop completes in < 15 seconds (P95) | Performance test |
| 3 | Returns exactly 5 recommendations | Unit test |
| 4 | Recommendations are sorted by score (highest first) | Unit test |
| 5 | Uncapped resistances always appear as recommendation #1 when present | Unit test |
| 6 | No more than 2 recommendations for the same slot | Unit test |
| 7 | At least 1 recommendation costs < 1 divine (if such candidates exist) | Unit test |
| 8 | Each recommendation includes a valid trade site URL | Unit test |
| 9 | Template explanations render without placeholder errors | Unit test |
| 10 | DPS deltas in recommendations match engine calculations within ±0.1% | Unit test |

---

## Dependencies

- **Upstream:** M2 (LuaJIT engine, calculate-swap endpoint), M3 (candidate pool, archetype, pricing)
- **External:** Official trade site URL format

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| 200 swap calculations exceed 15-second budget | Reduce candidates per slot; parallelize aggressively; short-circuit obvious losers |
| Ranking algorithm produces unintuitive results | Test with 10+ diverse builds; tune weights iteratively |
| Trade link format changes | Isolate URL generation; easy to update |
| Diversity constraint blocks high-value recommendations | Allow override if top candidate has 3x the score of alternatives |

---

## Definition of Done

- Full pipeline: `BuildData` → candidates → simulation → 5 ranked recommendations
- End-to-end time < 15 seconds for P95 builds
- Recommendations are accurate, diverse, and include actionable trade links
- Template explanations are clear and correctly filled

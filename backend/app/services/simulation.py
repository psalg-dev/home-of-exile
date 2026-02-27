"""Simulation loop and recommendation ranking engine — M4.

Orchestrates:
* D4.1 — simulation loop (``simulate_upgrades``)
* D4.2 — scoring / ranking (``score_recommendation``)
* D4.3 — critical issue detection (``detect_critical_issues``)
* D4.4 — recommendation builder (``build_recommendations``)
* D4.5 — trade link generator (``generate_trade_link``)

Design notes:
- All candidate simulations are dispatched to the LuaJIT pool in one
  parallel batch via ``calculate_swap_batch``.
- Scoring uses a weighted multi-objective formula with normalisation
  across the simulation run.
- Diversity constraints prevent the same slot from occupying more than
  2 of the 5 recommendation slots.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any

from app.models.calculation import CalculationResult
from app.models.candidate import (
    Archetype,
    BuildData,
    CandidateGem,
    CandidateItem,
    GemGroupCandidates,
    SlotCandidates,
)
from app.models.recommendation import (
    CriticalIssue,
    Recommendation,
    SimulationResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring weights (configurable per archetype later)
# ---------------------------------------------------------------------------

_W_CRITICAL = 5.0    # bonus for fixing a critical issue
_W_DPS = 1.0         # normalised DPS delta
_W_EHP = 0.8         # normalised EHP delta
_W_EFFICIENCY = 1.2  # stat gain per divine orb
_W_RELEVANCE = 0.5   # archetype relevance (from M3 pipeline)

# Fallback median price (divines) when an item is unpriced.
_FALLBACK_PRICE_DIVINE = 1.0

# Maximum top-N candidates per slot to simulate. Capped by the caller.
_DEFAULT_MAX_PER_SLOT = 10

# Expected minimum life pool by level tier (heuristic).
_LIFE_THRESHOLDS: list[tuple[int, int]] = [
    (90, 5000),
    (80, 4500),
    (60, 4000),
    (40, 3000),
    (20, 2000),
    (0, 1000),
]

# RES cap for elemental resistances.
_RES_CAP = 75

# Template strings for human-readable explanations.
TEMPLATES: dict[str, str] = {
    "gear_upgrade": (
        "{suggested_item} in your {slot} adds {dps_delta:+,.0f} DPS and"
        " {ehp_delta:+,.0f} EHP. "
        "At ~{price:.1f} divine(s), that's {efficiency:,.0f} DPS per divine"
        " spent."
    ),
    "gem_swap": (
        "Replacing {current_item} with {suggested_item} adds"
        " {dps_delta:+,.0f} DPS to your {main_skill} setup."
    ),
    "resist_fix": (
        "Your {element} resistance is {current_value:.0f}%% (cap: 75%%). "
        "{suggested_item} would cap it while adding {dps_delta:+,.0f} DPS."
    ),
    "life_fix": (
        "Your life pool ({current_value:,.0f}) is low for level {level}. "
        "{suggested_item} adds {life_delta:+,.0f} life and"
        " {dps_delta:+,.0f} DPS."
    ),
    "efficiency": (
        "{suggested_item} is a budget option at ~{price:.1f} divine(s), "
        "adding {dps_delta:+,.0f} DPS — best value upgrade available."
    ),
}


# ---------------------------------------------------------------------------
# D4.5 — Trade link generator
# ---------------------------------------------------------------------------


def generate_trade_link(
    item: CandidateItem | CandidateGem,
    league: str,
) -> str:
    """Generate a pre-filled trade site URL for a candidate item.

    For unique items the trade search is narrowed to the item name.
    For rare base types the base type is used with key mods as stat filters.
    For gems a gem-specific search is built.

    Args:
        item: Candidate item or gem.
        league: League name (e.g. ``'Settlers'``).

    Returns:
        Absolute URL pointing to ``pathofexile.com/trade``.
    """
    safe_league = urllib.parse.quote(league)
    base_url = f"https://www.pathofexile.com/trade/search/{safe_league}"

    if isinstance(item, CandidateGem):
        query: dict[str, Any] = {
            "query": {
                "type": item.name,
                "status": {"option": "online"},
            },
            "sort": {"price": "asc"},
        }
    elif item.rarity == "unique" and item.name:
        query = {
            "query": {
                "name": item.name,
                "status": {"option": "online"},
            },
            "sort": {"price": "asc"},
        }
    else:
        # Rare / normal — search by base type
        query = {
            "query": {
                "type": item.base_name,
                "status": {"option": "online"},
            },
            "sort": {"price": "asc"},
        }

    return f"{base_url}?q={urllib.parse.quote(json.dumps(query, separators=(',', ':')))}"


# ---------------------------------------------------------------------------
# D4.3 — Critical issue detection
# ---------------------------------------------------------------------------


def detect_critical_issues(build: BuildData) -> list[CriticalIssue]:
    """Detect critical flaws in the current build configuration.

    Checks for:
    * Uncapped elemental resistances (< 75%).
    * Low life pool relative to character level.
    * Missing movement skill gem.
    * Dead gem links (support gems in a group with no active skill).

    Args:
        build: Structured build data.

    Returns:
        List of :class:`~app.models.recommendation.CriticalIssue` objects,
        ordered by severity (critical first).
    """
    issues: list[CriticalIssue] = []

    stats = build.stats

    # 1. Uncapped elemental resistances
    res_checks = [
        ("fire_res", stats.fire_res, "fire", "fire_res"),
        ("cold_res", stats.cold_res, "cold", "cold_res"),
        ("lightning_res", stats.lightning_res, "lightning", "lightning_res"),
    ]
    for _key, value, element_label, affected_stat in res_checks:
        if value < _RES_CAP:
            severity = "critical" if value < 0 else "warning"
            issues.append(
                CriticalIssue(
                    category="uncapped_res",
                    severity=severity,
                    description=(
                        f"{element_label.capitalize()} resistance is"
                        f" {value}% (cap: {_RES_CAP}%)."
                    ),
                    affected_stat=affected_stat,
                    current_value=float(value),
                    target_value=float(_RES_CAP),
                )
            )

    # 2. Low life pool
    expected_life = _expected_life(build.level)
    if stats.life > 0 and stats.life < expected_life and build.stats.energy_shield < 1000:
        # Skip life check for ES builds (energy_shield > 1000 = likely CI/lowlife)
        issues.append(
            CriticalIssue(
                category="low_life",
                severity="warning",
                description=(
                    f"Life pool ({stats.life:,}) is low for level"
                    f" {build.level} (expected ≥ {expected_life:,})."
                ),
                affected_stat="life",
                current_value=float(stats.life),
                target_value=float(expected_life),
            )
        )

    # 3. Missing movement skill
    movement_keywords = {
        "dash", "flame dash", "leap slam", "whirling blades",
        "lightning warp", "shield charge", "phase run", "blink arrow",
        "mirror arrow", "smoke mine", "frostblink",
    }
    gem_names_lower = {n.lower() for n in build.all_gem_names}
    has_movement = any(
        any(kw in g for kw in movement_keywords)
        for g in gem_names_lower
    )
    if not has_movement and build.all_gem_names:
        issues.append(
            CriticalIssue(
                category="no_movement",
                severity="warning",
                description="No movement skill detected in skill groups.",
                affected_stat="movement_skill",
                current_value=0.0,
                target_value=1.0,
            )
        )

    # 4. Dead gem links (support gem in group with no active skill)
    for group in build.skill_groups:
        if not group.enabled:
            continue
        active_gems = [g for g in group.gems if not g.is_support and g.enabled]
        support_gems = [g for g in group.gems if g.is_support and g.enabled]
        if support_gems and not active_gems:
            issues.append(
                CriticalIssue(
                    category="dead_link",
                    severity="warning",
                    description=(
                        f"Skill group '{group.slot or group.label}' has"
                        f" support gems but no active skill."
                    ),
                    affected_stat="gem_links",
                    current_value=0.0,
                    target_value=1.0,
                )
            )

    # Sort: critical first, then by category
    issues.sort(key=lambda i: (0 if i.severity == "critical" else 1, i.category))
    return issues


def _expected_life(level: int) -> int:
    """Return the heuristic minimum expected life pool for a given level.

    Args:
        level: Character level (1–100).

    Returns:
        Expected minimum life value.
    """
    for threshold_level, threshold_life in _LIFE_THRESHOLDS:
        if level >= threshold_level:
            return threshold_life
    return 1000


# ---------------------------------------------------------------------------
# EHP helper
# ---------------------------------------------------------------------------


def _compute_ehp(stats: CalculationResult, defense_style: str) -> float:
    """Compute effective HP from a calculation result.

    Args:
        stats: Calculation result with life, energy_shield values.
        defense_style: Archetype defense style (life, es, hybrid, ci).

    Returns:
        Effective HP value.
    """
    life = float(stats.life)
    es = float(stats.energy_shield)
    if defense_style in ("es", "ci", "lowlife"):
        return es
    if defense_style == "hybrid":
        return life + es
    # default: life build
    return life


# ---------------------------------------------------------------------------
# D4.1 — Item text construction for simulation
# ---------------------------------------------------------------------------


def _build_item_text(candidate: CandidateItem) -> str:
    """Construct a PoE item text string from candidate data.

    The format mirrors the PoE clipboard item format.  PoB will parse the
    name for known uniques and look them up in its internal database.
    For rare base items, key mods are included as explicit mods.

    Args:
        candidate: Candidate item to convert.

    Returns:
        PoE item text string suitable for ``add_item_text`` RPC.
    """
    rarity_label = candidate.rarity.capitalize()
    lines = [f"Rarity: {rarity_label}"]

    if candidate.name:
        lines.append(candidate.name)
    if candidate.base_name:
        lines.append(candidate.base_name)

    lines.append("--------")

    if candidate.key_mods:
        for mod in candidate.key_mods:
            lines.append(mod)
        lines.append("--------")

    return "\n".join(lines)


def _build_gem_text(candidate: CandidateGem) -> str:
    """Construct a minimal PoE gem text from candidate data.

    Args:
        candidate: Candidate gem.

    Returns:
        PoE item text string for pasting into PoB.
    """
    gem_type = "Support Skill Gem" if candidate.is_support else "Active Skill Gem"
    lines = [
        f"Rarity: Gem",
        candidate.name,
        "--------",
        f"Gem Tags: {gem_type}",
        "--------",
        "Level: 20",
        "Quality: 0",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# D4.1 — Simulation loop
# ---------------------------------------------------------------------------


async def simulate_upgrades(
    build_xml: str,
    build: BuildData,
    item_candidates: list[SlotCandidates],
    gem_candidates: list[GemGroupCandidates],
    archetype: Archetype,
    pool: Any,
    max_per_slot: int = _DEFAULT_MAX_PER_SLOT,
) -> list[SimulationResult]:
    """Simulate all candidate upgrades against the baseline build.

    Dispatches all swap calculations to the LuaJIT pool in a single parallel
    batch.  Stores a :class:`~app.models.recommendation.SimulationResult`
    per successful simulation.

    Args:
        build_xml: Raw PoB XML string (for the calculation engine).
        build: Parsed build data (for current-item lookups).
        item_candidates: Per-slot candidate lists from the M3 pipeline.
        gem_candidates: Per-group gem candidate lists from the M3 pipeline.
        archetype: Detected build archetype.
        pool: Active :class:`~app.services.luajit_pool.LuaJITPoolManager`.
        max_per_slot: Maximum candidates to simulate per slot.

    Returns:
        List of :class:`~app.models.recommendation.SimulationResult`, one per
        successful swap.  Failed swaps are logged and skipped.
    """
    # Build a flat list of (slot, candidate, item_text) tuples
    swap_specs: list[tuple[str, CandidateItem | CandidateGem, str]] = []

    for slot_group in item_candidates:
        top_n = slot_group.candidates[:max_per_slot]
        for candidate in top_n:
            item_text = _build_item_text(candidate)
            swap_specs.append((slot_group.slot, candidate, item_text))

    for gem_group in gem_candidates:
        # Only simulate support gem swaps (skill alternatives need a different
        # approach — include top-3 support candidates for now).
        top_supports = gem_group.support_candidates[:3]
        for candidate in top_supports:
            gem_text = _build_gem_text(candidate)
            swap_specs.append((gem_group.slot, candidate, gem_text))

    if not swap_specs:
        return []

    # Build the batch payload for the pool
    batch_swaps = [
        {"item_text": item_text, "slot_name": slot}
        for slot, _candidate, item_text in swap_specs
    ]

    logger.info("Simulating %d candidate swaps in parallel", len(batch_swaps))
    raw_results = await pool.calculate_swap_batch(build_xml, batch_swaps)

    # Parse results
    results: list[SimulationResult] = []
    for (slot, candidate, _item_text), raw in zip(swap_specs, raw_results, strict=True):
        if isinstance(raw, dict) and "error" in raw and len(raw) == 1:
            logger.debug(
                "Swap failed for %s / %s: %s",
                slot,
                getattr(candidate, "name", getattr(candidate, "base_name", "?")),
                raw["error"],
            )
            continue

        raw_dict: dict[str, Any] = raw
        baseline = CalculationResult.from_pob_stats(raw_dict.get("baseline", {}))
        modified = CalculationResult.from_pob_stats(raw_dict.get("modified", {}))

        # Compute deltas for all numeric fields
        deltas: dict[str, float] = {}
        for field_name in CalculationResult.model_fields:
            b_val = float(getattr(baseline, field_name, 0) or 0)
            m_val = float(getattr(modified, field_name, 0) or 0)
            delta = m_val - b_val
            if delta != 0.0:
                deltas[field_name] = round(delta, 4)

        price = getattr(candidate, "price_divine", None)
        # Flag median-estimate prices as uncertain
        price_uncertain = price is None

        results.append(
            SimulationResult(
                slot=slot,
                candidate=candidate,
                baseline_stats=baseline,
                modified_stats=modified,
                deltas=deltas,
                price_divine=price,
                price_uncertain=price_uncertain,
            )
        )

    logger.info(
        "Simulation complete: %d/%d swaps succeeded",
        len(results),
        len(swap_specs),
    )
    return results


# ---------------------------------------------------------------------------
# D4.2 — Scoring formula
# ---------------------------------------------------------------------------


def score_recommendation(
    sim: SimulationResult,
    archetype: Archetype,
    issues: list[CriticalIssue],
    max_dps_delta: float = 1.0,
    max_ehp_delta: float = 1.0,
) -> float:
    """Compute a composite score for a simulation result.

    Formula components:
    * Critical fix bonus (×5.0) — item fixes an uncapped res or low life.
    * DPS delta (×1.0, normalised over the simulation batch).
    * EHP delta (×0.8, normalised over the simulation batch).
    * Cost efficiency (×1.2) — DPS gain per divine orb.
    * Archetype relevance (×0.5) — from the M3 candidate pipeline score.

    Args:
        sim: Simulation result to score.
        archetype: Build archetype (used to tune EHP weight for ES builds).
        issues: Current critical issues (used for critical fix bonus).
        max_dps_delta: Maximum absolute DPS delta across all simulations
            (for normalisation).
        max_ehp_delta: Maximum absolute EHP delta across all simulations
            (for normalisation).

    Returns:
        Composite float score (higher = better).
    """
    score = 0.0

    dps_delta = sim.deltas.get("dps", 0.0)
    life_delta = sim.deltas.get("life", 0.0)
    es_delta = sim.deltas.get("energy_shield", 0.0)
    ehp_delta = _compute_ehp(
        sim.modified_stats, archetype.defense_style
    ) - _compute_ehp(sim.baseline_stats, archetype.defense_style)

    # ---- Critical fix bonus --------------------------------------------------
    issue_cats = {i.category for i in issues}
    if isinstance(sim.candidate, CandidateItem):
        # Resistance fix: check if mods address uncapped resistance issues
        if "uncapped_res" in issue_cats:
            for mod in sim.candidate.key_mods:
                mod_lower = mod.lower()
                if any(
                    kw in mod_lower
                    for kw in ("fire resistance", "cold resistance",
                               "lightning resistance", "all elemental",
                               "all resistances")
                ):
                    score += _W_CRITICAL
                    break
        # Life fix: item adds significant life
        if "low_life" in issue_cats and life_delta > 100:
            score += _W_CRITICAL * 0.5

    # ---- EHP weight varies by defense style -----------------------------------
    ehp_weight = _W_EHP
    if archetype.defense_style in ("es", "ci", "lowlife"):
        # ES/CI builds care more about ES than life
        ehp_weight = _W_EHP * 1.5

    # ---- Normalised DPS / EHP deltas -----------------------------------------
    if max_dps_delta > 0:
        norm_dps = dps_delta / max_dps_delta
        score += _W_DPS * norm_dps

    if max_ehp_delta > 0:
        norm_ehp = ehp_delta / max_ehp_delta
        score += ehp_weight * norm_ehp

    # ---- Cost efficiency -------------------------------------------------------
    # Use inverse-price as a budget signal: items costing less score more.
    # Scale: price=0→1.0, price=1→0.5, price=5→0.167, price=10→0.09.
    price = sim.price_divine if sim.price_divine and sim.price_divine > 0 else None
    if price:
        budget_score = 1.0 / (1.0 + price)
        score += _W_EFFICIENCY * budget_score

    # ---- Archetype relevance --------------------------------------------------
    relevance = getattr(sim.candidate, "relevance_score", 0.0)
    score += _W_RELEVANCE * relevance

    return round(score, 4)


# ---------------------------------------------------------------------------
# D4.4 — Recommendation builder
# ---------------------------------------------------------------------------


def build_recommendations(
    simulations: list[SimulationResult],
    issues: list[CriticalIssue],
    build: BuildData,
    archetype: Archetype,
    league: str = "Settlers",
) -> list[Recommendation]:
    """Select the top 5 recommendations from simulation results.

    Diversity constraints:
    * Maximum 2 recommendations per slot.
    * At least 1 defensive recommendation when defensive gaps exist.
    * At least 1 cost-efficient option (< 1 divine) when available.

    Args:
        simulations: All simulation results.
        issues: Detected critical issues (used for critical_fix category).
        build: Build data (for current-item display names).
        archetype: Detected build archetype.
        league: League name (for trade link generation).

    Returns:
        List of up to 5 :class:`~app.models.recommendation.Recommendation`
        objects sorted by score (highest first).
    """
    if not simulations:
        return []

    # Compute normalisation bounds
    dps_deltas = [abs(s.deltas.get("dps", 0.0)) for s in simulations]
    ehp_deltas = [
        abs(
            _compute_ehp(s.modified_stats, archetype.defense_style)
            - _compute_ehp(s.baseline_stats, archetype.defense_style)
        )
        for s in simulations
    ]
    max_dps = max(dps_deltas, default=1.0) or 1.0
    max_ehp = max(ehp_deltas, default=1.0) or 1.0

    # Score every simulation
    scored: list[tuple[float, SimulationResult]] = [
        (
            score_recommendation(sim, archetype, issues, max_dps, max_ehp),
            sim,
        )
        for sim in simulations
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    # Issue categories for quick lookup
    issue_cats = {i.category for i in issues}
    has_defensive_gap = bool(
        issue_cats.intersection({"uncapped_res", "low_life"})
    )

    # Build the top-5 with diversity constraints
    selected: list[tuple[float, SimulationResult]] = []
    slot_counts: dict[str, int] = {}
    has_defensive = False
    has_budget = False

    def _is_defensive(sim: SimulationResult) -> bool:
        """Return True if the sim result improves defences meaningfully."""
        ehp_gain = (
            _compute_ehp(sim.modified_stats, archetype.defense_style)
            - _compute_ehp(sim.baseline_stats, archetype.defense_style)
        )
        dps_gain = sim.deltas.get("dps", 0.0)
        return ehp_gain > 0 and (dps_gain <= 0 or ehp_gain > dps_gain)

    def _is_budget(sim: SimulationResult) -> bool:
        """Return True if the item costs < 1 divine or is unpriced."""
        p = sim.price_divine
        return p is not None and p < 1.0

    # First pass: best per constraint
    for score_val, sim in scored:
        slot = sim.slot
        if slot_counts.get(slot, 0) >= 2:
            continue
        # Allow override when score is 3× the highest alternative
        selected.append((score_val, sim))
        slot_counts[slot] = slot_counts.get(slot, 0) + 1
        if _is_defensive(sim):
            has_defensive = True
        if _is_budget(sim):
            has_budget = True
        if len(selected) >= 5:
            break

    # Second pass: inject defensive / budget if missing
    if has_defensive_gap and not has_defensive:
        for score_val, sim in scored:
            if (score_val, sim) in selected:
                continue
            if not _is_defensive(sim):
                continue
            # Replace last selected if slot already capped for the new sim
            slot = sim.slot
            if slot_counts.get(slot, 0) < 2:
                # Inject and trim
                selected.append((score_val, sim))
                slot_counts[slot] = slot_counts.get(slot, 0) + 1
                # Remove the worst non-defensive entry to keep ≤ 5
                if len(selected) > 5:
                    selected.sort(key=lambda x: x[0], reverse=True)
                    selected = selected[:5]
                has_defensive = True
                break

    if not has_budget:
        for score_val, sim in scored:
            if (score_val, sim) in selected:
                continue
            if not _is_budget(sim):
                continue
            slot = sim.slot
            if slot_counts.get(slot, 0) < 2:
                if len(selected) >= 5:
                    # Replace the worst-scoring item to inject the budget pick.
                    # Prefer items whose slot has ≥ 2 representatives so no
                    # slot drops to zero; fall back to the absolute lowest.
                    worst_idx = -1
                    worst_score = float("inf")
                    for idx, (sv, s) in enumerate(selected):
                        s_slot = s.slot
                        if sv < worst_score and (
                            slot_counts.get(s_slot, 1) > 1 or worst_idx == -1
                        ):
                            worst_score = sv
                            worst_idx = idx
                    if worst_idx >= 0:
                        removed_slot = selected[worst_idx][1].slot
                        slot_counts[removed_slot] = (
                            slot_counts.get(removed_slot, 1) - 1
                        )
                        selected[worst_idx] = (score_val, sim)
                        slot_counts[slot] = slot_counts.get(slot, 0) + 1
                else:
                    selected.append((score_val, sim))
                    slot_counts[slot] = slot_counts.get(slot, 0) + 1
                selected.sort(key=lambda x: x[0], reverse=True)
                has_budget = True
                break

    # Final sort by score
    selected.sort(key=lambda x: x[0], reverse=True)

    recommendations: list[Recommendation] = []
    for rank_idx, (score_val, sim) in enumerate(selected[:5], start=1):
        rec = _build_single_recommendation(
            rank=rank_idx,
            score=score_val,
            sim=sim,
            build=build,
            archetype=archetype,
            issues=issues,
            league=league,
        )
        recommendations.append(rec)

    return recommendations


def _build_single_recommendation(
    rank: int,
    score: float,
    sim: SimulationResult,
    build: BuildData,
    archetype: Archetype,
    issues: list[CriticalIssue],
    league: str,
) -> Recommendation:
    """Convert a SimulationResult into a Recommendation.

    Args:
        rank: 1-based rank position.
        score: Computed score value.
        sim: Source simulation result.
        build: Current build data.
        archetype: Detected archetype.
        issues: Current critical issues.
        league: League name for trade links.

    Returns:
        Fully populated :class:`~app.models.recommendation.Recommendation`.
    """
    candidate = sim.candidate
    slot = sim.slot
    dps_delta = sim.deltas.get("dps", 0.0)
    ehp_delta = (
        _compute_ehp(sim.modified_stats, archetype.defense_style)
        - _compute_ehp(sim.baseline_stats, archetype.defense_style)
    )
    life_delta = sim.deltas.get("life", 0.0)

    # Current item name from build data
    current_item = ""
    if isinstance(candidate, CandidateItem):
        equipped = build.items.get(slot)
        if equipped:
            current_item = equipped.name or equipped.base_name
    else:
        # Gem — show slot label
        current_item = slot

    if isinstance(candidate, CandidateGem):
        suggested = candidate.name
    elif candidate.name:
        suggested = candidate.name
    else:
        suggested = candidate.base_name or slot

    price = sim.price_divine

    # Efficiency (DPS / divine)
    efficiency_score: float | None = None
    if price and price > 0 and dps_delta > 0:
        efficiency_score = round(dps_delta / price, 1)

    # Category
    category = _pick_category(sim, archetype, issues, dps_delta, ehp_delta)

    # Explanation
    explanation = _render_explanation(
        category=category,
        sim=sim,
        build=build,
        archetype=archetype,
        slot=slot,
        suggested_item=suggested,
        current_item=current_item,
        dps_delta=dps_delta,
        ehp_delta=ehp_delta,
        life_delta=life_delta,
        price=price,
        efficiency_score=efficiency_score,
        issues=issues,
    )

    # URLs
    trade_url = generate_trade_link(candidate, league)
    wiki_url: str | None = None
    ninja_url: str | None = None

    if isinstance(candidate, CandidateItem) and candidate.name:
        wiki_slug = urllib.parse.quote(candidate.name.replace(" ", "_"))
        wiki_url = f"https://www.poewiki.net/wiki/{wiki_slug}"
        ninja_slug = urllib.parse.quote(candidate.name)
        ninja_url = (
            f"https://poe.ninja/economy/{urllib.parse.quote(league.lower())}"
            f"/unique-armours?name={ninja_slug}"
        )

    return Recommendation(
        rank=rank,
        category=category,
        slot=slot,
        current_item=current_item,
        suggested_item=suggested,
        deltas=sim.deltas,
        price_divine=price,
        efficiency_score=efficiency_score,
        explanation=explanation,
        trade_url=trade_url,
        wiki_url=wiki_url,
        ninja_url=ninja_url,
        score=score,
    )


def _pick_category(
    sim: SimulationResult,
    archetype: Archetype,
    issues: list[CriticalIssue],
    dps_delta: float,
    ehp_delta: float,
) -> str:
    """Determine the recommendation category for a simulation result.

    Priority: critical_fix > power_upgrade > defense_upgrade >
    efficiency > qol.

    Args:
        sim: Simulation result.
        archetype: Build archetype.
        issues: Current detected issues.
        dps_delta: DPS change from the swap.
        ehp_delta: EHP change from the swap.

    Returns:
        Category string.
    """
    issue_cats = {i.category for i in issues}
    candidate = sim.candidate

    # Critical fix: addresses uncapped res or low life
    if isinstance(candidate, CandidateItem) and issue_cats:
        for mod in candidate.key_mods:
            mod_lower = mod.lower()
            if "uncapped_res" in issue_cats and any(
                kw in mod_lower
                for kw in ("resistance", "all elemental", "all res")
            ):
                return "critical_fix"
        if "low_life" in issue_cats and sim.deltas.get("life", 0) > 200:
            return "critical_fix"

    price = sim.price_divine
    if price is not None and price < 1.0 and dps_delta > 0:
        return "efficiency"

    if ehp_delta > 0 and (dps_delta <= 0 or ehp_delta > dps_delta):
        return "defense_upgrade"

    if dps_delta > 0:
        return "power_upgrade"

    return "qol"


def _render_explanation(
    category: str,
    sim: SimulationResult,
    build: BuildData,
    archetype: Archetype,
    slot: str,
    suggested_item: str,
    current_item: str,
    dps_delta: float,
    ehp_delta: float,
    life_delta: float,
    price: float | None,
    efficiency_score: float | None,
    issues: list[CriticalIssue],
) -> str:
    """Render a human-readable explanation from a template.

    Falls back gracefully if template context is incomplete.

    Args:
        category: Recommendation category.
        sim: Simulation result.
        build: Build data.
        archetype: Build archetype.
        slot: Equipment slot name.
        suggested_item: Display name of the recommended item.
        current_item: Display name of the currently equipped item.
        dps_delta: DPS change.
        ehp_delta: EHP change.
        life_delta: Life change.
        price: Price in divines (optional).
        efficiency_score: DPS per divine (optional).
        issues: Current critical issues.

    Returns:
        Rendered template string.
    """
    safe_price = price if price is not None else _FALLBACK_PRICE_DIVINE
    safe_eff = efficiency_score if efficiency_score is not None else 0.0

    if category == "critical_fix":
        # Find the matching issue for the best template
        res_issue = next(
            (i for i in issues if i.category == "uncapped_res"), None
        )
        life_issue = next(
            (i for i in issues if i.category == "low_life"), None
        )
        if res_issue and isinstance(sim.candidate, CandidateItem):
            element = res_issue.affected_stat.replace("_res", "")
            try:
                return TEMPLATES["resist_fix"].format(
                    element=element,
                    current_value=res_issue.current_value,
                    suggested_item=suggested_item,
                    dps_delta=dps_delta,
                )
            except (KeyError, ValueError):
                pass
        if life_issue:
            try:
                return TEMPLATES["life_fix"].format(
                    current_value=life_issue.current_value,
                    level=build.level,
                    suggested_item=suggested_item,
                    life_delta=life_delta,
                    dps_delta=dps_delta,
                )
            except (KeyError, ValueError):
                pass

    if category == "efficiency":
        try:
            return TEMPLATES["efficiency"].format(
                suggested_item=suggested_item,
                price=safe_price,
                dps_delta=dps_delta,
            )
        except (KeyError, ValueError):
            pass

    if isinstance(sim.candidate, CandidateGem):
        try:
            return TEMPLATES["gem_swap"].format(
                current_item=current_item,
                suggested_item=suggested_item,
                dps_delta=dps_delta,
                main_skill=build.main_skill or "your main skill",
            )
        except (KeyError, ValueError):
            pass

    try:
        return TEMPLATES["gear_upgrade"].format(
            suggested_item=suggested_item,
            slot=slot,
            dps_delta=dps_delta,
            ehp_delta=ehp_delta,
            price=safe_price,
            efficiency=safe_eff,
        )
    except (KeyError, ValueError):
        return (
            f"{suggested_item} in {slot} adds {dps_delta:+,.0f} DPS"
            f" and {ehp_delta:+,.0f} EHP."
        )

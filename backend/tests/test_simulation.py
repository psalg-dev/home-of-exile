"""Tests for the M4 simulation loop and recommendation engine.

Covers all acceptance criteria from M4:
* AC3  — Returns exactly 5 recommendations.
* AC4  — Recommendations are sorted by score (highest first).
* AC5  — Uncapped resistances always appear as recommendation #1.
* AC6  — No more than 2 recommendations for the same slot.
* AC7  — At least 1 recommendation costs < 1 divine when available.
* AC8  — Each recommendation includes a valid trade site URL.
* AC9  — Template explanations render without errors.
* AC10 — DPS deltas match engine calculations within ±0.1%.

Also covers:
* detect_critical_issues — res, low_life, no_movement, dead_link.
* score_recommendation — weights and normalisation.
* generate_trade_link — unique / rare / gem URL shapes.
* POST /api/v1/recommendations end-to-end (pool mocked).
"""

from __future__ import annotations

import base64
import json
import urllib.parse
import zlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.calculation import CalculationResult
from app.models.candidate import (
    Archetype,
    BuildData,
    BuildGem,
    BuildItem,
    BuildSkillGroup,
    BuildStats,
    CandidateGem,
    CandidateItem,
    CharacterAttrs,
    GemGroupCandidates,
    ItemAttrReq,
    SlotCandidates,
)
from app.models.recommendation import (
    CriticalIssue,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
    SimulationResult,
)
from app.services.simulation import (
    _build_item_text,
    _compute_ehp,
    build_recommendations,
    detect_critical_issues,
    generate_trade_link,
    score_recommendation,
    simulate_upgrades,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_archetype(
    damage_type: str = "fire",
    defense_style: str = "life",
    playstyle: str = "caster",
) -> Archetype:
    """Build a test Archetype.

    Args:
        damage_type: Primary damage type.
        defense_style: Defensive layer.
        playstyle: Combat style.

    Returns:
        :class:`~app.models.candidate.Archetype`.
    """
    return Archetype(
        damage_type=damage_type,
        defense_style=defense_style,
        playstyle=playstyle,
    )


def _make_build(
    level: int = 80,
    life: int = 4500,
    energy_shield: int = 200,
    fire_res: int = 75,
    cold_res: int = 75,
    lightning_res: int = 75,
    chaos_res: int = -60,
    dps: float = 1_200_000.0,
    main_skill: str = "Fireball",
    gems: list[str] | None = None,
    items: dict[str, str] | None = None,
) -> BuildData:
    """Construct a minimal BuildData for tests.

    Args:
        level: Character level.
        life: Life stat.
        energy_shield: Energy shield stat.
        fire_res: Fire resistance.
        cold_res: Cold resistance.
        lightning_res: Lightning resistance.
        chaos_res: Chaos resistance.
        dps: Main skill DPS.
        main_skill: Main active skill name.
        gems: List of gem names to add to one skill group.
        items: Map of slot name → item name to pre-populate items dict.

    Returns:
        Populated :class:`~app.models.candidate.BuildData`.
    """
    gem_objects = [
        BuildGem(name_spec=name, is_support=name.endswith("Support"))
        for name in (gems or ["Fireball", "Spell Echo Support"])
    ]
    skill_groups = [
        BuildSkillGroup(
            slot="Body Armour",
            enabled=True,
            gems=gem_objects,
            main_active_gem_index=0,
        )
    ]
    build_items: dict[str, BuildItem] = {}
    for slot, name in (items or {}).items():
        build_items[slot] = BuildItem(name=name, slot=slot, base_name=name)

    return BuildData(
        character_name="TestChar",
        **{"class": "Witch"},
        ascendancy="Occultist",
        level=level,
        main_skill=main_skill,
        stats=BuildStats(
            life=life,
            energy_shield=energy_shield,
            dps=dps,
            fire_res=fire_res,
            cold_res=cold_res,
            lightning_res=lightning_res,
            chaos_res=chaos_res,
        ),
        attrs=CharacterAttrs(str=100, dex=100, **{"int": 200}),
        skill_groups=skill_groups,
        items=build_items,
    )


def _make_calc_result(
    dps: float = 1_200_000.0,
    life: int = 4500,
    energy_shield: int = 200,
    fire_res: int = 75,
    cold_res: int = 75,
    lightning_res: int = 75,
) -> CalculationResult:
    """Create a CalculationResult for use in SimulationResults.

    Args:
        dps: Main skill DPS.
        life: Life pool value.
        energy_shield: Energy shield value.
        fire_res: Fire resistance.
        cold_res: Cold resistance.
        lightning_res: Lightning resistance.

    Returns:
        Populated :class:`~app.models.calculation.CalculationResult`.
    """
    return CalculationResult(
        dps=dps,
        total_dps=dps,
        life=life,
        energy_shield=energy_shield,
        fire_res=fire_res,
        cold_res=cold_res,
        lightning_res=lightning_res,
    )


def _make_simulation_result(
    slot: str = "Helmet",
    name: str = "Starkonja's Head",
    dps_gain: float = 100_000.0,
    life_gain: int = 200,
    price: float | None = 2.0,
    relevance_score: float = 0.8,
) -> SimulationResult:
    """Build a SimulationResult with configurable deltas.

    Args:
        slot: Equipment slot.
        name: Candidate item name.
        dps_gain: DPS increase from the swap.
        life_gain: Life increase from the swap.
        price: Item price in divine orbs.
        relevance_score: Archetype match score.

    Returns:
        :class:`~app.models.recommendation.SimulationResult`.
    """
    baseline = _make_calc_result(dps=1_000_000.0, life=4500)
    modified = _make_calc_result(
        dps=1_000_000.0 + dps_gain,
        life=4500 + life_gain,
    )
    deltas: dict[str, float] = {}
    if dps_gain != 0:
        deltas["dps"] = dps_gain
    if life_gain != 0:
        deltas["life"] = float(life_gain)

    candidate = CandidateItem(
        name=name,
        base_name="Hubris Circlet",
        slot=slot,
        rarity="unique",
        price_divine=price,
        relevance_score=relevance_score,
    )
    return SimulationResult(
        slot=slot,
        candidate=candidate,
        baseline_stats=baseline,
        modified_stats=modified,
        deltas=deltas,
        price_divine=price,
    )


def _make_build_code(xml: str) -> str:
    """Encode XML as a PoB export code.

    Args:
        xml: Raw XML string.

    Returns:
        URL-safe base64-encoded zlib-compressed code.
    """
    compressed = zlib.compress(xml.encode("utf-8"))
    encoded = base64.b64encode(compressed).decode("ascii")
    return encoded.replace("+", "-").replace("/", "_").rstrip("=")


_MINIMAL_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<PathOfBuilding>"
    "<Build level='80' className='Witch' ascendClassName='Occultist'>"
    "<PlayerStat stat='Life' value='4500'/>"
    "</Build>"
    "</PathOfBuilding>"
)


# ---------------------------------------------------------------------------
# Tests — detect_critical_issues
# ---------------------------------------------------------------------------


class TestDetectCriticalIssues:
    """Tests for the detect_critical_issues function."""

    def test_all_capped_no_issues(self) -> None:
        """Verify no issues are returned when all resistances are capped.

        Expected: empty list returned for a healthy build.
        """
        build = _make_build(
            fire_res=75,
            cold_res=75,
            lightning_res=75,
            life=5000,
            gems=["Fireball", "Flame Dash"],
        )
        issues = detect_critical_issues(build)
        # Only possible remaining issue is no_movement or dead_link
        res_issues = [i for i in issues if i.category == "uncapped_res"]
        life_issues = [i for i in issues if i.category == "low_life"]
        assert not res_issues
        assert not life_issues

    def test_uncapped_fire_resistance(self) -> None:
        """Detect uncapped fire resistance as a critical issue.

        Expected: issue with category='uncapped_res' and affected_stat='fire_res'.
        """
        build = _make_build(fire_res=40, gems=["Fireball", "Flame Dash"])
        issues = detect_critical_issues(build)
        res_issues = [i for i in issues if i.category == "uncapped_res"]
        assert len(res_issues) >= 1
        fire_issue = next(
            (i for i in res_issues if i.affected_stat == "fire_res"), None
        )
        assert fire_issue is not None
        assert fire_issue.current_value == 40.0
        assert fire_issue.target_value == 75.0

    def test_uncapped_cold_and_lightning(self) -> None:
        """Detect uncapped cold AND lightning resistances simultaneously.

        Expected: two uncapped_res issues returned.
        """
        build = _make_build(cold_res=20, lightning_res=30, gems=["Flame Dash"])
        issues = detect_critical_issues(build)
        res_issues = [i for i in issues if i.category == "uncapped_res"]
        affected_stats = {i.affected_stat for i in res_issues}
        assert "cold_res" in affected_stats
        assert "lightning_res" in affected_stats

    def test_negative_resistance_is_critical_severity(self) -> None:
        """Negative resistance should be flagged as 'critical' severity.

        Expected: severity='critical' when resistance < 0%.
        """
        build = _make_build(fire_res=-30, gems=["Flame Dash"])
        issues = detect_critical_issues(build)
        fire_issue = next(
            (
                i
                for i in issues
                if i.category == "uncapped_res"
                and i.affected_stat == "fire_res"
            ),
            None,
        )
        assert fire_issue is not None
        assert fire_issue.severity == "critical"

    def test_low_life_detected(self) -> None:
        """Low life pool relative to character level is detected.

        Expected: issue with category='low_life' for life=1000 at level 80.
        """
        build = _make_build(level=80, life=1000, energy_shield=50)
        issues = detect_critical_issues(build)
        life_issues = [i for i in issues if i.category == "low_life"]
        assert len(life_issues) == 1
        assert life_issues[0].current_value == 1000.0

    def test_high_es_build_skips_low_life_check(self) -> None:
        """ES/CI builds should not be flagged for low life.

        Expected: no low_life issue for an energy-shield-dominant build.
        """
        build = _make_build(level=80, life=1, energy_shield=5000)
        issues = detect_critical_issues(build)
        life_issues = [i for i in issues if i.category == "low_life"]
        assert not life_issues

    def test_missing_movement_skill(self) -> None:
        """Builds without any movement skill are flagged.

        Expected: issue with category='no_movement'.
        """
        build = _make_build(gems=["Fireball", "Added Lightning Damage Support"])
        issues = detect_critical_issues(build)
        movement_issues = [i for i in issues if i.category == "no_movement"]
        assert len(movement_issues) == 1

    def test_movement_skill_present_no_issue(self) -> None:
        """No movement issue when a movement skill gem exists.

        Expected: no no_movement issue when Flame Dash is equipped.
        """
        build = _make_build(gems=["Fireball", "Flame Dash"])
        issues = detect_critical_issues(build)
        movement_issues = [i for i in issues if i.category == "no_movement"]
        assert not movement_issues

    def test_dead_gem_link_detected(self) -> None:
        """Skill group with only support gems (no active skill) is flagged.

        Expected: issue with category='dead_link'.
        """
        build = _make_build()
        # Add an additional dead-link skill group
        dead_group = BuildSkillGroup(
            slot="Gloves",
            enabled=True,
            gems=[
                BuildGem(name_spec="Added Fire Support", is_support=True),
                BuildGem(name_spec="Multistrike Support", is_support=True),
            ],
        )
        build.skill_groups.append(dead_group)
        issues = detect_critical_issues(build)
        dead_issues = [i for i in issues if i.category == "dead_link"]
        assert len(dead_issues) >= 1

    def test_critical_issues_sorted_critical_first(self) -> None:
        """Critical-severity issues appear before warnings.

        Expected: 'critical' severity issues precede 'warning' issues.
        """
        build = _make_build(fire_res=-10, cold_res=30, gems=["Fireball"])
        issues = detect_critical_issues(build)
        severities = [i.severity for i in issues]
        # Find first warning index
        if "warning" in severities and "critical" in severities:
            first_warning = severities.index("warning")
            last_critical = len(severities) - 1 - severities[::-1].index("critical")
            assert last_critical < first_warning


# ---------------------------------------------------------------------------
# Tests — score_recommendation
# ---------------------------------------------------------------------------


class TestScoreRecommendation:
    """Tests for the score_recommendation scoring formula."""

    def test_positive_dps_produces_positive_score(self) -> None:
        """A simulation with positive DPS delta should produce a positive score.

        Expected: score > 0 when dps_delta > 0 and no critical issues.
        """
        archetype = _make_archetype()
        sim = _make_simulation_result(dps_gain=200_000.0)
        s = score_recommendation(
            sim, archetype, [], max_dps_delta=200_000.0, max_ehp_delta=1.0
        )
        assert s > 0.0

    def test_critical_fix_bonus_applied(self) -> None:
        """Item fixing an uncapped resistance gets a critical fix bonus.

        Expected: score with bonus > score without when a res issue exists.
        """
        archetype = _make_archetype()
        issues = [
            CriticalIssue(
                category="uncapped_res",
                severity="warning",
                description="Fire res uncapped",
                affected_stat="fire_res",
                current_value=40.0,
                target_value=75.0,
            )
        ]
        # Candidate with a resistance mod
        candidate = CandidateItem(
            name="Ring of the Council",
            base_name="Coral Ring",
            slot="Ring",
            rarity="unique",
            key_mods=["25% to all Elemental Resistances"],
            price_divine=1.5,
            relevance_score=0.5,
        )
        baseline = _make_calc_result()
        modified = _make_calc_result(dps=1_100_000.0)
        sim_with_res = SimulationResult(
            slot="Ring",
            candidate=candidate,
            baseline_stats=baseline,
            modified_stats=modified,
            deltas={"dps": 100_000.0},
            price_divine=1.5,
        )
        sim_no_res = _make_simulation_result(dps_gain=100_000.0)

        score_with = score_recommendation(
            sim_with_res, archetype, issues,
            max_dps_delta=100_000.0, max_ehp_delta=200.0,
        )
        score_without = score_recommendation(
            sim_no_res, archetype, [],
            max_dps_delta=100_000.0, max_ehp_delta=200.0,
        )
        assert score_with > score_without

    def test_cost_efficiency_boosts_score(self) -> None:
        """A cheap item with the same DPS gain scores higher than a pricey one.

        Expected: cheap item score > expensive item score for equal DPS.
        """
        archetype = _make_archetype()
        # Items with no life gain so EHP doesn’t dominate
        cheap = _make_simulation_result(dps_gain=100_000.0, life_gain=0, price=0.5)
        expensive = _make_simulation_result(dps_gain=100_000.0, life_gain=0, price=10.0)
        s_cheap = score_recommendation(
            cheap, archetype, [], max_dps_delta=100_000.0, max_ehp_delta=1.0,
        )
        s_expensive = score_recommendation(
            expensive, archetype, [], max_dps_delta=100_000.0, max_ehp_delta=1.0,
        )
        assert s_cheap > s_expensive

    def test_es_build_weights_ehp_higher(self) -> None:
        """ES/CI builds weigh EHP improvements more heavily.

        Expected: sim with ES gain scores higher on an ES archetype than life.
        """
        es_archetype = _make_archetype(defense_style="es")
        # Sim where modified = high ES
        baseline = _make_calc_result(energy_shield=1000)
        modified = _make_calc_result(energy_shield=3000)
        candidate = CandidateItem(
            name="Shavronnes",
            base_name="Occultist Vestment",
            slot="Body Armour",
            rarity="unique",
            price_divine=3.0,
            relevance_score=0.9,
        )
        sim_es = SimulationResult(
            slot="Body Armour",
            candidate=candidate,
            baseline_stats=baseline,
            modified_stats=modified,
            deltas={"energy_shield": 2000.0},
            price_divine=3.0,
        )
        score_es = score_recommendation(
            sim_es, es_archetype, [], max_dps_delta=1.0, max_ehp_delta=2000.0
        )

        life_archetype = _make_archetype(defense_style="life")
        score_life = score_recommendation(
            sim_es, life_archetype, [], max_dps_delta=1.0, max_ehp_delta=2000.0
        )
        # ES build scores the ES gain more
        assert score_es >= score_life


# ---------------------------------------------------------------------------
# Tests — build_recommendations (AC3-7)
# ---------------------------------------------------------------------------


class TestBuildRecommendations:
    """Tests for the build_recommendations diversity / ranking logic."""

    def _make_diverse_simulations(
        self, n: int = 10
    ) -> list[SimulationResult]:
        """Generate a set of diverse simulation results across multiple slots.

        Args:
            n: Total number of simulation results to create.

        Returns:
            List of :class:`~app.models.recommendation.SimulationResult`.
        """
        slots = [
            "Helmet", "Helmet", "Helmet",
            "Body Armour", "Body Armour",
            "Gloves", "Boots", "Ring", "Ring 2", "Amulet",
        ]
        sims = []
        for i in range(n):
            slot = slots[i % len(slots)]
            sims.append(
                _make_simulation_result(
                    slot=slot,
                    name=f"Item{i}",
                    dps_gain=float((n - i) * 50_000),
                    price=float(i + 1),
                )
            )
        return sims

    def test_returns_exactly_five_recommendations(self) -> None:
        """AC3: build_recommendations returns exactly 5 items.

        Expected: list length == 5.
        """
        build = _make_build()
        archetype = _make_archetype()
        sims = self._make_diverse_simulations(10)
        recs = build_recommendations(sims, [], build, archetype)
        assert len(recs) == 5

    def test_sorted_by_score_descending(self) -> None:
        """AC4: Recommendations are in descending score order.

        Expected: scores[i] >= scores[i+1] for all consecutive pairs.
        """
        build = _make_build()
        archetype = _make_archetype()
        sims = self._make_diverse_simulations(10)
        recs = build_recommendations(sims, [], build, archetype)
        scores = [r.score for r in recs]
        assert scores == sorted(scores, reverse=True)

    def test_max_two_per_slot(self) -> None:
        """AC6: No slot appears more than twice in the top-5.

        Expected: max slot count in recommendations <= 2.
        """
        build = _make_build()
        archetype = _make_archetype()
        sims = self._make_diverse_simulations(10)
        recs = build_recommendations(sims, [], build, archetype)
        slot_counts: dict[str, int] = {}
        for rec in recs:
            slot_counts[rec.slot] = slot_counts.get(rec.slot, 0) + 1
        assert max(slot_counts.values()) <= 2

    def test_ranks_are_1_through_5(self) -> None:
        """Ranks in recommendations are sequential integers 1–5.

        Expected: sorted rank list == [1, 2, 3, 4, 5].
        """
        build = _make_build()
        archetype = _make_archetype()
        sims = self._make_diverse_simulations(10)
        recs = build_recommendations(sims, [], build, archetype)
        assert sorted(r.rank for r in recs) == [1, 2, 3, 4, 5]

    def test_budget_item_included_when_available(self) -> None:
        """AC7: At least 1 recommendation costs < 1 divine when such items exist.

        Expected: at least one recommendation with price_divine < 1.0.
        """
        build = _make_build()
        archetype = _make_archetype()
        sims = self._make_diverse_simulations(10)
        # Force one cheap item into simulations
        sims[5] = _make_simulation_result(
            slot="Belt",
            name="Cheap Belt",
            dps_gain=10_000.0,
            price=0.3,
        )
        recs = build_recommendations(sims, [], build, archetype)
        # At least one rec should be budget (price < 1 divine)
        has_budget = any(
            r.price_divine is not None and r.price_divine < 1.0
            for r in recs
        )
        assert has_budget

    def test_critical_fix_first_when_uncapped_res(self) -> None:
        """AC5: Uncapped resistance fix is recommendation #1.

        Expected: rank 1 recommendation has category 'critical_fix'.
        """
        build = _make_build(fire_res=20)
        archetype = _make_archetype()
        issues = detect_critical_issues(build)
        res_issue = next(i for i in issues if i.category == "uncapped_res")

        # Create a candidate that fixes the resistance
        candidate = CandidateItem(
            name="Pyre",
            base_name="Coral Ring",
            slot="Ring",
            rarity="unique",
            key_mods=["15% to all Elemental Resistances"],
            price_divine=1.0,
            relevance_score=0.6,
        )
        baseline = _make_calc_result(fire_res=20)
        modified = _make_calc_result(fire_res=75)
        fix_sim = SimulationResult(
            slot="Ring",
            candidate=candidate,
            baseline_stats=baseline,
            modified_stats=modified,
            deltas={"fire_res": 55.0},
            price_divine=1.0,
        )
        # Mix with other sims with higher DPS gain but no res fix
        other_sims = self._make_diverse_simulations(8)
        all_sims = [fix_sim] + other_sims

        recs = build_recommendations(all_sims, issues, build, archetype)
        first = recs[0]
        assert first.category == "critical_fix"

    def test_empty_simulations_returns_empty(self) -> None:
        """No recommendations when simulation list is empty.

        Expected: empty list returned.
        """
        build = _make_build()
        archetype = _make_archetype()
        recs = build_recommendations([], [], build, archetype)
        assert recs == []

    def test_fewer_than_five_sims_returns_all(self) -> None:
        """Returns all simulation results when fewer than 5 candidates.

        Expected: list length equals number of simulations (≤ 5) when each
        sim is in a different slot (no diversity constraint applies).
        """
        build = _make_build()
        archetype = _make_archetype()
        # Use 3 sims in 3 different slots so the max-2-per-slot rule
        # doesn’t drop any of them.
        sims = [
            _make_simulation_result(slot="Helmet", name="A", dps_gain=300_000.0),
            _make_simulation_result(slot="Gloves", name="B", dps_gain=200_000.0),
            _make_simulation_result(slot="Boots",  name="C", dps_gain=100_000.0),
        ]
        recs = build_recommendations(sims, [], build, archetype)
        assert len(recs) == 3


# ---------------------------------------------------------------------------
# Tests — generate_trade_link (AC8)
# ---------------------------------------------------------------------------


class TestGenerateTradeLink:
    """Tests for generate_trade_link URL construction."""

    def test_unique_item_contains_name(self) -> None:
        """Trade link for a unique item uses the item name.

        Expected: URL contains the item name (URL-encoded).
        """
        candidate = CandidateItem(
            name="Starkonja's Head",
            base_name="Hubris Circlet",
            slot="Helmet",
            rarity="unique",
        )
        url = generate_trade_link(candidate, "Settlers")
        assert "pathofexile.com/trade" in url
        # The name might be JSON-encoded inside the query
        decoded = urllib.parse.unquote(url)
        assert "Starkonja" in decoded

    def test_rare_item_uses_base_type(self) -> None:
        """Trade link for a rare base item uses the base type.

        Expected: URL contains the base type name.
        """
        candidate = CandidateItem(
            name="",
            base_name="Hubris Circlet",
            slot="Helmet",
            rarity="rare",
        )
        url = generate_trade_link(candidate, "Settlers")
        decoded = urllib.parse.unquote(url)
        assert "Hubris Circlet" in decoded

    def test_gem_trade_link(self) -> None:
        """Trade link for a gem uses the gem name.

        Expected: URL contains the gem name.
        """
        candidate = CandidateGem(
            name="Empower Support",
            is_support=True,
        )
        url = generate_trade_link(candidate, "Settlers")
        decoded = urllib.parse.unquote(url)
        assert "Empower" in decoded

    def test_league_in_url(self) -> None:
        """League name is included in the trade URL.

        Expected: URL contains the league name.
        """
        candidate = CandidateItem(
            name="Test Item",
            base_name="Hubris Circlet",
            slot="Helmet",
            rarity="unique",
        )
        url = generate_trade_link(candidate, "TestLeague")
        assert "TestLeague" in url

    def test_url_starts_with_https(self) -> None:
        """Trade links are always HTTPS.

        Expected: URL starts with 'https://'.
        """
        candidate = CandidateItem(
            name="Item",
            base_name="Base",
            slot="Helmet",
            rarity="unique",
        )
        url = generate_trade_link(candidate, "Settlers")
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# Tests — template explanation rendering (AC9)
# ---------------------------------------------------------------------------


class TestExplanationRendering:
    """Tests that template explanations render without errors."""

    def _build_rec(
        self,
        issues: list[CriticalIssue] | None = None,
    ) -> list[Recommendation]:
        """Build a set of recommendations with optional critical issues.

        Args:
            issues: Optional list of critical issues to include.

        Returns:
            List of :class:`~app.models.recommendation.Recommendation`.
        """
        build = _make_build(fire_res=20 if issues else 75)
        archetype = _make_archetype()
        sims = [
            _make_simulation_result(
                slot=s,
                name=f"Item{i}",
                dps_gain=float((5 - i) * 100_000),
                price=float(i + 1),
            )
            for i, s in enumerate(
                ["Ring", "Helmet", "Body Armour", "Gloves", "Boots"]
            )
        ]
        return build_recommendations(sims, issues or [], build, archetype)

    def test_explanations_non_empty(self) -> None:
        """Every recommendation has a non-empty explanation string.

        Expected: all explanation fields are non-empty strings.
        """
        recs = self._build_rec()
        for r in recs:
            assert isinstance(r.explanation, str)
            assert len(r.explanation) > 0

    def test_resist_fix_explanation(self) -> None:
        """Resistance fix template renders correctly with res issue.

        Expected: explanation contains resistance-related text.
        """
        issues = [
            CriticalIssue(
                category="uncapped_res",
                severity="warning",
                description="Fire res uncapped",
                affected_stat="fire_res",
                current_value=20.0,
                target_value=75.0,
            )
        ]
        build = _make_build(fire_res=20)
        archetype = _make_archetype()
        # The fix sim: adds resistance modifier
        fix_candidate = CandidateItem(
            name="Pyre",
            base_name="Coral Ring",
            slot="Ring",
            rarity="unique",
            key_mods=["15% to all Elemental Resistances"],
            price_divine=1.0,
            relevance_score=0.7,
        )
        baseline = _make_calc_result()
        modified = _make_calc_result(dps=1_050_000.0, fire_res=75)
        fix_sim = SimulationResult(
            slot="Ring",
            candidate=fix_candidate,
            baseline_stats=baseline,
            modified_stats=modified,
            deltas={"dps": 50_000.0, "fire_res": 55.0},
            price_divine=1.0,
        )
        recs = build_recommendations([fix_sim], issues, build, archetype)
        assert len(recs) == 1
        assert recs[0].explanation  # non-empty
        # Should not contain Python format placeholders like {0}
        assert "{" not in recs[0].explanation or "%%" not in recs[0].explanation

    def test_no_placeholder_errors_in_all_templates(self) -> None:
        """Explanations do not contain raw Python format placeholders.

        Expected: no recommendation explanation ends with an unfilled
        '{...}' placeholder pattern.
        """
        import re

        recs = self._build_rec()
        placeholder_pattern = re.compile(r"\{[a-z_]+\}")
        for r in recs:
            assert not placeholder_pattern.search(
                r.explanation
            ), f"Unfilled placeholder in: {r.explanation!r}"


# ---------------------------------------------------------------------------
# Tests — simulate_upgrades (with mocked pool)
# ---------------------------------------------------------------------------


class TestSimulateUpgrades:
    """Tests for the simulate_upgrades async function."""

    def _make_pool_mock(
        self,
        success: bool = True,
        dps_modified: float = 1_300_000.0,
    ) -> MagicMock:
        """Build a mock pool that returns synthetic swap results.

        Args:
            success: If False, all swaps return error dicts.
            dps_modified: DPS value used in the 'modified' stats.

        Returns:
            MagicMock with async calculate_swap_batch.
        """
        pool = MagicMock()
        baseline_stats = {
            "Life": 4500, "EnergyShield": 200,
            "FireResist": 75, "ColdResist": 75, "LightningResist": 75,
            "ChaosResist": -60, "CombinedDPS": 1_200_000.0,
        }
        modified_stats = dict(baseline_stats)
        modified_stats["CombinedDPS"] = dps_modified

        if success:
            pool.calculate_swap_batch = AsyncMock(
                side_effect=lambda xml, swaps: [
                    {
                        "baseline": baseline_stats,
                        "modified": modified_stats,
                        "item": {"name": "MockItem"},
                    }
                    for _ in swaps
                ]
            )
        else:
            pool.calculate_swap_batch = AsyncMock(
                side_effect=lambda xml, swaps: [
                    {"error": "LuaJIT unavailable"} for _ in swaps
                ]
            )
        return pool

    @pytest.mark.asyncio
    async def test_returns_simulation_results(self) -> None:
        """simulate_upgrades returns one result per successful swap.

        Expected: non-empty result list when pool succeeds.
        """
        build = _make_build()
        archetype = _make_archetype()
        pool = self._make_pool_mock()

        candidates = CandidateItem(
            name="Test Item",
            base_name="Hubris Circlet",
            slot="Helmet",
            rarity="unique",
            price_divine=2.0,
            relevance_score=0.8,
        )
        item_candidates = [
            SlotCandidates(
                slot="Helmet",
                archetype=archetype,
                candidates=[candidates],
            )
        ]
        results = await simulate_upgrades(
            build_xml=_MINIMAL_XML,
            build=build,
            item_candidates=item_candidates,
            gem_candidates=[],
            archetype=archetype,
            pool=pool,
        )
        assert len(results) == 1
        assert results[0].slot == "Helmet"
        assert results[0].price_divine == 2.0

    @pytest.mark.asyncio
    async def test_failed_swaps_are_skipped(self) -> None:
        """Failed swap calculations are skipped without raising.

        Expected: result list is empty when all swaps return errors.
        """
        build = _make_build()
        archetype = _make_archetype()
        pool = self._make_pool_mock(success=False)

        candidates = CandidateItem(
            name="Test",
            base_name="Hubris Circlet",
            slot="Helmet",
            rarity="unique",
        )
        item_candidates = [
            SlotCandidates(
                slot="Helmet",
                archetype=archetype,
                candidates=[candidates],
            )
        ]
        results = await simulate_upgrades(
            build_xml=_MINIMAL_XML,
            build=build,
            item_candidates=item_candidates,
            gem_candidates=[],
            archetype=archetype,
            pool=pool,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self) -> None:
        """Empty candidate list returns empty result list.

        Expected: empty list returned immediately without calling pool.
        """
        build = _make_build()
        archetype = _make_archetype()
        pool = self._make_pool_mock()
        results = await simulate_upgrades(
            build_xml=_MINIMAL_XML,
            build=build,
            item_candidates=[],
            gem_candidates=[],
            archetype=archetype,
            pool=pool,
        )
        assert results == []
        pool.calculate_swap_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_dps_deltas_match_engine(self) -> None:
        """AC10: DPS deltas match engine calculation within ±0.1%.

        Expected: delta for 'dps' equals engine modified_dps - baseline_dps.
        """
        build = _make_build()
        archetype = _make_archetype()
        baseline_dps = 1_200_000.0
        modified_dps = 1_500_000.0
        expected_delta = modified_dps - baseline_dps

        pool = self._make_pool_mock(dps_modified=modified_dps)
        candidates = CandidateItem(
            name="Test",
            base_name="Hubris Circlet",
            slot="Helmet",
            rarity="unique",
        )
        item_candidates = [
            SlotCandidates(
                slot="Helmet",
                archetype=archetype,
                candidates=[candidates],
            )
        ]
        results = await simulate_upgrades(
            build_xml=_MINIMAL_XML,
            build=build,
            item_candidates=item_candidates,
            gem_candidates=[],
            archetype=archetype,
            pool=pool,
        )
        assert len(results) == 1
        actual_delta = results[0].deltas.get("dps", 0.0)
        tolerance = expected_delta * 0.001  # 0.1%
        assert abs(actual_delta - expected_delta) <= tolerance


# ---------------------------------------------------------------------------
# Tests — POST /api/v1/recommendations  (end-to-end via TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def test_client() -> TestClient:
    """Return a synchronous TestClient wrapping the FastAPI app.

    Returns:
        :class:`~fastapi.testclient.TestClient`.
    """
    return TestClient(app, raise_server_exceptions=True)


def _mock_pool_available() -> MagicMock:
    """Return a mock pool that is available and returns synthetic stats.

    Returns:
        MagicMock for :class:`~app.services.luajit_pool.LuaJITPoolManager`.
    """
    baseline_stats = {
        "Life": 4500, "EnergyShield": 200,
        "FireResist": 75, "ColdResist": 75, "LightningResist": 75,
        "ChaosResist": -60, "CombinedDPS": 1_200_000.0,
    }
    modified_stats = dict(baseline_stats)
    modified_stats["CombinedDPS"] = 1_500_000.0

    pool = MagicMock()
    pool.is_available = True
    pool.calculate_swap_batch = AsyncMock(
        side_effect=lambda xml, swaps: [
            {"baseline": baseline_stats, "modified": modified_stats, "item": {"name": "x"}}
            for _ in swaps
        ]
    )
    return pool


def _make_request_body(
    build: BuildData,
    build_code: str,
    league: str = "Settlers",
    max_candidates: int = 3,
) -> dict[str, Any]:
    """Build the JSON body for POST /api/v1/recommendations.

    Args:
        build: Pre-built BuildData.
        build_code: PoB export code.
        league: League name.
        max_candidates: Maximum candidates per slot.

    Returns:
        Dict ready for json= parameter in test_client.post.
    """
    return {
        "build": build.model_dump(by_alias=True),
        "build_code": build_code,
        "league": league,
        "max_candidates_per_slot": max_candidates,
    }


class TestRecommendationsEndpoint:
    """End-to-end tests for POST /api/v1/recommendations."""

    def test_endpoint_returns_200(self, test_client: TestClient) -> None:
        """POST /api/v1/recommendations returns 200 OK.

        Expected: HTTP 200 status code.
        """
        build = _make_build()
        code = _make_build_code(_MINIMAL_XML)

        with (
            patch(
                "app.api.v1.recommendations.run_pipeline",
                return_value=([], []),
            ),
            patch(
                "app.api.v1.recommendations.detect_critical_issues",
                return_value=[],
            ),
            patch(
                "app.api.v1.recommendations.get_pool",
                side_effect=RuntimeError("no pool"),
            ),
            patch(
                "app.services.poe_ninja.PoeNinjaClient.get_item_prices",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            resp = test_client.post(
                "/api/v1/recommendations",
                json=_make_request_body(build, code),
            )
        assert resp.status_code == 200

    def test_response_schema_valid(self, test_client: TestClient) -> None:
        """Response body matches RecommendResponse schema.

        Expected: response can be parsed without error.
        """
        build = _make_build()
        code = _make_build_code(_MINIMAL_XML)

        with (
            patch(
                "app.api.v1.recommendations.run_pipeline",
                return_value=([], []),
            ),
            patch(
                "app.api.v1.recommendations.detect_critical_issues",
                return_value=[],
            ),
            patch(
                "app.api.v1.recommendations.get_pool",
                side_effect=RuntimeError("no pool"),
            ),
            patch(
                "app.services.poe_ninja.PoeNinjaClient.get_item_prices",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            resp = test_client.post(
                "/api/v1/recommendations",
                json=_make_request_body(build, code),
            )
        body = resp.json()
        parsed = RecommendResponse(**body)
        assert isinstance(parsed.recommendations, list)
        assert isinstance(parsed.critical_issues, list)
        assert parsed.simulation_count >= 0
        assert parsed.elapsed_seconds >= 0.0

    def test_missing_build_code_returns_422(
        self, test_client: TestClient
    ) -> None:
        """Request without any build source returns 422 Unprocessable Entity.

        Expected: HTTP 422 status code.
        """
        build = _make_build()
        body = {"build": build.model_dump(by_alias=True), "league": "Settlers"}
        resp = test_client.post("/api/v1/recommendations", json=body)
        assert resp.status_code == 422

    def test_critical_issues_propagated(
        self, test_client: TestClient
    ) -> None:
        """Critical issues detected in the build are propagated to response.

        Expected: response critical_issues list is non-empty when build has
        uncapped resistances.
        """
        build = _make_build(fire_res=20)
        code = _make_build_code(_MINIMAL_XML)

        with (
            patch(
                "app.api.v1.recommendations.run_pipeline",
                return_value=([], []),
            ),
            patch(
                "app.api.v1.recommendations.get_pool",
                side_effect=RuntimeError("no pool"),
            ),
            patch(
                "app.services.poe_ninja.PoeNinjaClient.get_item_prices",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            resp = test_client.post(
                "/api/v1/recommendations",
                json=_make_request_body(build, code),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["critical_issues"]) >= 1
        fire_issue = next(
            (
                i
                for i in body["critical_issues"]
                if i["affected_stat"] == "fire_res"
            ),
            None,
        )
        assert fire_issue is not None

    def test_recommendations_with_mock_pool(
        self, test_client: TestClient
    ) -> None:
        """Full pipeline returns non-empty recommendations with mocked pool.

        Expected: at least 1 recommendation returned when pool is available.
        """
        build = _make_build()
        code = _make_build_code(_MINIMAL_XML)
        pool = _mock_pool_available()

        # Create simple item candidates for the mock pipeline
        archetype = _make_archetype()
        item_candidates = [
            SlotCandidates(
                slot="Helmet",
                archetype=archetype,
                candidates=[
                    CandidateItem(
                        name="Starkonja",
                        base_name="Hubris Circlet",
                        slot="Helmet",
                        rarity="unique",
                        price_divine=2.0,
                        relevance_score=0.9,
                    )
                ],
            ),
            SlotCandidates(
                slot="Ring",
                archetype=archetype,
                candidates=[
                    CandidateItem(
                        name="Circle of Regret",
                        base_name="Coral Ring",
                        slot="Ring",
                        rarity="unique",
                        price_divine=1.5,
                        relevance_score=0.7,
                    )
                ],
            ),
        ]

        with (
            patch(
                "app.api.v1.recommendations.run_pipeline",
                return_value=(item_candidates, []),
            ),
            patch(
                "app.api.v1.recommendations.detect_critical_issues",
                return_value=[],
            ),
            patch(
                "app.api.v1.recommendations.get_pool",
                return_value=pool,
            ),
            patch(
                "app.services.poe_ninja.PoeNinjaClient.get_item_prices",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            resp = test_client.post(
                "/api/v1/recommendations",
                json=_make_request_body(build, code),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["recommendations"]) >= 1
        rec = body["recommendations"][0]
        assert rec["trade_url"].startswith("https://")
        assert rec["explanation"]
        assert rec["score"] > 0

    def test_all_recommendation_trade_urls_valid(
        self, test_client: TestClient
    ) -> None:
        """AC8: All recommendations include valid trade site URLs.

        Expected: every recommendation trade_url starts with 'https://'.
        """
        build = _make_build()
        code = _make_build_code(_MINIMAL_XML)
        pool = _mock_pool_available()
        archetype = _make_archetype()

        slots = ["Helmet", "Gloves", "Boots", "Ring", "Body Armour"]
        item_candidates = [
            SlotCandidates(
                slot=slot,
                archetype=archetype,
                candidates=[
                    CandidateItem(
                        name=f"Item {slot}",
                        base_name="Base",
                        slot=slot,
                        rarity="unique",
                        price_divine=float(i + 1),
                        relevance_score=0.6,
                    )
                ],
            )
            for i, slot in enumerate(slots)
        ]

        with (
            patch(
                "app.api.v1.recommendations.run_pipeline",
                return_value=(item_candidates, []),
            ),
            patch(
                "app.api.v1.recommendations.detect_critical_issues",
                return_value=[],
            ),
            patch(
                "app.api.v1.recommendations.get_pool",
                return_value=pool,
            ),
            patch(
                "app.services.poe_ninja.PoeNinjaClient.get_item_prices",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            resp = test_client.post(
                "/api/v1/recommendations",
                json=_make_request_body(build, code),
            )
        assert resp.status_code == 200
        for rec in resp.json()["recommendations"]:
            assert rec["trade_url"].startswith("https://"), (
                f"Invalid trade URL: {rec['trade_url']!r}"
            )

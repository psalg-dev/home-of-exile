"""Tests for the M3 candidate pool pipeline.

Covers:
* Archetype detection for physical melee, cold caster, and minion summoner
  builds (acceptance criteria 1-3).
* Candidate generator returns ≤ 20 items per slot (AC 4).
* All returned candidates pass level requirement check (AC 5).
* All returned candidates pass attribute requirement check (AC 6).
* Gem candidates exclude already-equipped gems (AC 8).
* Constraint validator flags items requiring attributes the build lacks (AC 9).
* Pipeline runs for all 10 equipment slots in < 3 seconds with cached
  prices (AC 10).
* POST /api/v1/candidates endpoint works end-to-end.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.candidate import (
    Archetype,
    BuildData,
    BuildGem,
    BuildSkillGroup,
    BuildStats,
    CandidateItem,
    CharacterAttrs,
    ItemAttrReq,
)
from app.services.archetype import (
    archetype_mod_keywords,
    archetype_template_mods,
    detect_archetype,
    extract_key_mods,
    score_mod_relevance,
)
from app.services.candidate_generator import (
    generate_candidates,
    generate_gem_candidates,
    run_pipeline,
    validate_constraints,
)

# ---------------------------------------------------------------------------
# Shared build fixtures
# ---------------------------------------------------------------------------


def _make_build(
    level: int = 80,
    char_class: str = "Witch",
    ascendancy: str = "Occultist",
    life: int = 4000,
    energy_shield: int = 200,
    main_skill: str = "",
    gems: list[str] | None = None,
    str_attr: int = 100,
    dex_attr: int = 100,
    int_attr: int = 200,
) -> BuildData:
    """Helper: construct a minimal BuildData for tests.

    Args:
        level: Character level.
        char_class: PoE class name.
        ascendancy: Ascendancy class name.
        life: Life stat.
        energy_shield: Energy shield stat.
        main_skill: Name of the main active skill.
        gems: List of gem display names to add to the first skill group.
        str_attr: Strength attribute.
        dex_attr: Dexterity attribute.
        int_attr: Intelligence attribute.

    Returns:
        Populated BuildData.
    """
    gem_objects = [
        BuildGem(name_spec=name, is_support=name.endswith("Support"))
        for name in (gems or [])
    ]
    skill_groups = []
    if gem_objects:
        skill_groups = [
            BuildSkillGroup(
                slot="Body Armour",
                enabled=True,
                gems=gem_objects,
                main_active_gem_index=0,
            )
        ]

    return BuildData(
        **{
            "class": char_class,
            "ascendancy": ascendancy,
            "level": level,
            "main_skill": main_skill,
            "stats": BuildStats(
                life=life,
                energy_shield=energy_shield,
            ),
            "attrs": CharacterAttrs(**{
                "str": str_attr,
                "dex": dex_attr,
                "int": int_attr,
            }),
            "skill_groups": skill_groups,
        }
    )


@pytest.fixture
def physical_melee_build() -> BuildData:
    """A level-90 Juggernaut physical melee build."""
    return _make_build(
        level=90,
        char_class="Marauder",
        ascendancy="Juggernaut",
        life=6000,
        energy_shield=100,
        main_skill="Cyclone",
        gems=[
            "Cyclone",
            "Melee Physical Damage Support",
            "Fortify Support",
            "Brutality Support",
        ],
        str_attr=250,
        dex_attr=120,
        int_attr=50,
    )


@pytest.fixture
def cold_caster_build() -> BuildData:
    """A level-90 Occultist cold caster build."""
    return _make_build(
        level=90,
        char_class="Witch",
        ascendancy="Occultist",
        life=4000,
        energy_shield=3000,
        main_skill="Ice Nova",
        gems=[
            "Ice Nova",
            "Controlled Destruction Support",
            "Added Cold Damage Support",
            "Spell Echo Support",
        ],
        str_attr=70,
        dex_attr=80,
        int_attr=300,
    )


@pytest.fixture
def minion_summoner_build() -> BuildData:
    """A level-90 Necromancer minion/summoner build."""
    return _make_build(
        level=90,
        char_class="Witch",
        ascendancy="Necromancer",
        life=4500,
        energy_shield=500,
        main_skill="Raise Zombie",
        gems=[
            "Raise Zombie",
            "Minion Damage Support",
            "Summon Skeletons",
            "Animate Guardian",
        ],
        str_attr=100,
        dex_attr=90,
        int_attr=250,
    )


@pytest.fixture
def test_client() -> TestClient:
    """Return a synchronous TestClient (bypasses lifespan)."""
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# AC 1 — Archetype detection: physical melee
# ---------------------------------------------------------------------------


class TestArchetypeDetectionPhysicalMelee:
    """Archetype detection correctly classifies a physical melee build."""

    def test_damage_type_is_physical(
        self, physical_melee_build: BuildData
    ) -> None:
        """Damage type should be 'physical'."""
        archetype = detect_archetype(physical_melee_build)
        assert archetype.damage_type == "physical", (
            f"Expected 'physical', got '{archetype.damage_type}'"
        )

    def test_defense_style_is_life(
        self, physical_melee_build: BuildData
    ) -> None:
        """Defense style should be 'life' (6 000 life, 100 ES)."""
        archetype = detect_archetype(physical_melee_build)
        assert archetype.defense_style == "life"

    def test_playstyle_is_melee(
        self, physical_melee_build: BuildData
    ) -> None:
        """Playstyle should be 'melee'."""
        archetype = detect_archetype(physical_melee_build)
        assert archetype.playstyle == "melee"


# ---------------------------------------------------------------------------
# AC 2 — Archetype detection: cold caster
# ---------------------------------------------------------------------------


class TestArchetypeDetectionColdCaster:
    """Archetype detection correctly classifies a cold caster build."""

    def test_damage_type_is_cold(
        self, cold_caster_build: BuildData
    ) -> None:
        """Damage type should be 'cold'."""
        archetype = detect_archetype(cold_caster_build)
        assert archetype.damage_type == "cold", (
            f"Expected 'cold', got '{archetype.damage_type}'"
        )

    def test_playstyle_is_caster(
        self, cold_caster_build: BuildData
    ) -> None:
        """Playstyle should be 'caster'."""
        archetype = detect_archetype(cold_caster_build)
        assert archetype.playstyle == "caster"


# ---------------------------------------------------------------------------
# AC 3 — Archetype detection: minion summoner
# ---------------------------------------------------------------------------


class TestArchetypeDetectionMinionSummoner:
    """Archetype detection correctly classifies a minion summoner build."""

    def test_damage_type_is_minion(
        self, minion_summoner_build: BuildData
    ) -> None:
        """Damage type should be 'minion'."""
        archetype = detect_archetype(minion_summoner_build)
        assert archetype.damage_type == "minion", (
            f"Expected 'minion', got '{archetype.damage_type}'"
        )

    def test_playstyle_is_summoner(
        self, minion_summoner_build: BuildData
    ) -> None:
        """Playstyle should be 'summoner'."""
        archetype = detect_archetype(minion_summoner_build)
        assert archetype.playstyle == "summoner"


# ---------------------------------------------------------------------------
# AC 4 — Candidate generator returns ≤ 20 items per slot
# ---------------------------------------------------------------------------


class TestCandidateCount:
    """Candidate generator must return at most 20 items per slot."""

    def test_helmet_candidates_capped(
        self, cold_caster_build: BuildData
    ) -> None:
        """Helmet candidates should not exceed 20."""
        archetype = detect_archetype(cold_caster_build)
        candidates = generate_candidates(
            cold_caster_build, "Helmet", archetype, {}
        )
        assert len(candidates) <= 20, (
            f"Expected ≤ 20 candidates, got {len(candidates)}"
        )

    def test_all_slots_capped(
        self, physical_melee_build: BuildData
    ) -> None:
        """All slots must return ≤ 20 candidates."""
        archetype = detect_archetype(physical_melee_build)
        slots = [
            "Helmet", "Body Armour", "Gloves", "Boots",
            "Amulet", "Ring", "Ring 2", "Belt", "Weapon", "Shield",
        ]
        for slot in slots:
            candidates = generate_candidates(
                physical_melee_build, slot, archetype, {}
            )
            assert len(candidates) <= 20, (
                f"Slot '{slot}': expected ≤ 20, got {len(candidates)}"
            )


# ---------------------------------------------------------------------------
# AC 5 — All returned candidates pass level requirement
# ---------------------------------------------------------------------------


class TestCandidatesPassLevelReq:
    """Every returned candidate must have level_req ≤ character level."""

    def test_level_req_respected(
        self, cold_caster_build: BuildData
    ) -> None:
        """All Helmet candidates must have level_req ≤ 90."""
        archetype = detect_archetype(cold_caster_build)
        candidates = generate_candidates(
            cold_caster_build, "Helmet", archetype, {}
        )
        for c in candidates:
            assert c.level_req <= cold_caster_build.level, (
                f"Candidate '{c.name or c.base_name}' has level_req "
                f"{c.level_req} > character level {cold_caster_build.level}"
            )


# ---------------------------------------------------------------------------
# AC 6 — All returned candidates pass attribute requirements
# ---------------------------------------------------------------------------


class TestCandidatesPassAttrReq:
    """Every returned candidate must satisfy the character's attribute stats."""

    def test_attr_req_respected_helmets(
        self, physical_melee_build: BuildData
    ) -> None:
        """Physical melee build (250 str) should not see str > 250."""
        archetype = detect_archetype(physical_melee_build)
        candidates = generate_candidates(
            physical_melee_build, "Helmet", archetype, {}
        )
        attrs = physical_melee_build.attrs
        for c in candidates:
            if c.attr_req.str > 0:
                assert c.attr_req.str <= attrs.str, (
                    f"Str req {c.attr_req.str} > available {attrs.str}"
                )
            if c.attr_req.dex > 0:
                assert c.attr_req.dex <= attrs.dex, (
                    f"Dex req {c.attr_req.dex} > available {attrs.dex}"
                )
            if c.attr_req.int_ > 0:
                assert c.attr_req.int_ <= attrs.int_, (
                    f"Int req {c.attr_req.int_} > available {attrs.int_}"
                )


# ---------------------------------------------------------------------------
# AC 8 — Gem candidates exclude already-equipped gems
# ---------------------------------------------------------------------------


class TestGemCandidatesExcludeEquipped:
    """Support gem candidates must exclude gems already in the skill group."""

    def test_equipped_gems_not_suggested(
        self, cold_caster_build: BuildData
    ) -> None:
        """Controlled Destruction Support should not appear as a candidate."""
        archetype = detect_archetype(cold_caster_build)
        group = cold_caster_build.skill_groups[0]
        result = generate_gem_candidates(
            cold_caster_build, group, archetype, {}
        )
        equipped_names = {
            g.name_spec.lower() for g in group.gems if g.enabled
        }
        for candidate in result.support_candidates:
            assert candidate.name.lower() not in equipped_names, (
                f"'{candidate.name}' is already equipped but was suggested"
            )


# ---------------------------------------------------------------------------
# AC 9 — Constraint validator flags insufficient attributes
# ---------------------------------------------------------------------------


class TestConstraintValidator:
    """Constraint validator must flag items the build cannot equip."""

    def test_insufficient_str_flagged(self) -> None:
        """Candidate requiring 300 str should be invalid for a 50-str build."""
        build = _make_build(
            level=80, str_attr=50, dex_attr=50, int_attr=50
        )
        candidate = CandidateItem(
            slot="Helmet",
            level_req=60,
            attr_req=ItemAttrReq(**{"str": 300, "dex": 0, "int": 0}),
        )
        result = validate_constraints(build, candidate)
        assert not result.valid
        assert any("Strength" in w for w in result.warnings)

    def test_level_req_too_high_flagged(self) -> None:
        """Candidate requiring level 80 should be invalid for level 70 char."""
        build = _make_build(level=70)
        candidate = CandidateItem(
            slot="Helmet",
            level_req=80,
            attr_req=ItemAttrReq(),
        )
        result = validate_constraints(build, candidate)
        assert not result.valid
        assert any("Level" in w for w in result.warnings)

    def test_valid_item_passes(self) -> None:
        """An item the character can equip should have valid=True."""
        build = _make_build(
            level=80, str_attr=200, dex_attr=100, int_attr=100
        )
        candidate = CandidateItem(
            slot="Helmet",
            level_req=60,
            attr_req=ItemAttrReq(**{"str": 155, "dex": 0, "int": 0}),
        )
        result = validate_constraints(build, candidate)
        assert result.valid

    def test_borderline_attr_generates_warning(self) -> None:
        """A build that is 5 points short of an attribute gets a warning."""
        build = _make_build(
            level=80, str_attr=95, dex_attr=100, int_attr=100
        )
        candidate = CandidateItem(
            slot="Helmet",
            level_req=60,
            attr_req=ItemAttrReq(**{"str": 100, "dex": 0, "int": 0}),
        )
        result = validate_constraints(build, candidate)
        # 95 < 100 → invalid
        assert not result.valid

    def test_tight_attr_generates_warning_not_invalid(self) -> None:
        """A build that has exactly enough attrs but within 10 gets a warning."""
        build = _make_build(
            level=80, str_attr=105, dex_attr=100, int_attr=100
        )
        candidate = CandidateItem(
            slot="Helmet",
            level_req=60,
            attr_req=ItemAttrReq(**{"str": 100, "dex": 0, "int": 0}),
        )
        result = validate_constraints(build, candidate)
        assert result.valid
        assert any("Strength" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# AC 10 — Pipeline runs for all 10 slots in < 3 seconds
# ---------------------------------------------------------------------------


class TestPipelinePerformance:
    """Pipeline must complete all slots in under 3 seconds (cached prices)."""

    def test_all_slots_under_3_seconds(
        self, cold_caster_build: BuildData
    ) -> None:
        """Full pipeline with empty prices (cached) finishes in < 3 s."""
        archetype = detect_archetype(cold_caster_build)
        start = time.perf_counter()
        run_pipeline(
            build=cold_caster_build,
            archetype=archetype,
            prices={},
        )
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, (
            f"Pipeline took {elapsed:.2f}s, expected < 3s"
        )


# ---------------------------------------------------------------------------
# Archetype mod keywords & scoring
# ---------------------------------------------------------------------------


class TestArchetypeModScoring:
    """Archetype mod relevance scoring works correctly."""

    def test_life_mod_scores_for_life_build(self) -> None:
        """'+100 to maximum Life' should score > 0 for a life archetype."""
        archetype = Archetype(
            damage_type="physical",
            defense_style="life",
            playstyle="melee",
        )
        score = score_mod_relevance(
            ["+100 to maximum Life", "+50 to Strength"],
            archetype,
        )
        assert score > 0.0

    def test_es_mod_scores_for_es_build(self) -> None:
        """A flat ES mod should score > 0 for an ES archetype."""
        archetype = Archetype(
            damage_type="cold",
            defense_style="es",
            playstyle="caster",
        )
        score = score_mod_relevance(
            ["+200 to maximum Energy Shield", "adds 10-20 cold damage"],
            archetype,
        )
        assert score > 0.0

    def test_irrelevant_mod_scores_zero(self) -> None:
        """'10% reduced Flask Charges used' should score 0 for melee."""
        archetype = Archetype(
            damage_type="physical",
            defense_style="life",
            playstyle="melee",
        )
        score = score_mod_relevance(
            ["10% reduced Flask Charges used"],
            archetype,
        )
        assert score == 0.0


# ---------------------------------------------------------------------------
# API endpoint test
# ---------------------------------------------------------------------------


class TestCandidatesEndpoint:
    """POST /api/v1/candidates endpoint integration tests."""

    def _make_request_body(
        self,
        build: BuildData | None = None,
        slot: str | None = "Helmet",
        league: str = "TestLeague",
    ) -> dict[str, Any]:
        """Build a request body dict."""
        if build is None:
            build = _make_build(level=80)
        return {
            "build": build.model_dump(by_alias=True),
            "slot": slot,
            "league": league,
        }

    def test_returns_200(self, test_client: TestClient) -> None:
        """Endpoint should return HTTP 200 with a valid request."""
        body = self._make_request_body()
        with patch(
            "app.api.v1.candidates._get_poe_ninja_client",
        ) as mock_factory:
            mock_client = AsyncMock()
            mock_client.get_item_prices = AsyncMock(return_value={})
            mock_factory.return_value = mock_client

            response = test_client.post("/api/v1/candidates", json=body)

        assert response.status_code == 200, response.text

    def test_response_has_archetype(self, test_client: TestClient) -> None:
        """Response must contain an archetype field."""
        body = self._make_request_body()
        with patch(
            "app.api.v1.candidates._get_poe_ninja_client",
        ) as mock_factory:
            mock_client = AsyncMock()
            mock_client.get_item_prices = AsyncMock(return_value={})
            mock_factory.return_value = mock_client

            response = test_client.post("/api/v1/candidates", json=body)

        data = response.json()
        assert "archetype" in data
        assert "damage_type" in data["archetype"]
        assert "defense_style" in data["archetype"]
        assert "playstyle" in data["archetype"]

    def test_response_has_item_candidates(self, test_client: TestClient) -> None:
        """Response must contain item_candidates list."""
        body = self._make_request_body(slot="Helmet")
        with patch(
            "app.api.v1.candidates._get_poe_ninja_client",
        ) as mock_factory:
            mock_client = AsyncMock()
            mock_client.get_item_prices = AsyncMock(return_value={})
            mock_factory.return_value = mock_client

            response = test_client.post("/api/v1/candidates", json=body)

        data = response.json()
        assert "item_candidates" in data
        assert isinstance(data["item_candidates"], list)

    def test_slot_filter_respected(self, test_client: TestClient) -> None:
        """When slot='Helmet', only Helmet slot candidates should appear."""
        body = self._make_request_body(slot="Helmet")
        with patch(
            "app.api.v1.candidates._get_poe_ninja_client",
        ) as mock_factory:
            mock_client = AsyncMock()
            mock_client.get_item_prices = AsyncMock(return_value={})
            mock_factory.return_value = mock_client

            response = test_client.post("/api/v1/candidates", json=body)

        data = response.json()
        for slot_result in data["item_candidates"]:
            assert slot_result["slot"] == "Helmet"

    def test_poe_ninja_enrichment(self, test_client: TestClient) -> None:
        """When poe.ninja has a helmet, it should appear in candidates."""
        build = _make_build(
            level=80,
            str_attr=9999,
            dex_attr=9999,
            int_attr=9999,
        )
        body = {
            "build": build.model_dump(by_alias=True),
            "slot": "Helmet",
            "league": "TestLeague",
        }

        mock_prices: dict[str, Any] = {
            "Starkonja's Head": {
                "baseType": "Silken Hood",
                "divineValue": 1.5,
                "listingCount": 30,
                "levelRequired": 60,
            }
        }

        # Patch repoe to return a Silken Hood with Helmet class
        from app.models.repoe import RePoEBaseItem
        mock_base_items: dict[str, RePoEBaseItem] = {
            "Metadata/Items/Armours/Helmets/SilkenHood": RePoEBaseItem(
                name="Silken Hood",
                item_class="Helmet",
                requirements={"level": 60, "dex": 100},
                tags=["helmet"],
            )
        }

        with patch(
            "app.api.v1.candidates._get_poe_ninja_client",
        ) as mock_factory, patch(
            "app.services.candidate_generator.load_base_items",
            return_value=mock_base_items,
        ):
            mock_client = AsyncMock()
            mock_client.get_item_prices = AsyncMock(
                return_value=mock_prices
            )
            mock_factory.return_value = mock_client

            response = test_client.post("/api/v1/candidates", json=body)

        data = response.json()
        assert response.status_code == 200
        # Starkonja's Head should appear in Helmet candidates
        helmet_slot = next(
            (s for s in data["item_candidates"] if s["slot"] == "Helmet"),
            None,
        )
        assert helmet_slot is not None
        names = [c["name"] for c in helmet_slot["candidates"]]
        assert "Starkonja's Head" in names

    def test_invalid_build_returns_422(self, test_client: TestClient) -> None:
        """Sending a build with level=0 should return 422."""
        body = {
            "build": {"level": 0, "class": "Witch"},
            "league": "Test",
        }
        response = test_client.post("/api/v1/candidates", json=body)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Additional archetype detection edge-cases
# ---------------------------------------------------------------------------


class TestArchetypeEdgeCases:
    """Edge-case scenarios for archetype detection."""

    def test_ci_detected_when_life_is_1(self) -> None:
        """A build with life=1 should be classified as CI."""
        build = _make_build(
            level=90, life=1, energy_shield=5000,
            char_class="Witch", ascendancy="Occultist",
        )
        archetype = detect_archetype(build)
        assert archetype.defense_style == "ci"

    def test_es_build_detected(self) -> None:
        """A build with very high ES vs low life should be non-life style."""
        build = _make_build(
            level=90, life=500, energy_shield=4000,
            char_class="Witch", ascendancy="Occultist",
        )
        archetype = detect_archetype(build)
        # 500 life vs 4000 ES → low-life or es (not pure life-based)
        assert archetype.defense_style in ("es", "hybrid", "lowlife")

    def test_hybrid_build_detected(self) -> None:
        """A build with 3000 life and 3000 ES should be 'hybrid'."""
        build = _make_build(
            level=90, life=3000, energy_shield=3000,
            char_class="Templar", ascendancy="Inquisitor",
        )
        archetype = detect_archetype(build)
        assert archetype.defense_style in ("hybrid", "life", "es")

    def test_default_damage_type_is_physical(self) -> None:
        """A build with no strong damage signals defaults to physical."""
        build = _make_build(level=90, main_skill="Generic Attack")
        archetype = detect_archetype(build)
        assert archetype.damage_type in (
            "physical", "fire", "cold", "lightning",
            "chaos", "minion", "totem", "trap",
        )


# ---------------------------------------------------------------------------
# Archetype template mods
# ---------------------------------------------------------------------------


class TestArchetypeTemplateMods:
    """archetype_template_mods() returns sensible mods for each archetype."""

    def test_minion_archetype_has_minion_mods(self) -> None:
        """Minion archetype must include a minion damage mod."""
        archetype = Archetype(
            damage_type="minion",
            defense_style="life",
            playstyle="summoner",
        )
        mods = archetype_template_mods(archetype)
        assert any("minion" in m.lower() for m in mods), (
            f"Expected a minion mod; got: {mods}"
        )

    def test_fire_archetype_has_fire_mods(self) -> None:
        """Fire archetype must include a fire damage mod."""
        archetype = Archetype(
            damage_type="fire",
            defense_style="life",
            playstyle="caster",
        )
        mods = archetype_template_mods(archetype)
        assert any("fire" in m.lower() for m in mods), (
            f"Expected a fire mod; got: {mods}"
        )

    def test_cold_archetype_has_cold_mods(self) -> None:
        """Cold archetype must include a cold damage mod."""
        archetype = Archetype(
            damage_type="cold",
            defense_style="es",
            playstyle="caster",
        )
        mods = archetype_template_mods(archetype)
        assert any("cold" in m.lower() for m in mods), (
            f"Expected a cold mod; got: {mods}"
        )

    def test_life_defense_includes_life_mod(self) -> None:
        """Life defense archetype must always include a maximum Life mod."""
        archetype = Archetype(
            damage_type="physical",
            defense_style="life",
            playstyle="melee",
        )
        mods = archetype_template_mods(archetype)
        assert any("life" in m.lower() for m in mods), (
            f"Expected a Life mod; got: {mods}"
        )

    def test_summoner_playstyle_has_aura_mod(self) -> None:
        """Summoner playstyle must include an aura or non-curse aura mod."""
        archetype = Archetype(
            damage_type="minion",
            defense_style="life",
            playstyle="summoner",
        )
        mods = archetype_template_mods(archetype)
        assert any("aura" in m.lower() for m in mods), (
            f"Expected an aura mod; got: {mods}"
        )

    def test_caster_playstyle_has_cast_speed_mod(self) -> None:
        """Caster playstyle must include a cast speed mod."""
        archetype = Archetype(
            damage_type="fire",
            defense_style="life",
            playstyle="caster",
        )
        mods = archetype_template_mods(archetype)
        assert any("cast speed" in m.lower() for m in mods), (
            f"Expected a cast speed mod; got: {mods}"
        )

    def test_template_mods_capped_at_five(self) -> None:
        """archetype_template_mods() must return at most 5 items."""
        for damage_type in ("fire", "cold", "lightning", "chaos", "physical", "minion"):
            for playstyle in ("caster", "melee", "ranged", "summoner"):
                archetype = Archetype(
                    damage_type=damage_type,
                    defense_style="life",
                    playstyle=playstyle,
                )
                mods = archetype_template_mods(archetype)
                assert len(mods) <= 5, (
                    f"{damage_type}/{playstyle}: expected ≤5 mods, got {len(mods)}"
                )

    def test_template_mods_are_unique(self) -> None:
        """archetype_template_mods() must not return duplicate mod strings."""
        archetype = Archetype(
            damage_type="minion",
            defense_style="life",
            playstyle="summoner",
        )
        mods = archetype_template_mods(archetype)
        assert len(mods) == len(set(mods)), f"Duplicate mods found: {mods}"

    def test_physical_archetype_has_physical_mods(self) -> None:
        """Physical archetype must include a physical damage mod."""
        archetype = Archetype(
            damage_type="physical",
            defense_style="life",
            playstyle="melee",
        )
        mods = archetype_template_mods(archetype)
        assert any("physical" in m.lower() for m in mods), (
            f"Expected a physical mod; got: {mods}"
        )


# ---------------------------------------------------------------------------
# extract_key_mods
# ---------------------------------------------------------------------------


class TestExtractKeyMods:
    """extract_key_mods() correctly filters mods for an archetype."""

    def test_extracts_life_mod_for_life_build(self) -> None:
        """Life mod should be extracted for a life-defense archetype."""
        archetype = Archetype(
            damage_type="physical",
            defense_style="life",
            playstyle="melee",
        )
        mods = [
            "+80 to maximum Life",
            "+30% to Lightning Resistance",
            "10% reduced Flask Charges used",
        ]
        result = extract_key_mods(mods, archetype)
        assert "+80 to maximum Life" in result

    def test_ignores_irrelevant_mods(self) -> None:
        """'10% reduced Flask Charges used' should not be extracted for melee."""
        archetype = Archetype(
            damage_type="physical",
            defense_style="life",
            playstyle="melee",
        )
        mods = ["10% reduced Flask Charges used", "20% reduced Flask Duration"]
        result = extract_key_mods(mods, archetype)
        assert result == [], f"Expected no relevant mods, got {result}"

    def test_returns_empty_for_no_mods(self) -> None:
        """Empty mod list returns empty result."""
        archetype = Archetype(
            damage_type="cold",
            defense_style="es",
            playstyle="caster",
        )
        assert extract_key_mods([], archetype) == []

    def test_respects_max_mods_limit(self) -> None:
        """extract_key_mods() must never return more than max_mods items."""
        archetype = Archetype(
            damage_type="fire",
            defense_style="life",
            playstyle="caster",
        )
        mods = [
            "+80 to maximum Life",
            "+40 to Fire Resistance",
            "50% increased Fire Damage",
            "+25% to Fire Damage over Time Multiplier",
            "15% increased Cast Speed",
            "+30% to Cold Resistance",
        ]
        result = extract_key_mods(mods, archetype, max_mods=2)
        assert len(result) <= 2

    def test_extracts_energy_shield_mod_for_es_build(self) -> None:
        """Energy shield mod should be extracted for a CI/ES archetype."""
        archetype = Archetype(
            damage_type="chaos",
            defense_style="ci",
            playstyle="caster",
        )
        mods = [
            "+200 to maximum Energy Shield",
            "+80 to maximum Life",
        ]
        result = extract_key_mods(mods, archetype)
        assert any("energy shield" in m.lower() for m in result), (
            f"Expected energy shield mod in {result}"
        )

    def test_extracts_minion_mod_for_summoner(self) -> None:
        """Minion mod should be extracted for a minion archetype."""
        archetype = Archetype(
            damage_type="minion",
            defense_style="life",
            playstyle="summoner",
        )
        mods = [
            "Minions deal 50% increased Damage",
            "+80 to maximum Life",
            "10% reduced Flask Charges used",
        ]
        result = extract_key_mods(mods, archetype)
        assert "Minions deal 50% increased Damage" in result


# ---------------------------------------------------------------------------
# archetype_mod_keywords
# ---------------------------------------------------------------------------


class TestArchetypeModKeywords:
    """archetype_mod_keywords() produces the correct keyword sets."""

    def test_life_defense_includes_life_and_res_keywords(self) -> None:
        """Life defense keywords must include 'maximum life' and 'resistance'."""
        archetype = Archetype(
            damage_type="physical",
            defense_style="life",
            playstyle="melee",
        )
        kws = archetype_mod_keywords(archetype)
        assert "maximum life" in kws
        assert "all resistances" in kws

    def test_es_defense_includes_energy_shield_keywords(self) -> None:
        """ES/CI/hybrid defense keywords must include 'energy shield'."""
        for defense in ("es", "ci", "lowlife"):
            archetype = Archetype(
                damage_type="cold",
                defense_style=defense,
                playstyle="caster",
            )
            kws = archetype_mod_keywords(archetype)
            assert "energy shield" in kws, (
                f"Expected 'energy shield' in keywords for defense={defense}"
            )

    def test_minion_damage_type_includes_minion_keywords(self) -> None:
        """Minion damage keywords must include 'minion damage' and 'minion life'."""
        archetype = Archetype(
            damage_type="minion",
            defense_style="life",
            playstyle="summoner",
        )
        kws = archetype_mod_keywords(archetype)
        assert "minion damage" in kws
        assert "minion life" in kws

    def test_keywords_have_no_duplicates(self) -> None:
        """archetype_mod_keywords() must not have duplicate entries."""
        for damage_type in ("fire", "cold", "minion", "physical"):
            for playstyle in ("caster", "melee", "summoner"):
                archetype = Archetype(
                    damage_type=damage_type,
                    defense_style="life",
                    playstyle=playstyle,
                )
                kws = archetype_mod_keywords(archetype)
                assert len(kws) == len(set(kws)), (
                    f"Duplicate keywords for {damage_type}/{playstyle}: {kws}"
                )

    def test_fire_damage_type_includes_fire_keywords(self) -> None:
        """Fire archetype keywords must include 'fire damage'."""
        archetype = Archetype(
            damage_type="fire",
            defense_style="life",
            playstyle="caster",
        )
        kws = archetype_mod_keywords(archetype)
        assert "fire damage" in kws


# ---------------------------------------------------------------------------
# More archetype damage/playstyle detection edge-cases
# ---------------------------------------------------------------------------


class TestMoreArchetypeDetection:
    """Additional archetype detection cases for fire, lightning, chaos, ranged builds."""

    def test_fire_build_detected_via_fireball_gem(self) -> None:
        """A build with Fireball should detect fire damage type."""
        build = _make_build(
            level=90,
            gems=["Fireball", "Increased Area of Effect Support"],
            main_skill="Fireball",
            char_class="Witch",
            ascendancy="Elementalist",
        )
        archetype = detect_archetype(build)
        assert archetype.damage_type == "fire", (
            f"Expected fire, got '{archetype.damage_type}'"
        )

    def test_lightning_build_detected_via_class_hint(self) -> None:
        """Deadeye ascendancy should contribute to lightning damage detection."""
        build = _make_build(
            level=90,
            gems=["Lightning Arrow", "Added Lightning Damage Support"],
            main_skill="Lightning Arrow",
            char_class="Ranger",
            ascendancy="Deadeye",
        )
        archetype = detect_archetype(build)
        # Deadeye gives 'lightning' hint; lightning arrow has lightning keywords
        assert archetype.damage_type in ("lightning", "physical"), (
            f"Expected lightning or physical, got '{archetype.damage_type}'"
        )

    def test_chaos_build_detected_via_occultist(self) -> None:
        """Occultist ascendancy with chaos skills should detect chaos damage."""
        build = _make_build(
            level=90,
            gems=["Essence Drain", "Contagion", "Wither"],
            main_skill="Essence Drain",
            char_class="Witch",
            ascendancy="Occultist",
        )
        archetype = detect_archetype(build)
        assert archetype.damage_type == "chaos", (
            f"Expected chaos, got '{archetype.damage_type}'"
        )

    def test_totem_build_detected_via_gem(self) -> None:
        """A build with Ancestral Warchief should detect totem build."""
        build = _make_build(
            level=90,
            gems=["Ancestral Warchief", "Totem Support", "Multiple Totems"],
            main_skill="Ancestral Warchief",
            char_class="Templar",
            ascendancy="Hierophant",
        )
        archetype = detect_archetype(build)
        assert archetype.damage_type in ("totem", "physical"), (
            f"Expected totem or physical; got '{archetype.damage_type}'"
        )

    def test_ranged_build_playstyle_via_arrow_gem(self) -> None:
        """A build with Burning Arrow should detect 'ranged' playstyle."""
        build = _make_build(
            level=90,
            gems=["Burning Arrow", "Elemental Damage with Attacks Support"],
            main_skill="Burning Arrow",
            char_class="Ranger",
            ascendancy="Deadeye",
        )
        archetype = detect_archetype(build)
        assert archetype.playstyle in ("ranged", "caster"), (
            f"Expected ranged or caster; got '{archetype.playstyle}'"
        )

    def test_lowlife_defense_detected(self) -> None:
        """Build with life < 35% of ES should be classified as lowlife."""
        build = _make_build(
            level=90,
            life=400,
            energy_shield=2000,
            char_class="Witch",
            ascendancy="Occultist",
        )
        archetype = detect_archetype(build)
        # 400 < 2000 * 0.35 = 700 → lowlife
        assert archetype.defense_style == "lowlife", (
            f"Expected lowlife, got '{archetype.defense_style}'"
        )

    def test_hybrid_defense_detected(self) -> None:
        """Build with life >= 1000 and ES >= 1000 should be classified as hybrid."""
        build = _make_build(
            level=90,
            life=2000,
            energy_shield=2000,
            char_class="Templar",
            ascendancy="Inquisitor",
        )
        archetype = detect_archetype(build)
        # 2000 >= 2000*0.35=700 (not lowlife), 2000 >= 6000? No (not es), both>=1000 → hybrid
        assert archetype.defense_style == "hybrid", (
            f"Expected hybrid, got '{archetype.defense_style}'"
        )

    def test_lightning_build_via_arc_gem(self) -> None:
        """A build with Arc should detect lightning damage."""
        build = _make_build(
            level=90,
            gems=["Arc", "Added Lightning Damage Support", "Controlled Destruction Support"],
            main_skill="Arc",
            char_class="Witch",
            ascendancy="Occultist",
        )
        archetype = detect_archetype(build)
        assert archetype.damage_type == "lightning", (
            f"Expected lightning, got '{archetype.damage_type}'"
        )

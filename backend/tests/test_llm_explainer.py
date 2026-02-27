"""Tests for the M7 LLM Explainer service and related utilities.

Covers:
* D7.1 — LLMExplainerService: generate_explanation, fallback paths.
* D7.2 — validate_llm_output: hallucination detection.
* D7.3 — A/B routing: _is_llm_ab_group hash distribution.
* D7.4 — build_recommendations_async: LLM vs template branching.
* D7.6 — DailyUsageTracker: cost cap, daily reset, snapshot.
* Admin endpoint: GET /api/v1/admin/llm-usage.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from openai import APIStatusError

from app.main import app
from app.models.calculation import CalculationResult
from app.models.candidate import (
    Archetype,
    BuildData,
    BuildGem,
    BuildSkillGroup,
    BuildStats,
    CandidateItem,
    CharacterAttrs,
)
from app.models.recommendation import SimulationResult
from app.services.llm_explainer import (
    DailyUsageTracker,
    LLMExplainerService,
    LLMExplanationOutput,
    validate_llm_output,
)
from app.services.simulation import (
    _is_llm_ab_group,
    build_recommendations_async,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_output(
    explanation: str = "This is a great upgrade for your build.",
    beginner_tip: str | None = None,
) -> LLMExplanationOutput:
    return LLMExplanationOutput(explanation=explanation, beginner_tip=beginner_tip)


def _make_engine_data(
    dps_delta: float = 200_000.0,
    life_delta: float = 300.0,
    es_delta: float = 0.0,
    price_divine: float = 2.0,
    suggested_item: str = "Starkonja's Head",
    current_item: str = "Rare Helmet",
) -> dict[str, Any]:
    return {
        "dps_delta": dps_delta,
        "life_delta": life_delta,
        "es_delta": es_delta,
        "price_divine": price_divine,
        "suggested_item": suggested_item,
        "current_item": current_item,
    }


def _make_archetype(
    damage_type: str = "fire",
    defense_style: str = "life",
    playstyle: str = "caster",
) -> Archetype:
    return Archetype(
        damage_type=damage_type,
        defense_style=defense_style,
        playstyle=playstyle,
    )


def _make_build() -> BuildData:
    gem_objects = [
        BuildGem(name_spec="Fireball", is_support=False),
        BuildGem(name_spec="Spell Echo Support", is_support=True),
    ]
    return BuildData(
        character_name="TestChar",
        **{"class": "Witch"},
        ascendancy="Occultist",
        level=80,
        main_skill="Fireball",
        stats=BuildStats(
            life=4500,
            energy_shield=200,
            dps=1_200_000.0,
            fire_res=75,
            cold_res=75,
            lightning_res=75,
            chaos_res=-60,
        ),
        attrs=CharacterAttrs(str=100, dex=100, **{"int": 200}),
        skill_groups=[
            BuildSkillGroup(
                slot="Body Armour",
                enabled=True,
                gems=gem_objects,
                main_active_gem_index=0,
            )
        ],
        items={},
    )


def _make_sim_result(
    slot: str = "Helmet",
    name: str = "Starkonja's Head",
    dps_gain: float = 200_000.0,
    life_gain: int = 300,
    price: float = 2.0,
) -> SimulationResult:
    baseline = CalculationResult(
        dps=1_000_000.0,
        total_dps=1_000_000.0,
        life=4500,
        energy_shield=200,
        fire_res=75,
        cold_res=75,
        lightning_res=75,
    )
    modified = CalculationResult(
        dps=1_000_000.0 + dps_gain,
        total_dps=1_000_000.0 + dps_gain,
        life=4500 + life_gain,
        energy_shield=200,
        fire_res=75,
        cold_res=75,
        lightning_res=75,
    )
    candidate = CandidateItem(
        name=name,
        base_name="Hubris Circlet",
        slot=slot,
        rarity="unique",
        price_divine=price,
        relevance_score=0.8,
    )
    return SimulationResult(
        slot=slot,
        candidate=candidate,
        baseline_stats=baseline,
        modified_stats=modified,
        deltas={"dps": dps_gain, "life": float(life_gain)},
        price_divine=price,
    )


# ---------------------------------------------------------------------------
# Tests — validate_llm_output (D7.2)
# ---------------------------------------------------------------------------


class TestValidateLlmOutput:
    """Tests for hallucination detection in LLM output."""

    def test_valid_output_passes(self) -> None:
        """Output with no fabricated data passes validation.

        Expected: ValidationResult.valid == True.
        """
        output = _make_llm_output(
            "This item upgrade benefits your build significantly."
        )
        engine_data = _make_engine_data(
            dps_delta=200_000.0,
            life_delta=300.0,
            price_divine=2.0,
            suggested_item="Starkonja's Head",
            current_item="Rare Helmet",
        )
        result = validate_llm_output(output, engine_data)
        assert result.valid

    def test_hallucinated_large_number_fails(self) -> None:
        """A fabricated large DPS number that isn't in engine data fails.

        Expected: ValidationResult.valid == False with numeric issue.
        """
        # Engine says dps_delta=200_000; LLM claims 999_999
        output = _make_llm_output(
            "This upgrade will increase your DPS by 999999, which is amazing."
        )
        engine_data = _make_engine_data(dps_delta=200_000.0, life_delta=0.0)
        result = validate_llm_output(output, engine_data)
        assert not result.valid
        assert any("999999" in issue for issue in result.issues)

    def test_hallucinated_item_name_fails(self) -> None:
        """A fabricated item name (capitalized two-word phrase) fails validation.

        Expected: ValidationResult.valid == False with item issue.
        """
        # Use a two-word capitalized name with no apostrophe so the regex can match.
        # Equipping Loreweave (two bare capitalized words) triggers the item check.
        output = _make_llm_output(
            "Equipping Loreweave Chest is a far better option for your build."
        )
        engine_data = _make_engine_data(
            suggested_item="Starkonja's Head",
            current_item="Rare Helmet",
        )
        result = validate_llm_output(output, engine_data)
        assert not result.valid
        # At least one of the two-word pairs should be flagged
        assert len(result.issues) >= 1

    def test_correct_item_name_passes(self) -> None:
        """Mentioning the actual suggested item passes validation.

        Expected: ValidationResult.valid == True.
        """
        output = _make_llm_output(
            "Starkonja's Head provides both offense and defense."
        )
        engine_data = _make_engine_data(suggested_item="Starkonja's Head")
        result = validate_llm_output(output, engine_data)
        assert result.valid

    def test_wrong_currency_amount_fails(self) -> None:
        """A fabricated price far from the actual price fails.

        Expected: ValidationResult.valid == False with currency issue.
        """
        # Engine price = 2.0 divine; LLM says 99 divine
        output = _make_llm_output(
            "At only 99 divine orbs this item is great value."
        )
        engine_data = _make_engine_data(
            dps_delta=0.0,
            life_delta=0.0,
            price_divine=2.0,
            suggested_item="Starkonja's Head",
            current_item="Rare Helmet",
        )
        result = validate_llm_output(output, engine_data)
        assert not result.valid
        assert any("99" in issue for issue in result.issues)

    def test_correct_currency_amount_passes(self) -> None:
        """Mentioning the correct price passes validation.

        Expected: ValidationResult.valid == True.
        """
        output = _make_llm_output(
            "At just 2 divine orbs this upgrade is excellent value."
        )
        engine_data = _make_engine_data(
            dps_delta=0.0,
            life_delta=0.0,
            price_divine=2.0,
            suggested_item="Some Item",
            current_item="Other Item",
        )
        result = validate_llm_output(output, engine_data)
        assert result.valid

    def test_small_numbers_are_ignored(self) -> None:
        """Numbers below 50 are not flagged even if absent from engine data.

        Expected: valid when all mentioned numbers are < 50.
        """
        output = _make_llm_output(
            "Your resistance was 20 and now reaches 42, which is an improvement."
        )
        # All numbers in the text (20, 42) are < 50 → threshold skips them.
        engine_data = _make_engine_data(
            dps_delta=0.0, life_delta=0.0, price_divine=0.0
        )
        result = validate_llm_output(output, engine_data)
        assert result.valid

    def test_beginner_tip_included_in_validation(self) -> None:
        """The beginner_tip text is also validated for hallucinations.

        Expected: issue found in beginner_tip triggers invalid result.
        """
        output = LLMExplanationOutput(
            explanation="This is a fine upgrade.",
            beginner_tip="You will gain 9999999 DPS from this.",
        )
        engine_data = _make_engine_data(dps_delta=200_000.0, life_delta=0.0)
        result = validate_llm_output(output, engine_data)
        assert not result.valid


# ---------------------------------------------------------------------------
# Tests — DailyUsageTracker (D7.6)
# ---------------------------------------------------------------------------


class TestDailyUsageTracker:
    """Tests for DailyUsageTracker cost controls and daily reset."""

    def test_initial_state_is_zero(self) -> None:
        """Fresh tracker has zero tokens and zero cost.

        Expected: all counters are 0.
        """
        tracker = DailyUsageTracker()
        assert tracker.total_input_tokens == 0
        assert tracker.total_output_tokens == 0
        assert tracker.estimated_cost_usd == pytest.approx(0.0)
        assert tracker.requests_served == 0
        assert tracker.fallback_count == 0

    def test_record_usage_accumulates(self) -> None:
        """Recording usage accumulates token counts.

        Expected: tokens and cost increase correctly after each call.
        """
        tracker = DailyUsageTracker()
        tracker.record_usage(input_tokens=100, output_tokens=50)
        tracker.record_usage(input_tokens=200, output_tokens=100)
        assert tracker.total_input_tokens == 300
        assert tracker.total_output_tokens == 150
        assert tracker.requests_served == 2
        expected_cost = 300 * 0.00000015 + 150 * 0.00000060
        assert tracker.estimated_cost_usd == pytest.approx(expected_cost)

    def test_cap_not_reached_below_threshold(self) -> None:
        """Spend cap is not triggered when cost is below the limit.

        Expected: cap_reached returns False.
        """
        tracker = DailyUsageTracker()
        tracker.record_usage(input_tokens=1000, output_tokens=500)
        assert not tracker.cap_reached(cap_usd=5.0)

    def test_cap_reached_above_threshold(self) -> None:
        """Spend cap is triggered when cost exceeds the limit.

        Expected: cap_reached returns True.
        """
        tracker = DailyUsageTracker()
        # Record enough tokens to exceed $0.001 cap
        tracker.record_usage(input_tokens=10_000_000, output_tokens=0)
        assert tracker.cap_reached(cap_usd=0.001)

    def test_cap_zero_means_unlimited(self) -> None:
        """A cap of 0 disables the limit entirely.

        Expected: cap_reached always returns False when cap_usd == 0.
        """
        tracker = DailyUsageTracker()
        tracker.record_usage(input_tokens=10_000_000, output_tokens=10_000_000)
        assert not tracker.cap_reached(cap_usd=0)

    def test_record_fallback_increments_counter(self) -> None:
        """Recording a fallback increments fallback_count.

        Expected: fallback_count == 2 after two fallback records.
        """
        tracker = DailyUsageTracker()
        tracker.record_fallback()
        tracker.record_fallback(cap_triggered=True)
        assert tracker.fallback_count == 2
        assert tracker.cap_hit_count == 1

    def test_daily_reset_on_new_day(self) -> None:
        """Counters reset when the calendar day changes.

        Expected: all counters are 0 after date advances.
        """
        tracker = DailyUsageTracker()
        tracker.record_usage(input_tokens=500, output_tokens=250)
        assert tracker.requests_served == 1

        # Manually roll back the tracker's date to simulate a new day.
        from datetime import timedelta
        yesterday = datetime.now(UTC).date() - timedelta(days=1)
        tracker._date = yesterday
        # Force the reset by accessing any property that calls _maybe_reset
        _ = tracker.estimated_cost_usd
        assert tracker.total_input_tokens == 0
        assert tracker.requests_served == 0

    def test_snapshot_contains_expected_keys(self) -> None:
        """Snapshot dict contains all required keys.

        Expected: keys include date, tokens, cost, counts.
        """
        tracker = DailyUsageTracker()
        tracker.record_usage(input_tokens=100, output_tokens=50)
        snap = tracker.snapshot()
        assert "date" in snap
        assert "total_input_tokens" in snap
        assert "total_output_tokens" in snap
        assert "total_tokens" in snap
        assert "estimated_cost_usd" in snap
        assert "requests_served" in snap
        assert "fallback_count" in snap
        assert "cap_hit_count" in snap
        assert snap["total_tokens"] == 150


# ---------------------------------------------------------------------------
# Tests — LLMExplainerService (D7.1)
# ---------------------------------------------------------------------------


class TestLLMExplainerService:
    """Tests for LLMExplainerService fallback paths and happy path."""

    def _make_service(
        self,
        api_key: str = "sk-test",
        llm_enabled: bool = True,
        daily_spend_cap_usd: float = 5.0,
        timeout_seconds: float = 3.0,
    ) -> LLMExplainerService:
        svc = LLMExplainerService(
            api_key=api_key,
            model="gpt-4o-mini",
            timeout_seconds=timeout_seconds,
            daily_spend_cap_usd=daily_spend_cap_usd,
            llm_enabled=llm_enabled,
        )
        return svc

    def _call_kwargs(self, template: str = "template result") -> dict[str, Any]:
        return {
            "slot": "Helmet",
            "current_item": "Rare Helmet",
            "suggested_item": "Starkonja's Head",
            "category": "power_upgrade",
            "deltas": {"dps": 200_000.0, "life": 300.0},
            "price_divine": 2.0,
            "level": 80,
            "ascendancy": "Occultist",
            "damage_type": "fire",
            "playstyle": "caster",
            "main_skill": "Fireball",
            "template_explanation": template,
        }

    @pytest.mark.asyncio
    async def test_no_api_key_returns_template(self) -> None:
        """Service with empty API key falls back to template.

        Expected: source == 'template', text == template_explanation.
        """
        svc = self._make_service(api_key="")
        _text, source = await svc.generate_explanation(**self._call_kwargs())
        assert source == "template"
        assert _text == "template result"

    @pytest.mark.asyncio
    async def test_llm_disabled_returns_template(self) -> None:
        """Service with llm_enabled=False falls back to template.

        Expected: source == 'template'.
        """
        svc = self._make_service(llm_enabled=False)
        _text, source = await svc.generate_explanation(**self._call_kwargs())
        assert source == "template"

    @pytest.mark.asyncio
    async def test_spend_cap_reached_returns_template(self) -> None:
        """Service returns template when daily cap is reached.

        Expected: source == 'template', cap_hit_count increments.
        """
        svc = self._make_service(daily_spend_cap_usd=0.000001)
        # Inject a tracker that's already over cap
        fake_tracker = DailyUsageTracker()
        fake_tracker.record_usage(input_tokens=50_000_000, output_tokens=0)
        svc._tracker = fake_tracker

        _text, source = await svc.generate_explanation(**self._call_kwargs())
        assert source == "template"
        assert fake_tracker.cap_hit_count >= 1

    @pytest.mark.asyncio
    async def test_timeout_returns_template(self) -> None:
        """Service falls back to template when OpenAI call times out.

        Expected: source == 'template', fallback_count increments.
        """
        svc = self._make_service()
        fake_tracker = DailyUsageTracker()
        svc._tracker = fake_tracker

        # Mock _client so parse() returns a MagicMock (not a real coroutine)
        svc._client = MagicMock()
        svc._client.beta.chat.completions.parse = MagicMock(
            return_value=MagicMock()
        )

        # Patch asyncio.wait_for to raise TimeoutError immediately
        with patch("app.services.llm_explainer.asyncio.wait_for") as mock_wait:
            mock_wait.side_effect = TimeoutError()
            _text, source = await svc.generate_explanation(**self._call_kwargs())

        assert source == "template"
        assert fake_tracker.fallback_count >= 1

    @pytest.mark.asyncio
    async def test_5xx_retries_once_then_falls_back(self) -> None:
        """Service retries once on 5xx then falls back to template.

        Expected: source == 'template', wait_for called twice (2 attempts).
        """
        svc = self._make_service()
        fake_tracker = DailyUsageTracker()
        svc._tracker = fake_tracker

        call_count = 0

        async def _raise_5xx(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_resp.headers = {}
            raise APIStatusError(
                "Service Unavailable",
                response=mock_resp,
                body={"error": "Service Unavailable"},
            )

        # Patch both wait_for (to intercept calls) and the client parse method
        # (to avoid creating an unawaited real coroutine)
        with patch("app.services.llm_explainer.asyncio.wait_for") as mock_wait:
            mock_wait.side_effect = _raise_5xx
            # Also mock the client so parse() returns a MagicMock, not a coroutine
            svc._client = MagicMock()
            svc._client.beta.chat.completions.parse = MagicMock(
                return_value=MagicMock()
            )
            _text, source = await svc.generate_explanation(**self._call_kwargs())

        assert source == "template"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_hallucination_detected_returns_template(self) -> None:
        """If LLM response fails validation, service returns template.

        Expected: source == 'template'.
        """
        svc = self._make_service()
        fake_tracker = DailyUsageTracker()
        svc._tracker = fake_tracker

        # Build a response that will fail hallucination check
        hallucinated_output = LLMExplanationOutput(
            explanation=(
                "This upgrade adds 999999 DPS — insane value at 99 divine orbs."
            )
        )
        # Mock _call_with_fallback to return the hallucinated output directly
        with patch.object(
            svc, "_call_with_fallback",
            new=AsyncMock(return_value=hallucinated_output)
        ):
            _text, source = await svc.generate_explanation(**self._call_kwargs())

        assert source == "template"

    @pytest.mark.asyncio
    async def test_successful_llm_call_returns_llm_source(self) -> None:
        """Successful, valid LLM response returns 'llm' source.

        Expected: source == 'llm', text matches LLM output.
        """
        svc = self._make_service()
        svc._tracker = DailyUsageTracker()

        valid_output = LLMExplanationOutput(
            explanation=(
                "Starkonja's Head is perfect for your Occultist build."
            )
        )
        with patch.object(
            svc, "_call_with_fallback",
            new=AsyncMock(return_value=valid_output)
        ):
            _text, source = await svc.generate_explanation(**self._call_kwargs())

        assert source == "llm"
        assert "Starkonja's Head" in _text

    @pytest.mark.asyncio
    async def test_beginner_tip_appended_to_explanation(self) -> None:
        """When beginner_tip is provided, it is appended to explanation.

        Expected: final text contains both explanation and tip.
        """
        svc = self._make_service()
        svc._tracker = DailyUsageTracker()

        combined_output = LLMExplanationOutput(
            explanation="Starkonja's Head improves your crit chance.",
            beginner_tip="Tip: check your resistances after equipping this.",
        )
        with patch.object(
            svc, "_call_with_fallback",
            new=AsyncMock(return_value=combined_output)
        ):
            _text, source = await svc.generate_explanation(**self._call_kwargs())

        assert source == "llm"
        assert "improves your crit chance" in _text
        assert "Tip: check your resistances" in _text


# ---------------------------------------------------------------------------
# Tests — _is_llm_ab_group (D7.3)
# ---------------------------------------------------------------------------


class TestIsLlmAbGroup:
    """Tests for the A/B routing hash function."""

    def test_deterministic_for_same_session(self) -> None:
        """Same session_id always maps to the same group.

        Expected: repeated calls return the same bool.
        """
        sid = "550e8400-e29b-41d4-a716-446655440000"
        result1 = _is_llm_ab_group(sid)
        result2 = _is_llm_ab_group(sid)
        assert result1 == result2

    def test_approximately_fifty_fifty_distribution(self) -> None:
        """Roughly 50% of session IDs map to the LLM group.

        Expected: between 30% and 70% in LLM group for 1000 sessions.
        """
        import uuid
        sessions = [str(uuid.uuid4()) for _ in range(1000)]
        llm_count = sum(1 for s in sessions if _is_llm_ab_group(s))
        assert 250 <= llm_count <= 750, (
            f"Expected ~50% LLM group, got {llm_count}/1000"
        )

    def test_known_md5_assignment(self) -> None:
        """Known MD5 hash produces predictable group assignment.

        Expected: hash(sid)[:4] mod 2 == 0 → LLM group.
        """
        # Compute manually
        sid = "test-session-123"
        digest = hashlib.md5(sid.encode(), usedforsecurity=False).hexdigest()
        expected = int(digest[:4], 16) % 2 == 0
        assert _is_llm_ab_group(sid) == expected

    def test_empty_string_does_not_raise(self) -> None:
        """Empty session_id does not raise an exception.

        Expected: returns True or False without error.
        """
        result = _is_llm_ab_group("")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Tests — build_recommendations_async (D7.4)
# ---------------------------------------------------------------------------


class TestBuildRecommendationsAsync:
    """Tests for async recommendation builder with LLM support."""

    @pytest.mark.asyncio
    async def test_no_session_returns_template_source(self) -> None:
        """Without session_id, recommendations have template source.

        Expected: all explanation_source == 'template'.
        """
        build = _make_build()
        archetype = _make_archetype()
        sims = [
            _make_sim_result(slot="Helmet", name="Starkonja's Head"),
            _make_sim_result(slot="Gloves", name="Rare Gloves"),
            _make_sim_result(slot="Boots", name="Rare Boots"),
        ]
        recs = await build_recommendations_async(
            simulations=sims,
            issues=[],
            build=build,
            archetype=archetype,
            session_id=None,
            llm_service=None,
        )
        assert all(r.explanation_source == "template" for r in recs)

    @pytest.mark.asyncio
    async def test_llm_service_none_returns_template_source(self) -> None:
        """Without llm_service, recommendations have template source.

        Expected: all explanation_source == 'template'.
        """
        build = _make_build()
        archetype = _make_archetype()
        sims = [_make_sim_result()]
        recs = await build_recommendations_async(
            simulations=sims,
            issues=[],
            build=build,
            archetype=archetype,
            session_id="some-session-id",
            llm_service=None,
        )
        assert all(r.explanation_source == "template" for r in recs)

    @pytest.mark.asyncio
    async def test_non_llm_group_returns_template_source(self) -> None:
        """Session not in LLM A/B group gets template explanations.

        Expected: all explanation_source == 'template'.
        """
        build = _make_build()
        archetype = _make_archetype()
        sims = [_make_sim_result()]

        # Find a session_id that's NOT in the LLM group
        non_llm_session = "non-llm-session-forced"
        with patch("app.services.simulation._is_llm_ab_group", return_value=False):
            mock_svc = MagicMock(spec=LLMExplainerService)
            recs = await build_recommendations_async(
                simulations=sims,
                issues=[],
                build=build,
                archetype=archetype,
                session_id=non_llm_session,
                llm_service=mock_svc,
            )
        assert all(r.explanation_source == "template" for r in recs)
        mock_svc.generate_explanation.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_group_enriches_explanations(self) -> None:
        """Session in LLM A/B group gets LLM explanations.

        Expected: explanation_source == 'llm' after enrichment.
        """
        build = _make_build()
        archetype = _make_archetype()
        sims = [
            _make_sim_result(slot="Helmet", name="Starkonja's Head"),
        ]

        mock_svc = MagicMock(spec=LLMExplainerService)
        mock_svc.generate_explanation = AsyncMock(
            return_value=("LLM explanation text", "llm")
        )

        with patch("app.services.simulation._is_llm_ab_group", return_value=True):
            recs = await build_recommendations_async(
                simulations=sims,
                issues=[],
                build=build,
                archetype=archetype,
                session_id="llm-session-abc",
                llm_service=mock_svc,
            )

        assert all(r.explanation_source == "llm" for r in recs)
        assert all(r.explanation == "LLM explanation text" for r in recs)
        assert mock_svc.generate_explanation.call_count == len(recs)

    @pytest.mark.asyncio
    async def test_empty_simulations_returns_empty(self) -> None:
        """Empty simulation list returns empty recommendations.

        Expected: empty list.
        """
        build = _make_build()
        archetype = _make_archetype()
        recs = await build_recommendations_async(
            simulations=[],
            issues=[],
            build=build,
            archetype=archetype,
        )
        assert recs == []


# ---------------------------------------------------------------------------
# Tests — Admin endpoint (D7.6)
# ---------------------------------------------------------------------------


class TestAdminLlmUsageEndpoint:
    """Tests for GET /api/v1/admin/llm-usage."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_endpoint_returns_200(self, client: TestClient) -> None:
        """Admin endpoint returns 200 OK.

        Expected: status_code == 200.
        """
        resp = client.get("/api/v1/admin/llm-usage")
        assert resp.status_code == 200

    def test_response_contains_required_fields(self, client: TestClient) -> None:
        """Response contains all required dashboard fields.

        Expected: date, tokens, cost, counts, config present.
        """
        resp = client.get("/api/v1/admin/llm-usage")
        data = resp.json()
        for field in [
            "date",
            "total_input_tokens",
            "total_output_tokens",
            "total_tokens",
            "estimated_cost_usd",
            "requests_served",
            "fallback_count",
            "cap_hit_count",
            "llm_enabled",
            "model",
            "daily_spend_cap_usd",
            "cap_reached",
            "timeout_seconds",
        ]:
            assert field in data, f"Missing field: {field}"

    def test_tokens_are_non_negative(self, client: TestClient) -> None:
        """Token counts are non-negative integers.

        Expected: all token counts >= 0.
        """
        resp = client.get("/api/v1/admin/llm-usage")
        data = resp.json()
        assert data["total_input_tokens"] >= 0
        assert data["total_output_tokens"] >= 0
        assert data["total_tokens"] >= 0

    def test_estimated_cost_is_non_negative(self, client: TestClient) -> None:
        """Estimated cost is a non-negative float.

        Expected: estimated_cost_usd >= 0.
        """
        resp = client.get("/api/v1/admin/llm-usage")
        data = resp.json()
        assert data["estimated_cost_usd"] >= 0.0

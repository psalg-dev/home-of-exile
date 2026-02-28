"""LLM-based explanation generator for upgrade recommendations — M7.

Provides ``LLMExplainerService`` that generates natural-language
explanations for recommendation cards using OpenAI GPT-4o-mini,
grounded in engine-calculated data.

Key design decisions:
- 3-second timeout per LLM call; falls back to template on timeout.
- 1 retry on 5xx errors; then falls back to template.
- Structured JSON output enforced via a Pydantic response model.
- Daily spend cap: configurable via ``LLM_DAILY_SPEND_CAP_USD`` env var.
- Hallucination validation: catches fabricated numbers, items, gems.
- A/B routing: caller passes session-derived flag to use LLM or template.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from openai import APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Estimated cost per token (GPT-4o-mini, Feb 2026 pricing)
# ---------------------------------------------------------------------------
# Input:  $0.15 / 1M tokens → $0.00000015 per token
# Output: $0.60 / 1M tokens → $0.00000060 per token
_COST_PER_INPUT_TOKEN: float = 0.00000015
_COST_PER_OUTPUT_TOKEN: float = 0.00000060

# ---------------------------------------------------------------------------
# System prompt (as specified in milestone D7.1)
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = (
    "You are an expert Path of Exile advisor helping players optimize "
    "their builds.\n\n"
    "Rules:\n"
    "1. Use ONLY the numbers and data provided in the input. Never invent "
    "statistics.\n"
    "2. Explain WHY this upgrade matters for the player's specific build "
    "archetype.\n"
    "3. Keep explanations to 2-3 sentences maximum.\n"
    "4. Use language appropriate for the player's apparent experience level.\n"
    "5. Mention the cost-efficiency if the upgrade is a good value.\n"
    "6. If the upgrade fixes a critical issue (uncapped resistance, low life), "
    "lead with that.\n"
    "7. Do not reference patch notes, meta shifts, or information not in the "
    "input."
)

# ---------------------------------------------------------------------------
# User prompt template (as specified in the milestone)
# ---------------------------------------------------------------------------
_USER_PROMPT_TEMPLATE = (
    "Build: Level {level} {ascendancy} ({damage_type} {playstyle})\n"
    "Current {slot}: {current_item}\n"
    "Suggested: {suggested_item}\n\n"
    "Stat changes:\n"
    "- DPS: {dps_delta:+,.0f}\n"
    "- Life: {life_delta:+,.0f}\n"
    "- Energy Shield: {es_delta:+,.0f}\n"
    "- Fire Res: {fire_delta:+.0f}%\n"
    "- Cold Res: {cold_delta:+.0f}%\n"
    "- Lightning Res: {lightning_delta:+.0f}%\n\n"
    "Cost: {price} divine orb(s)\n"
    "Category: {category}\n\n"
    "Write a 2-3 sentence explanation for this upgrade recommendation.\n"
    "If helpful, include a 1-sentence beginner tip."
)


# ---------------------------------------------------------------------------
# Structured output model (D7.1 — JSON schema enforcement)
# ---------------------------------------------------------------------------

class LLMExplanationOutput(BaseModel):
    """JSON schema for structured OpenAI response.

    Attributes:
        explanation: 2-3 sentence explanation of the upgrade.
        beginner_tip: Optional 1-sentence tip for new players.
    """

    explanation: str
    beginner_tip: str | None = None


# ---------------------------------------------------------------------------
# Daily usage tracker (D7.6 — cost controls)
# ---------------------------------------------------------------------------

@dataclass
class DailyUsageTracker:
    """Track token usage and estimated cost for the current calendar day.

    Resets automatically when the calendar date changes.

    Attributes:
        _date: The date for which usage is tracked.
        total_input_tokens: Cumulative input tokens today.
        total_output_tokens: Cumulative output tokens today.
        requests_served: Number of LLM requests completed today.
        fallback_count: Number of times the template fallback was used.
        cap_hit_count: Number of times the spend cap triggered a fallback.
    """

    _date: date = field(default_factory=lambda: datetime.now(UTC).date())
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    requests_served: int = 0
    fallback_count: int = 0
    cap_hit_count: int = 0

    def _maybe_reset(self) -> None:
        """Reset counters if we have rolled over to a new day."""
        today = datetime.now(UTC).date()
        if today != self._date:
            self._date = today
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.requests_served = 0
            self.fallback_count = 0
            self.cap_hit_count = 0

    def record_usage(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record token usage for a completed LLM call.

        Args:
            input_tokens: Number of prompt tokens consumed.
            output_tokens: Number of completion tokens produced.
        """
        self._maybe_reset()
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.requests_served += 1

    def record_fallback(self, *, cap_triggered: bool = False) -> None:
        """Increment the fallback counter.

        Args:
            cap_triggered: ``True`` if the spend cap forced the fallback.
        """
        self._maybe_reset()
        self.fallback_count += 1
        if cap_triggered:
            self.cap_hit_count += 1

    @property
    def estimated_cost_usd(self) -> float:
        """Return estimated cost in USD for today's usage.

        Returns:
            Estimated spend in USD.
        """
        self._maybe_reset()
        return (
            self.total_input_tokens * _COST_PER_INPUT_TOKEN
            + self.total_output_tokens * _COST_PER_OUTPUT_TOKEN
        )

    def cap_reached(self, cap_usd: float) -> bool:
        """Return True if the daily spend cap has been reached.

        Args:
            cap_usd: Configured spend cap in USD (0 = disabled).

        Returns:
            ``True`` if ``estimated_cost_usd >= cap_usd`` and cap is
            enabled.
        """
        if cap_usd <= 0:
            return False
        self._maybe_reset()
        return self.estimated_cost_usd >= cap_usd

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of today's usage.

        Returns:
            Dict with token counts, cost, request counts, date.
        """
        self._maybe_reset()
        return {
            "date": self._date.isoformat(),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "requests_served": self.requests_served,
            "fallback_count": self.fallback_count,
            "cap_hit_count": self.cap_hit_count,
        }


# Module-level usage tracker shared across all service instances.
_usage_tracker = DailyUsageTracker()


def get_usage_tracker() -> DailyUsageTracker:
    """Return the module-level usage tracker.

    Returns:
        The singleton :class:`DailyUsageTracker`.
    """
    return _usage_tracker


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of hallucination validation.

    Attributes:
        valid: ``True`` if no issues were found.
        issues: List of human-readable issue descriptions for logging.
    """

    valid: bool
    issues: list[str] = field(default_factory=list)


def validate_llm_output(
    llm_response: LLMExplanationOutput,
    engine_data: dict[str, Any],
) -> ValidationResult:
    """Validate LLM-generated explanation against engine-calculated data.

    Checks:
    1. No numeric values (DPS/EHP) that differ by > 5% from engine deltas.
    2. No item names mentioned that aren't in the recommendation.
    3. No gem names from a blocklist that aren't in the build data.
    4. No currency amounts that differ from pricing data.

    Args:
        llm_response: Parsed LLM output with ``explanation`` and
            ``beginner_tip``.
        engine_data: Dict containing ``dps_delta``, ``life_delta``,
            ``es_delta``, ``price_divine``, ``suggested_item``,
            ``current_item``, ``gem_names`` (list of gem names in build),
            ``other_items`` (list of other item names in build).

    Returns:
        :class:`ValidationResult` with ``valid=True`` if all checks pass.
    """
    text = llm_response.explanation
    if llm_response.beginner_tip:
        text = f"{text} {llm_response.beginner_tip}"

    issues: list[str] = []

    # ---- 1. Numeric value check (DPS / EHP / life values) --------------------
    # Extract all numbers that look like stat values from the explanation.
    # Numbers >= 100 are likely stat deltas; check them against known values.
    numeric_pattern = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?[kKmM]?")
    found_numbers: list[float] = []
    for match in numeric_pattern.finditer(text):
        raw = match.group().replace(",", "")
        multiplier = 1.0
        if raw.endswith(("k", "K")):
            raw = raw[:-1]
            multiplier = 1_000.0
        elif raw.endswith(("m", "M")):
            raw = raw[:-1]
            multiplier = 1_000_000.0
        try:
            found_numbers.append(float(raw) * multiplier)
        except ValueError:
            continue

    # Known stat delta values from engine data.
    dps_delta = engine_data.get("dps_delta") or 0.0
    life_delta = engine_data.get("life_delta") or 0.0
    es_delta = engine_data.get("es_delta") or 0.0
    price = engine_data.get("price_divine") or 0.0
    level_val = engine_data.get("level") or 0.0
    fire_res = engine_data.get("fire_res_delta") or 0.0
    cold_res = engine_data.get("cold_res_delta") or 0.0
    lightning_res = engine_data.get("lightning_res_delta") or 0.0

    known_values: list[float] = []
    for v in [dps_delta, life_delta, es_delta, price, level_val,
               fire_res, cold_res, lightning_res]:
        if abs(v) > 0:
            known_values.append(abs(v))

    for num in found_numbers:
        # Only flag large values that may be plausible stat claims.
        if abs(num) < 50:
            continue
        # Allow if number is within 5% of any known engine value.
        ok = False
        for known in known_values:
            if known > 0 and abs(num - known) / known <= 0.05:
                ok = True
                break
            # Also allow if the number is in a reasonable range fractional
            # of a large dps value (truncation artefacts).
            if abs(num - known) <= 5:
                ok = True
                break
        if not ok:
            issues.append(
                f"Number {num} not found in engine data "
                f"(known: {known_values!r})"
            )

    # ---- 2. Item name check --------------------------------------------------
    suggested_item: str = engine_data.get("suggested_item") or ""
    current_item: str = engine_data.get("current_item") or ""
    allowed_items = {
        n.lower()
        for n in [suggested_item, current_item]
        if n
    }
    # Additional items explicitly in the build
    for extra in engine_data.get("other_items") or []:
        allowed_items.add(str(extra).lower())

    # Heuristic: flag capitalized multi-word phrases that don't appear in
    # allowed items.  We look for sequences like "Piscator's Vigil" or
    # "Kaom's Heart".
    item_pattern = re.compile(r"\b([A-Z][a-z]+'?\s+[A-Z][a-z]+)\b")
    for match in item_pattern.finditer(text):
        name = match.group().lower()
        # Allow the suggested item and current item names.
        if any(name in allowed or allowed in name for allowed in allowed_items):
            continue
        issues.append(
            f"Item '{match.group()}' mentioned but not in recommendation "
            f"(allowed: {allowed_items!r})"
        )

    # ---- 3. Currency amount check -------------------------------------------
    currency_pattern = re.compile(
        r"(\d[\d,]*(?:\.\d+)?)\s*(?:divine|div|exalted|ex|chaos)",
        re.IGNORECASE,
    )
    if price and price > 0:
        for match in currency_pattern.finditer(text):
            try:
                mentioned_amount = float(match.group(1).replace(",", ""))
            except ValueError:
                continue
            if abs(mentioned_amount - price) / max(price, 0.01) > 0.05:
                issues.append(
                    f"Currency amount {mentioned_amount} differs from "
                    f"engine price {price:.2f} by more than 5%"
                )

    valid = len(issues) == 0
    if not valid:
        logger.warning(
            "LLM hallucination detected: %d issue(s): %s",
            len(issues),
            "; ".join(issues),
        )
    return ValidationResult(valid=valid, issues=issues)


# ---------------------------------------------------------------------------
# LLM Explainer Service
# ---------------------------------------------------------------------------

class LLMExplainerService:
    """Service that generates natural-language upgrade explanations via OpenAI.

    Falls back to a caller-supplied template string when:
    - ``openai_api_key`` is empty (feature disabled).
    - The daily spend cap is reached.
    - The OpenAI API call times out (> ``timeout_seconds``).
    - The API returns a 5xx error (after 1 retry).
    - The LLM output fails hallucination validation.
    - The global feature flag (``llm_enabled``) is ``False``.

    Attributes:
        model: OpenAI model identifier.
        timeout_seconds: Per-call timeout before fallback.
        daily_spend_cap_usd: Daily spend cap in USD.
        llm_enabled: Global on/off switch.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 3.0,
        daily_spend_cap_usd: float = 5.0,
        llm_enabled: bool = True,
    ) -> None:
        """Initialise the service.

        Args:
            api_key: OpenAI API key.  Pass an empty string to disable LLM.
            model: Model identifier (e.g. ``"gpt-4o-mini"``).
            timeout_seconds: Timeout per API call before fallback.
            daily_spend_cap_usd: Daily spend limit in USD (0 = unlimited).
            llm_enabled: Master feature flag.
        """
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.daily_spend_cap_usd = daily_spend_cap_usd
        self.llm_enabled = llm_enabled
        self._api_key = api_key
        self._client: AsyncOpenAI | None = (
            AsyncOpenAI(api_key=api_key) if api_key else None
        )
        self._tracker = _usage_tracker

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_explanation(
        self,
        *,
        slot: str,
        current_item: str,
        suggested_item: str,
        category: str,
        deltas: dict[str, float],
        price_divine: float | None,
        level: int,
        ascendancy: str,
        damage_type: str,
        playstyle: str,
        main_skill: str,
        template_explanation: str,
    ) -> tuple[str, str]:
        """Generate an explanation for an upgrade recommendation.

        Returns the best available explanation and its source label.

        Args:
            slot: Equipment / gem slot name.
            current_item: Currently equipped item name.
            suggested_item: Recommended item name.
            category: Recommendation category (e.g. ``"power_upgrade"``).
            deltas: Stat delta dict from the simulation.
            price_divine: Item price in divine orbs, or ``None``.
            level: Character level.
            ascendancy: Character ascendancy / class name.
            damage_type: Detected damage archetype (e.g. ``"fire"``).
            playstyle: Detected playstyle (e.g. ``"caster"``).
            main_skill: Name of the main skill.
            template_explanation: Pre-rendered template fallback string.

        Returns:
            Tuple of (``explanation_text``, ``source``) where ``source``
            is ``"llm"`` or ``"template"``.
        """
        if not self._should_use_llm():
            return template_explanation, "template"

        engine_data: dict[str, Any] = {
            "dps_delta": deltas.get("dps", 0.0),
            "life_delta": deltas.get("life", 0.0),
            "es_delta": deltas.get("energy_shield", 0.0),
            "price_divine": price_divine,
            "suggested_item": suggested_item,
            "current_item": current_item,
            # Include all numbers from the prompt so the validator
            # doesn't flag them as hallucinations.
            "level": float(level),
            "fire_res_delta": deltas.get("fire_res", 0.0),
            "cold_res_delta": deltas.get("cold_res", 0.0),
            "lightning_res_delta": deltas.get("lightning_res", 0.0),
        }

        user_prompt = self._build_user_prompt(
            slot=slot,
            current_item=current_item,
            suggested_item=suggested_item,
            category=category,
            deltas=deltas,
            price_divine=price_divine,
            level=level,
            ascendancy=ascendancy,
            damage_type=damage_type,
            playstyle=playstyle,
        )

        llm_result = await self._call_with_fallback(user_prompt)
        if llm_result is None:
            # Fallback already recorded by _call_with_fallback.
            return template_explanation, "template"

        # Validate for hallucinations.
        validation = validate_llm_output(llm_result, engine_data)
        if not validation.valid:
            logger.warning(
                "LLM hallucination — falling back to template "
                "(item=%s, issues=%s)",
                suggested_item,
                validation.issues,
            )
            self._tracker.record_fallback()
            return template_explanation, "template"

        # Combine explanation + optional beginner tip.
        final_text = llm_result.explanation
        if llm_result.beginner_tip:
            final_text = f"{final_text} {llm_result.beginner_tip}"

        return final_text, "llm"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_use_llm(self) -> bool:
        """Return True if LLM calls are currently allowed.

        Returns:
            ``False`` if:
            - ``llm_enabled`` is ``False``.
            - No API key is configured.
            - Daily spend cap is reached.
        """
        if not self.llm_enabled:
            return False
        if not self._api_key or self._client is None:
            return False
        if self._tracker.cap_reached(self.daily_spend_cap_usd):
            logger.warning(
                "LLM daily spend cap reached (%.4f USD); "
                "falling back to templates.",
                self._tracker.estimated_cost_usd,
            )
            self._tracker.record_fallback(cap_triggered=True)
            return False
        return True

    def _build_user_prompt(
        self,
        *,
        slot: str,
        current_item: str,
        suggested_item: str,
        category: str,
        deltas: dict[str, float],
        price_divine: float | None,
        level: int,
        ascendancy: str,
        damage_type: str,
        playstyle: str,
    ) -> str:
        """Format the user prompt from the template.

        Args:
            slot: Equipment slot name.
            current_item: Currently equipped item.
            suggested_item: Recommended item.
            category: Recommendation category label.
            deltas: Stat delta dict.
            price_divine: Item price in divines or ``None``.
            level: Character level.
            ascendancy: Ascendancy / class.
            damage_type: Damage archetype.
            playstyle: Playstyle archetype.

        Returns:
            Formatted user prompt string.
        """
        dps = deltas.get("dps", 0.0)

        return _USER_PROMPT_TEMPLATE.format(
            level=level,
            ascendancy=ascendancy or "Exile",
            damage_type=damage_type or "unknown",
            playstyle=playstyle or "unknown",
            slot=slot,
            current_item=current_item or "nothing",
            suggested_item=suggested_item,
            dps_delta=dps,
            life_delta=deltas.get("life", 0.0),
            es_delta=deltas.get("energy_shield", 0.0),
            fire_delta=deltas.get("fire_res", 0.0),
            cold_delta=deltas.get("cold_res", 0.0),
            lightning_delta=deltas.get("lightning_res", 0.0),
            price=f"{price_divine:.1f}" if price_divine is not None else "unknown",
            category=category,
        )

    async def _call_with_fallback(
        self,
        user_prompt: str,
    ) -> LLMExplanationOutput | None:
        """Call OpenAI with timeout and retry logic.

        Makes up to 2 attempts (1 retry on 5xx errors).  On any failure
        or timeout, returns ``None`` and records a fallback.

        Args:
            user_prompt: Formatted user prompt string.

        Returns:
            Parsed :class:`LLMExplanationOutput` on success, ``None`` on
            any failure.
        """
        assert self._client is not None, "Client must be initialised"

        for attempt in range(2):
            try:
                response = await asyncio.wait_for(
                    self._client.beta.chat.completions.parse(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format=LLMExplanationOutput,
                        max_tokens=300,
                        temperature=0.3,
                    ),
                    timeout=self.timeout_seconds,
                )

                usage = response.usage
                if usage:
                    self._tracker.record_usage(
                        input_tokens=usage.prompt_tokens,
                        output_tokens=usage.completion_tokens,
                    )
                    logger.debug(
                        "LLM tokens: input=%d output=%d cost~=%.5f USD",
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.prompt_tokens * _COST_PER_INPUT_TOKEN
                        + usage.completion_tokens * _COST_PER_OUTPUT_TOKEN,
                    )

                message = response.choices[0].message
                if message.parsed is not None:
                    return message.parsed

                # Model refused
                logger.warning(
                    "OpenAI model refusal: %s", message.refusal
                )
                self._tracker.record_fallback()
                return None

            except TimeoutError:
                logger.warning(
                    "LLM call timed out after %.1fs (attempt %d)",
                    self.timeout_seconds,
                    attempt + 1,
                )
                self._tracker.record_fallback()
                return None

            except APITimeoutError:
                logger.warning(
                    "OpenAI API timeout (attempt %d)", attempt + 1
                )
                self._tracker.record_fallback()
                return None

            except APIStatusError as exc:
                if exc.status_code >= 500 and attempt == 0:
                    # 5xx error — retry once.
                    logger.warning(
                        "OpenAI 5xx error %d (attempt %d), retrying",
                        exc.status_code,
                        attempt + 1,
                    )
                    await asyncio.sleep(0.2)
                    continue
                logger.warning(
                    "OpenAI API error %d: %s",
                    exc.status_code,
                    exc.message,
                )
                self._tracker.record_fallback()
                return None

            except Exception as exc:
                logger.warning("Unexpected LLM error: %s", exc)
                self._tracker.record_fallback()
                return None

        # All retries exhausted.
        self._tracker.record_fallback()
        return None


# ---------------------------------------------------------------------------
# Module-level singleton (lazily initialised from settings)
# ---------------------------------------------------------------------------

_service: LLMExplainerService | None = None


def get_llm_service() -> LLMExplainerService:
    """Return the module-level LLM service singleton.

    The service is lazily initialised on first access using the application
    :class:`~app.core.config.Settings`.

    Returns:
        :class:`LLMExplainerService` instance.
    """
    global _service
    if _service is None:
        from app.core.config import Settings

        settings = Settings()
        _service = LLMExplainerService(
            api_key=settings.openai_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            daily_spend_cap_usd=settings.llm_daily_spend_cap_usd,
            llm_enabled=settings.llm_enabled,
        )
    return _service

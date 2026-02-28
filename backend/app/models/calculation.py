"""Pydantic models for LuaJIT calculation requests and responses.

These models correspond to the data structures described in M2 of the
project milestones and are used by the ``/api/v1/calculate`` and
``/api/v1/calculate-swap`` endpoints.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CalculateRequest(BaseModel):
    """Request body for ``POST /api/v1/calculate``.

    The caller supplies a raw PoB export code (URL-safe base64-encoded,
    zlib-compressed XML) or the already-decoded XML.  One of ``build_code``
    or ``build_xml`` must be provided.
    """

    build_code: str | None = Field(
        default=None,
        description=(
            "PoB export code (URL-safe base64-encoded zlib-compressed XML)."
        ),
    )
    build_xml: str | None = Field(
        default=None,
        description="Raw PoB XML string (alternative to build_code).",
    )

    @field_validator("build_code", "build_xml", mode="before")
    @classmethod
    def _strip_whitespace(cls, v: str | None) -> str | None:
        """Strip surrounding whitespace from string fields."""
        return v.strip() if isinstance(v, str) else v

    def model_post_init(self, __context: object) -> None:
        """Validate that at least one input field is provided."""
        if not self.build_code and not self.build_xml:
            raise ValueError(
                "Either 'build_code' or 'build_xml' must be provided."
            )


class SwapItem(BaseModel):
    """A single item swap specification."""

    slot: str = Field(
        description=(
            "Equipment slot name, e.g. 'Helmet', 'Body Armour', "
            "'Weapon 1', 'Ring', 'Ring 2', 'Amulet', 'Belt', "
            "'Gloves', 'Boots', 'Flask 1'-'Flask 5'."
        )
    )
    item_text: str = Field(
        description=(
            "Path of Exile item text (paste from game tooltip or "
            "trade site)."
        )
    )


class CalculateSwapRequest(BaseModel):
    """Request body for ``POST /api/v1/calculate-swap``."""

    build_code: str | None = Field(default=None)
    build_xml: str | None = Field(default=None)
    slot: str = Field(description="Equipment slot to swap.")
    item_text: str = Field(description="New item in PoE text format.")

    @field_validator("build_code", "build_xml", mode="before")
    @classmethod
    def _strip_whitespace(cls, v: str | None) -> str | None:
        """Strip surrounding whitespace from string fields."""
        return v.strip() if isinstance(v, str) else v

    def model_post_init(self, __context: object) -> None:
        """Validate that a build source is provided."""
        if not self.build_code and not self.build_xml:
            raise ValueError(
                "Either 'build_code' or 'build_xml' must be provided."
            )


class SwapBatchItem(BaseModel):
    """One entry in a batch swap request."""

    slot: str
    item_text: str


class CalculateSwapBatchRequest(BaseModel):
    """Request body for ``POST /api/v1/calculate-swap/batch``."""

    build_code: str | None = Field(default=None)
    build_xml: str | None = Field(default=None)
    swaps: list[SwapBatchItem] = Field(
        min_length=1, description="List of item swaps to evaluate."
    )

    def model_post_init(self, __context: object) -> None:
        """Validate that a build source is provided."""
        if not self.build_code and not self.build_xml:
            raise ValueError(
                "Either 'build_code' or 'build_xml' must be provided."
            )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CalculationResult(BaseModel):
    """Structured stat output from a PoB calculation.

    All values default to 0 so the model deserialises safely when a stat
    is missing from the engine output (e.g. a life build has no ES).
    """

    dps: float = Field(default=0.0, description="Main skill DPS.")
    total_dps: float = Field(
        default=0.0,
        description="Sum of all skills/DoTs contributing to damage.",
    )
    life: int = Field(default=0, description="Maximum life pool.")
    energy_shield: int = Field(
        default=0, description="Maximum energy shield pool."
    )
    fire_res: int = Field(
        default=0, description="Fire resistance percentage."
    )
    cold_res: int = Field(
        default=0, description="Cold resistance percentage."
    )
    lightning_res: int = Field(
        default=0, description="Lightning resistance percentage."
    )
    chaos_res: int = Field(
        default=0, description="Chaos resistance percentage."
    )
    armour: int = Field(default=0, description="Armour rating.")
    evasion: int = Field(default=0, description="Evasion rating.")
    block_chance: float = Field(
        default=0.0, description="Block chance percentage."
    )
    spell_block: float = Field(
        default=0.0, description="Spell block chance percentage."
    )

    @classmethod
    def from_pob_stats(cls, stats: dict[str, Any]) -> CalculationResult:
        """Construct a CalculationResult from a raw PoB stats dict.

        The PoB engine may return any subset of stat keys; missing keys
        default to 0.

        Args:
            stats: Raw stat dict from the PoB API ``get_stats`` response.

        Returns:
            A fully populated :class:`CalculationResult`.
        """

        def _float(key: str) -> float:
            v = stats.get(key, 0)
            return float(v) if v is not None else 0.0

        def _int(key: str) -> int:
            v = stats.get(key, 0)
            return int(float(v)) if v is not None else 0

        # DPS: prefer CombinedDPS → TotalDPS → FullDPS → AverageDamage
        # For minion/summoner builds, player DPS is 0 — fall back to minion DPS
        # (MinionCombinedDPS / MinionTotalDPS from BuildOps minion augmentation)
        dps = (
            _float("CombinedDPS")
            or _float("TotalDPS")
            or _float("FullDPS")
            or _float("AverageDamage")
            or _float("MinionCombinedDPS")
            or _float("MinionTotalDPS")
            or _float("MinionAverageDamage")
        )

        return cls(
            dps=dps,
            total_dps=_float("TotalDPS") or _float("FullDPS") or dps,
            life=_int("Life"),
            energy_shield=_int("EnergyShield"),
            fire_res=_int("FireResist"),
            cold_res=_int("ColdResist"),
            lightning_res=_int("LightningResist"),
            chaos_res=_int("ChaosResist"),
            armour=_int("Armour"),
            evasion=_int("Evasion"),
            block_chance=_float("BlockChance"),
            spell_block=_float("SpellBlockChance"),
        )


class SwapResult(BaseModel):
    """Result of a single item swap calculation.

    Includes baseline and modified :class:`CalculationResult` objects plus
    a ``deltas`` dict showing the change in each stat.
    """

    slot: str = Field(description="Equipment slot that was swapped.")
    new_item_name: str = Field(
        default="", description="Name of the item that was swapped in."
    )
    baseline: CalculationResult
    modified: CalculationResult
    deltas: dict[str, float] = Field(
        description="Stat name → numeric change (positive = improvement)."
    )

    @classmethod
    def from_swap_data(
        cls,
        slot: str,
        item_name: str,
        baseline_stats: dict[str, Any],
        modified_stats: dict[str, Any],
    ) -> SwapResult:
        """Build a SwapResult from raw PoB stats dicts.

        Args:
            slot: Slot name.
            item_name: Display name of the new item.
            baseline_stats: Raw stats before the swap.
            modified_stats: Raw stats after the swap.

        Returns:
            A SwapResult with computed deltas.
        """
        baseline = CalculationResult.from_pob_stats(baseline_stats)
        modified = CalculationResult.from_pob_stats(modified_stats)

        # Compute deltas for all numeric fields
        deltas: dict[str, float] = {}
        for field_name in CalculationResult.model_fields:
            b_raw: Any = getattr(baseline, field_name)
            m_raw: Any = getattr(modified, field_name)
            b_val: float = float(b_raw) if b_raw is not None else 0.0
            m_val: float = float(m_raw) if m_raw is not None else 0.0
            delta = m_val - b_val
            if delta != 0.0:
                deltas[field_name] = round(delta, 4)

        return cls(
            slot=slot,
            new_item_name=item_name,
            baseline=baseline,
            modified=modified,
            deltas=deltas,
        )


class BatchSwapResult(BaseModel):
    """Result of a batch swap calculation."""

    build_code: str = Field(default="", description="Echo of input details.")
    results: list[SwapResult | dict[str, str]] = Field(
        description=(
            "Ordered list of swap results. Failed swaps include an "
            "'error' key."
        )
    )

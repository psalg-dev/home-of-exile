"""Pydantic models for the M3 candidate pool pipeline.

These models describe the build input (BuildData), archetype classification
(Archetype), candidate items/gems, and constraint validation results used by
the candidate generation pipeline.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Build data models (Python mirror of the frontend PoB types)
# ---------------------------------------------------------------------------


class CharacterAttrs(BaseModel):
    """Character base attributes (strength, dexterity, intelligence).

    Defaults to a permissive 9999 so that constraint filtering is effectively
    disabled when attribute data is unavailable.
    """

    str: int = Field(default=9999, ge=0)
    dex: int = Field(default=9999, ge=0)
    int_: int = Field(default=9999, ge=0, alias="int")

    model_config = {"populate_by_name": True}


class BuildStats(BaseModel):
    """Key statistics extracted from a PoB build.

    All fields default to 0 so the model deserialises safely when a stat
    is absent.
    """

    life: int = Field(default=0, ge=0)
    energy_shield: int = Field(default=0, ge=0)
    dps: float = Field(default=0.0, ge=0.0)
    fire_res: int = Field(default=0)
    cold_res: int = Field(default=0)
    lightning_res: int = Field(default=0)
    chaos_res: int = Field(default=0)


class ItemAttrReq(BaseModel):
    """Attribute requirements for an item (str/dex/int)."""

    str: int = Field(default=0, ge=0, alias="str")
    dex: int = Field(default=0, ge=0, alias="dex")
    int_: int = Field(default=0, ge=0, alias="int")

    model_config = {"populate_by_name": True}


class BuildItem(BaseModel):
    """An equipped item in a build, as provided by the PoB XML parser."""

    name: str = Field(default="")
    base_name: str = Field(default="")
    slot: str = Field(default="")
    rarity: str = Field(default="normal")
    level_req: int = Field(default=0, ge=0)
    attr_req: ItemAttrReq = Field(default_factory=ItemAttrReq)
    sockets: str = Field(default="")
    mods: list[str] = Field(default_factory=list)
    corrupted: bool = Field(default=False)

    @field_validator("mods", mode="before")
    @classmethod
    def coerce_mods(cls, v: Any) -> list[Any]:
        """Ensure mods is always a list."""
        return v if isinstance(v, list) else []


class BuildGem(BaseModel):
    """A skill gem within a skill group."""

    name_spec: str = Field(default="", description="Display name of the gem.")
    skill_id: str = Field(default="")
    level: int = Field(default=1, ge=1)
    quality: int = Field(default=0, ge=0)
    enabled: bool = Field(default=True)
    is_support: bool = Field(default=False)


class BuildSkillGroup(BaseModel):
    """A linked socket group containing gems."""

    slot: str = Field(default="")
    label: str = Field(default="")
    enabled: bool = Field(default=True)
    gems: list[BuildGem] = Field(default_factory=list)
    main_active_gem_index: int = Field(default=0, ge=0)

    @field_validator("gems", mode="before")
    @classmethod
    def coerce_gems(cls, v: Any) -> list[Any]:
        """Ensure gems is always a list."""
        return v if isinstance(v, list) else []

    @property
    def main_active_gem(self) -> BuildGem | None:
        """Return the primary active (non-support) gem, if any."""
        active = [g for g in self.gems if not g.is_support and g.enabled]
        if self.main_active_gem_index < len(active):
            return active[self.main_active_gem_index]
        return active[0] if active else None


class BuildData(BaseModel):
    """Structured representation of a Path of Exile build.

    This is the primary input to the candidate pool pipeline.  It mirrors
    the frontend ``BuildData`` type (see ``frontend/src/lib/pob/types.ts``)
    but uses snake_case field names and Pydantic for validation.
    """

    character_name: str = Field(default="")
    char_class: str = Field(
        default="", alias="class",
        description="PoE character class, e.g. 'Witch'.",
    )
    ascendancy: str = Field(default="")
    level: int = Field(default=1, ge=1, le=100)
    bandit: str = Field(default="None")
    main_skill: str = Field(default="")
    stats: BuildStats = Field(default_factory=BuildStats)
    attrs: CharacterAttrs = Field(default_factory=CharacterAttrs)
    passive_tree: list[int] = Field(default_factory=list)
    items: dict[str, BuildItem] = Field(
        default_factory=dict,
        description="Map of slot name → equipped item.",
    )
    skill_groups: list[BuildSkillGroup] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @field_validator("passive_tree", mode="before")
    @classmethod
    def coerce_passive_tree(cls, v: Any) -> list[Any]:
        """Ensure passive_tree is always a list."""
        return v if isinstance(v, list) else []

    @field_validator("skill_groups", mode="before")
    @classmethod
    def coerce_skill_groups(cls, v: Any) -> list[Any]:
        """Ensure skill_groups is always a list."""
        return v if isinstance(v, list) else []

    @property
    def all_active_gems(self) -> list[BuildGem]:
        """Return all active (non-support, enabled) gems across all groups."""
        return [
            gem
            for group in self.skill_groups
            for gem in group.gems
            if not gem.is_support and gem.enabled
        ]

    @property
    def all_gem_names(self) -> list[str]:
        """Return all equipped gem display names (active + support)."""
        return [
            gem.name_spec
            for group in self.skill_groups
            for gem in group.gems
            if gem.enabled and gem.name_spec
        ]


# ---------------------------------------------------------------------------
# Archetype models
# ---------------------------------------------------------------------------


class Archetype(BaseModel):
    """Classified build archetype used to score candidate relevance.

    Attributes:
        damage_type: Primary damage element or sub-system
            (physical, fire, cold, lightning, chaos, minion, totem, trap).
        defense_style: Defensive layer (life, es, hybrid, lowlife, ci).
        playstyle: Combat style (melee, ranged, caster, summoner).
    """

    damage_type: str = Field(
        description=(
            "Primary damage type: physical, fire, cold, lightning, "
            "chaos, minion, totem, trap."
        )
    )
    defense_style: str = Field(
        description="Defensive layer: life, es, hybrid, lowlife, ci."
    )
    playstyle: str = Field(
        description="Combat style: melee, ranged, caster, summoner."
    )


# ---------------------------------------------------------------------------
# Candidate models
# ---------------------------------------------------------------------------


class CandidateItem(BaseModel):
    """A candidate upgrade item for a specific equipment slot.

    Attributes:
        name: Unique / rare item name (empty for base items).
        base_name: Item base type name.
        slot: Equipment slot (e.g. 'Helmet').
        rarity: Item rarity (normal, magic, rare, unique).
        level_req: Level requirement.
        attr_req: Attribute requirements (str/dex/int).
        key_mods: Notable mod lines relevant to the archetype.
        price_divine: Price in divine orbs (None if unpriced).
        price_confidence: Listing confidence (high, medium, low).
        relevance_score: Archetype match score between 0.0 and 1.0.
        source: Data source (poe.ninja_unique, poe.ninja_rare, repoe).
    """

    name: str = Field(default="")
    base_name: str = Field(default="")
    slot: str
    rarity: str = Field(default="normal")
    level_req: int = Field(default=0, ge=0)
    attr_req: ItemAttrReq = Field(default_factory=ItemAttrReq)
    key_mods: list[str] = Field(default_factory=list)
    price_divine: float | None = Field(default=None)
    price_confidence: str = Field(default="low")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = Field(default="repoe")


class CandidateGem(BaseModel):
    """A candidate gem upgrade for a skill group.

    Attributes:
        name: Display name of the gem.
        level_req: Level requirement.
        attr_req: Attribute requirements (str/dex/int).
        tags: Gem tags from RePoE.
        is_support: True if this is a support gem.
        price_divine: Price in divine orbs (None if unpriced).
    """

    name: str
    level_req: int = Field(default=1, ge=1)
    attr_req: ItemAttrReq = Field(default_factory=ItemAttrReq)
    tags: list[str] = Field(default_factory=list)
    is_support: bool = Field(default=False)
    price_divine: float | None = Field(default=None)


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


class ValidationResult(BaseModel):
    """Result of a constraint check for a candidate item against a build.

    Attributes:
        valid: True if the item is unambiguously usable by the build.
        warnings: Human-readable warning strings for borderline cases
            (e.g. 'Two points of Strength short').
    """

    valid: bool = Field(default=True)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------


class CandidatesRequest(BaseModel):
    """Request body for ``POST /api/v1/candidates``.

    The caller provides a parsed build (or encodes one from PoB XML) plus
    an optional slot filter and league for live pricing.
    """

    build: BuildData
    slot: str | None = Field(
        default=None,
        description=(
            "If provided, generate candidates only for this slot. "
            "If omitted, all slots are processed."
        ),
    )
    league: str = Field(
        default="Settlers",
        description="League name used to fetch live poe.ninja prices.",
    )


class SlotCandidates(BaseModel):
    """Candidate results for a single equipment slot."""

    slot: str
    archetype: Archetype
    candidates: list[CandidateItem]


class GemGroupCandidates(BaseModel):
    """Candidate gem results for a single skill group."""

    slot: str
    support_candidates: list[CandidateGem]
    skill_alternatives: list[CandidateGem]


class CandidatesResponse(BaseModel):
    """Response body for ``POST /api/v1/candidates``."""

    archetype: Archetype
    item_candidates: list[SlotCandidates] = Field(default_factory=list)
    gem_candidates: list[GemGroupCandidates] = Field(default_factory=list)

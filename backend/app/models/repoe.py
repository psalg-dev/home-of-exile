"""Pydantic v2 models mirroring the RePoE data format."""

from typing import Any

from pydantic import BaseModel, field_validator


class RePoEBaseItem(BaseModel):
    """A base item entry from RePoE base_items.json."""

    name: str = ""
    item_class: str = ""
    requirements: dict[str, Any] = {}
    implicit_mods: list[str] = []
    tags: list[str] = []

    @field_validator("requirements", mode="before")
    @classmethod
    def coerce_requirements(cls, v: Any) -> dict[str, Any]:
        """Convert null to empty dict."""
        return v if isinstance(v, dict) else {}

    @field_validator("implicit_mods", "tags", mode="before")
    @classmethod
    def coerce_list(cls, v: Any) -> list[Any]:
        """Convert null to empty list."""
        return v if isinstance(v, list) else []


class RePoEGem(BaseModel):
    """A gem/skill entry from RePoE gems.json."""

    class BaseItem(BaseModel):
        """Nested base item descriptor within a gem entry."""

        display_name: str = ""
        release_state: str = ""

    base_item: BaseItem | None = None
    tags: list[str] = []
    is_support: bool = False

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[Any]:
        """Convert null to empty list."""
        return v if isinstance(v, list) else []


class RePoEModStat(BaseModel):
    """Stat range for a single stat within a mod."""

    id: str = ""
    min: int = 0
    max: int = 0


class RePoESpawnWeight(BaseModel):
    """Spawn weight for a tag within a mod."""

    tag: str = ""
    weight: int = 0


class RePoEMod(BaseModel):
    """A mod entry from RePoE mods.json."""

    name: str = ""
    generation_type: str = ""
    groups: list[str] = []
    stats: list[RePoEModStat] = []
    spawn_weights: list[RePoESpawnWeight] = []

    @field_validator("groups", "stats", "spawn_weights", mode="before")
    @classmethod
    def coerce_list(cls, v: Any) -> list[Any]:
        """Convert null to empty list."""
        return v if isinstance(v, list) else []

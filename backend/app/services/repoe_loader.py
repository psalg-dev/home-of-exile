"""
RePoE data loader service.

Reads static JSON data files from the configured data directory
and caches the parsed results using functools.lru_cache.
"""

import functools
import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models.repoe import RePoEBaseItem, RePoEGem, RePoEMod


def _data_path(filename: str) -> Path:
    """
    Resolve the absolute path to a RePoE data file.

    Args:
        filename: The JSON filename (e.g. 'base_items.json').

    Returns:
        Resolved Path object for the file.
    """
    return Path(settings.repoe_data_dir).resolve() / filename


@functools.lru_cache(maxsize=1)
def load_base_items() -> dict[str, RePoEBaseItem]:
    """
    Load and cache all base item data from base_items.json.

    Returns:
        A dict mapping item ID (str) → RePoEBaseItem.
    """
    path = _data_path("base_items.json")
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {item_id: RePoEBaseItem.model_validate(data) for item_id, data in raw.items()}


@functools.lru_cache(maxsize=1)
def load_gems() -> dict[str, RePoEGem]:
    """
    Load and cache all gem data from gems.json.

    Returns:
        A dict mapping gem ID (str) → RePoEGem.
    """
    path = _data_path("gems.json")
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {gem_id: RePoEGem.model_validate(data) for gem_id, data in raw.items()}


@functools.lru_cache(maxsize=1)
def load_mods() -> dict[str, RePoEMod]:
    """
    Load and cache all mod data from mods.json.

    Returns:
        A dict mapping mod ID (str) → RePoEMod.
    """
    path = _data_path("mods.json")
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {mod_id: RePoEMod.model_validate(data) for mod_id, data in raw.items()}

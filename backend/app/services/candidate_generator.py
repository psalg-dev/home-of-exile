"""Candidate pool pipeline — item and gem candidate generation.

This module implements the three core pipeline stages described in M3:

* :func:`generate_candidates` (D3.2) — generate priced, filtered item
  candidates for a single equipment slot.
* :func:`generate_gem_candidates` (D3.3) — generate support and skill
  gem candidates for a skill group.
* :func:`validate_constraints` (D3.5) — validate character constraints
  against a candidate item.

Additional public helper:
* :func:`run_pipeline` — run all slots and skill groups in one call.

Design notes:
- Unique items come from poe.ninja price tables (populated by
  :class:`~app.services.poe_ninja.PoeNinjaClient`).
- Base items come from RePoE via
  :func:`~app.services.repoe_loader.load_base_items`.
- Gem candidates come from RePoE via
  :func:`~app.services.repoe_loader.load_gems`.
- All public functions are synchronous; network I/O (poe.ninja) is
  expected to be completed before calling them (pass pre-fetched price
  dicts to avoid repeated async calls).
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.candidate import (
    Archetype,
    BuildData,
    BuildSkillGroup,
    CandidateGem,
    CandidateItem,
    GemGroupCandidates,
    ItemAttrReq,
    SlotCandidates,
    ValidationResult,
)
from app.services.archetype import (
    archetype_template_mods,
    extract_key_mods,
    score_mod_relevance,
)
from app.services.repoe_loader import load_base_items, load_gems

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slot ↔ item-class mapping
# ---------------------------------------------------------------------------

# Maps each equipment slot to the RePoE item_class values associated with it.
# Used to filter base items and poe.ninja entries by slot.
SLOT_TO_CLASSES: dict[str, list[str]] = {
    "Helmet": ["Helmet"],
    "Body Armour": ["Body Armour"],
    "Gloves": ["Gloves"],
    "Boots": ["Boots"],
    "Amulet": ["Amulet"],
    "Ring": ["Ring"],
    "Ring 2": ["Ring"],
    "Belt": ["Belt"],
    "Weapon": [
        "One Hand Axe", "One Hand Mace", "One Hand Sword",
        "Thrusting One Hand Sword", "Claw", "Dagger", "Rune Dagger",
        "Wand", "Sceptre", "Two Hand Axe", "Two Hand Mace",
        "Two Hand Sword", "Staff", "Warstaff", "Bow", "FishingRod",
    ],
    "Weapon 2": [
        "One Hand Axe", "One Hand Mace", "One Hand Sword",
        "Thrusting One Hand Sword", "Claw", "Dagger", "Rune Dagger",
        "Wand", "Sceptre", "Shield", "Quiver",
    ],
    "Shield": ["Shield"],
    "Flask": [
        "LifeFlask", "ManaFlask", "HybridFlask",
        "UtilityFlask",
    ],
    "Jewel": ["Jewel", "AbyssJewel"],
}

# Normalised slot aliases (frontend may send either form).
_SLOT_ALIASES: dict[str, str] = {
    "Weapon 1": "Weapon",
}

# Hard cap on candidates returned per slot (performance guard).
_MAX_CANDIDATES = 20

# Minimum listing count thresholds for price confidence levels.
_CONFIDENCE_HIGH = 20
_CONFIDENCE_MED = 5

# How many levels below the character level a base item is still considered
# relevant.  Bases with level_req < (char_level - delta) are skipped so that
# low-tier items like 'Shabby Jerkin' never appear for a level-99 character.
_MIN_BASE_ILVL_DELTA = 40

# ---------------------------------------------------------------------------
# Slot-specific template-mod overrides for simulation
# ---------------------------------------------------------------------------
# When PoB simulates a candidate item it uses the item's key_mods as explicit
# mods on the base.  Using the same full-archetype damage template on every
# slot produces identical DPS deltas (all driven by "50% increased Fire Damage"
# regardless of whether the slot is a shield or an amulet), which makes
# ranking meaningless.  Instead each slot gets plausible top-roll mods that
# reflect what it actually contributes to the build.
_SLOT_TEMPLATE_OVERRIDES: dict[str, list[str]] = {
    # Body armour: primary life-and-resistance slot; no explicit damage%.
    "Body Armour": [
        "+120 to maximum Life",
        "+35% to Fire Resistance",
        "+35% to Cold Resistance",
        "+35% to Lightning Resistance",
        "6% increased maximum Life",
    ],
    # Off-hand shields contribute life, resistances and block.
    # Weapons in the off-hand use archetype_template_mods instead (fallthrough).
    "Weapon 2": [
        "+80 to maximum Life",
        "+35% to Fire Resistance",
        "+35% to Cold Resistance",
        "20% Chance to Block Attack Damage",
    ],
    # Helmet: life + resistances; strength as common stat for melee/summoners.
    "Helmet": [
        "+80 to maximum Life",
        "+35% to Fire Resistance",
        "+35% to Cold Resistance",
        "+40 to Strength",
    ],
    # Gloves: life + resistances + speed modifier.
    "Gloves": [
        "+70 to maximum Life",
        "+30% to Fire Resistance",
        "+30% to Cold Resistance",
        "15% increased Attack Speed",
    ],
    # Boots: movement speed is the core upgrade alongside life/res.
    "Boots": [
        "+70 to maximum Life",
        "+30% to Fire Resistance",
        "+30% to Cold Resistance",
        "30% increased Movement Speed",
    ],
    # Belt: high flat life + all resistances; life% as unique belt suffix.
    "Belt": [
        "+100 to maximum Life",
        "+30% to Fire Resistance",
        "+30% to Cold Resistance",
        "+30% to Lightning Resistance",
    ],
    # Rings contribute life + resistances; less damage-focused than amulets.
    "Ring": [
        "+60 to maximum Life",
        "+30% to Fire Resistance",
        "+30% to Cold Resistance",
    ],
    "Ring 2": [
        "+60 to maximum Life",
        "+30% to Fire Resistance",
        "+30% to Cold Resistance",
    ],
    # Amulet: life + resistances are the realistic explicit mods that roll on
    # rare amulets and that trade searches can find.  Damage mods (fire%, DoT
    # multi, cast speed) are excluded here because they only appear as implicits
    # on specific bases (Blue Pearl Amulet, etc.) and almost never roll as
    # explicit mods — including them in the simulation template grossly inflates
    # the DPS delta shown to the user.
    "Amulet": [
        "+80 to maximum Life",
        "+30% to Fire Resistance",
        "+30% to Cold Resistance",
        "+30% to Lightning Resistance",
    ],
    # Weapon slots fall through to archetype_template_mods, which includes the
    # primary build-damage modifier.  This intentionally preserves higher DPS
    # deltas for the most offensive slots.
}

# ---------------------------------------------------------------------------
# poe.ninja item type → item class mapping
# (used to infer slot from poe.ninja category data)
# ---------------------------------------------------------------------------

_NINJA_CATEGORY_TO_CLASSES: dict[str, list[str]] = {
    "UniqueWeapon": [
        "One Hand Axe", "One Hand Mace", "One Hand Sword",
        "Thrusting One Hand Sword", "Claw", "Dagger", "Rune Dagger",
        "Wand", "Sceptre", "Two Hand Axe", "Two Hand Mace",
        "Two Hand Sword", "Staff", "Warstaff", "Bow",
    ],
    "UniqueArmour": [
        "Helmet", "Body Armour", "Gloves", "Boots", "Shield",
    ],
    "UniqueAccessory": ["Amulet", "Ring", "Belt"],
    "UniqueFlask": ["LifeFlask", "ManaFlask", "HybridFlask", "UtilityFlask"],
    "UniqueJewel": ["Jewel", "AbyssJewel"],
    "SkillGem": ["Active Skill Gem", "Support Skill Gem"],
}


def _normalise_slot(slot: str) -> str:
    """Normalise a slot name, resolving known aliases."""
    return _SLOT_ALIASES.get(slot, slot)


def _slot_template_mods(archetype: Archetype, slot: str) -> list[str]:
    """Return template mods appropriate for *slot* and *archetype*.

    Defensive slots (body armour, shield, boots, belt, rings, amulet, etc.)
    return a curated list focused on life and resistances that omits the
    primary build-damage modifier.  Offensive slots (weapon) return the full
    :func:`archetype_template_mods` result, which includes the archetype's
    primary damage mod.

    Using slot-specific mods avoids all candidates producing the same
    DPS delta (which happens when every slot is simulated with the same
    damage-boosting mod).

    Args:
        archetype: Detected build archetype.
        slot: Normalised equipment slot name.

    Returns:
        List of up to 5 PoE-format mod strings for item simulation.
    """
    override = _SLOT_TEMPLATE_OVERRIDES.get(slot)
    if override is not None:
        return override[:]
    # Slots with no override (Weapon, Jewel, Flask) get the full
    # archetype template including the primary damage modifier.
    return archetype_template_mods(archetype)


def _confidence_from_count(listing_count: int) -> str:
    """Map a listing count to a confidence label.

    Args:
        listing_count: Number of trade listings on poe.ninja.

    Returns:
        'high', 'medium', or 'low'.
    """
    if listing_count >= _CONFIDENCE_HIGH:
        return "high"
    if listing_count >= _CONFIDENCE_MED:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_candidates(
    build: BuildData,
    slot: str,
    archetype: Archetype,
    prices: dict[str, Any],
) -> list[CandidateItem]:
    """Generate candidate upgrade items for a single equipment slot.

    Combines unique items from poe.ninja prices with viable base items
    from RePoE, then filters by character constraints and scores each
    candidate for archetype relevance.

    Args:
        build: The character's parsed build data.
        slot: Equipment slot name (e.g. 'Helmet').
        archetype: Detected build archetype.
        prices: Pre-fetched poe.ninja item-price dict as returned by
            :meth:`~app.services.poe_ninja.PoeNinjaClient.get_item_prices`.
            Keys are item names; values are price dicts with ``divineValue``
            and ``listingCount``.

    Returns:
        List of :class:`~app.models.candidate.CandidateItem` sorted by
        relevance score (descending), capped at ``_MAX_CANDIDATES``.
    """
    slot = _normalise_slot(slot)
    target_classes = SLOT_TO_CLASSES.get(slot, [])
    if not target_classes:
        logger.warning("Unknown slot '%s'; returning empty candidate list", slot)
        return []

    candidates: list[CandidateItem] = []

    # 1. poe.ninja unique items
    candidates.extend(
        _candidates_from_poe_ninja(
            build, slot, target_classes, archetype, prices
        )
    )

    # 2. RePoE base items (for viable rare base types)
    candidates.extend(
        _candidates_from_repoe(
            build, slot, target_classes, archetype
        )
    )

    # 3. Filter by hard constraints
    valid_candidates = [
        c for c in candidates
        if _passes_hard_constraints(build, c)
    ]

    # 4. Discard candidates with zero relevance (unless we'd end up empty)
    relevant = [c for c in valid_candidates if c.relevance_score > 0.0]
    if not relevant:
        relevant = valid_candidates

    # 5. Sort by relevance descending; cap at max
    relevant.sort(key=lambda c: c.relevance_score, reverse=True)
    return relevant[:_MAX_CANDIDATES]


def generate_gem_candidates(
    build: BuildData,
    skill_group: BuildSkillGroup,
    archetype: Archetype,
    prices: dict[str, Any],
) -> GemGroupCandidates:
    """Generate candidate gems for a skill group.

    Produces two lists:
    * ``support_candidates`` — support gems compatible with the main
      skill's tags that are not already equipped.
    * ``skill_alternatives`` — alternative active skills for the archetype.

    Args:
        build: Parsed build data.
        skill_group: The skill group to generate gems for.
        archetype: Detected build archetype.
        prices: Pre-fetched poe.ninja price dict.

    Returns:
        A :class:`~app.models.candidate.GemGroupCandidates` instance.
    """
    main_gem = skill_group.main_active_gem
    main_tags: list[str] = []
    if main_gem:
        # Look up gem tags from RePoE
        gems_data = load_gems()
        for _, gem_entry in gems_data.items():
            display = (
                gem_entry.base_item.display_name
                if gem_entry.base_item
                else ""
            )
            if display.lower() == main_gem.name_spec.lower():
                main_tags = gem_entry.tags or []
                break

    equipped_names_lower = {
        g.name_spec.lower()
        for g in skill_group.gems
        if g.enabled
    }

    support_candidates = _generate_support_candidates(
        build, main_tags, equipped_names_lower, archetype, prices
    )
    skill_alternatives = _generate_skill_alternatives(
        build, archetype, equipped_names_lower, prices
    )

    return GemGroupCandidates(
        slot=skill_group.slot,
        support_candidates=support_candidates,
        skill_alternatives=skill_alternatives,
    )


def validate_constraints(
    build: BuildData,
    candidate: CandidateItem,
) -> ValidationResult:
    """Validate character constraints against a candidate item.

    Checks:
    * Level requirement vs. character level.
    * Strength / Dexterity / Intelligence requirements vs. character
      attributes.
    * Flags borderline cases as warnings (within 10 points of meeting
      the requirement) rather than hard failures.

    Args:
        build: Parsed build data, including character level and attributes.
        candidate: Candidate item to validate.

    Returns:
        A :class:`~app.models.candidate.ValidationResult` with ``valid``
        set to ``False`` and ``warnings`` populated if constraints are
        violated.
    """
    warnings: list[str] = []
    valid = True

    # Level requirement
    if candidate.level_req > build.level:
        valid = False
        warnings.append(
            f"Level {candidate.level_req} required "
            f"(character is level {build.level})"
        )
    elif candidate.level_req > build.level - 5:
        # Close to the level requirement — flag as marginal
        warnings.append(
            f"Level requirement ({candidate.level_req}) is close to "
            f"character level ({build.level})"
        )

    # Attribute requirements
    attr_map = {
        "str": (
            candidate.attr_req.str,
            build.attrs.str,
            "Strength",
        ),
        "dex": (
            candidate.attr_req.dex,
            build.attrs.dex,
            "Dexterity",
        ),
        "int": (
            candidate.attr_req.int_,
            build.attrs.int_,
            "Intelligence",
        ),
    }
    for _key, (req, have, label) in attr_map.items():
        if req <= 0:
            continue
        if have < req:
            shortfall = req - have
            valid = False
            warnings.append(
                f"{shortfall} {label} short "
                f"(requires {req}, have {have})"
            )
        elif have < req + 10:
            warnings.append(
                f"{label} is tight: requires {req}, "
                f"character has {have}"
            )

    return ValidationResult(valid=valid, warnings=warnings)


def run_pipeline(
    build: BuildData,
    archetype: Archetype,
    prices: dict[str, Any],
    slot_filter: str | None = None,
) -> tuple[list[SlotCandidates], list[GemGroupCandidates]]:
    """Run the full candidate pipeline for all slots and skill groups.

    Args:
        build: Parsed build data.
        archetype: Detected build archetype.
        prices: Pre-fetched poe.ninja price dict.
        slot_filter: If provided, only process this slot. Otherwise, process
            all 10 equipment slots.

    Returns:
        A tuple of (item_candidates, gem_candidates).
    """
    slots = list(SLOT_TO_CLASSES.keys())
    if slot_filter:
        norm = _normalise_slot(slot_filter)
        if norm in SLOT_TO_CLASSES:
            slots = [norm]
        else:
            logger.warning("Unknown slot filter '%s'; processing all slots", slot_filter)

    # Item candidates
    item_candidates: list[SlotCandidates] = []
    for slot in slots:
        candidates = generate_candidates(build, slot, archetype, prices)
        item_candidates.append(
            SlotCandidates(
                slot=slot,
                archetype=archetype,
                candidates=candidates,
            )
        )

    # Gem candidates (only for enabled skill groups)
    gem_candidates: list[GemGroupCandidates] = []
    for group in build.skill_groups:
        if group.enabled and group.gems:
            gem_group = generate_gem_candidates(
                build, group, archetype, prices
            )
            gem_candidates.append(gem_group)

    return item_candidates, gem_candidates


# ---------------------------------------------------------------------------
# Internal helpers — item candidate generation
# ---------------------------------------------------------------------------


def _candidates_from_poe_ninja(
    build: BuildData,
    slot: str,
    target_classes: list[str],
    archetype: Archetype,
    prices: dict[str, Any],
) -> list[CandidateItem]:
    """Build candidate list from the poe.ninja price table.

    Iterates through all price entries, attempts to determine the slot
    from the base type name via RePoE lookup, and constructs a
    CandidateItem with pricing data.

    Args:
        build: Build data (for level/attrs used in constraint pre-filtering).
        slot: Target slot name.
        target_classes: Item classes valid for this slot.
        archetype: Build archetype for relevance scoring.
        prices: poe.ninja price dict.

    Returns:
        List of candidate items sourced from poe.ninja.
    """
    base_items = load_base_items()
    # Only include tradeable base items (same filter as _candidates_from_repoe).
    # Excludes unique_only items (demigod trophies, etc.) and unreleased items
    # so they cannot slip through as poe.ninja candidates.
    _tradeable_states = {"released", "legacy"}
    _tradeable_bases = {
        k: v for k, v in base_items.items()
        if not v.release_state or v.release_state in _tradeable_states
    }
    # Build a lower-case base-name → item_class map for lookup.
    base_name_to_class: dict[str, str] = {
        v.name.lower(): v.item_class
        for v in _tradeable_bases.values()
        if v.name
    }
    # Also map lower-case item ID → item_class
    id_to_class: dict[str, str] = {
        k.lower(): v.item_class
        for k, v in _tradeable_bases.items()
    }

    candidates: list[CandidateItem] = []

    for item_name, price_info in prices.items():
        if not isinstance(price_info, dict):
            continue

        # Determine base type / item class from the price entry.
        base_type: str = price_info.get("baseType", "") or ""
        item_class = (
            base_name_to_class.get(base_type.lower())
            or id_to_class.get(base_type.lower())
        )
        if not item_class:
            # Fall back: look up by the item name itself (for base-type items)
            item_class = base_name_to_class.get(item_name.lower())

        if not item_class or item_class not in target_classes:
            continue

        divine_val = float(price_info.get("divineValue", 0) or 0)
        listing_count = int(price_info.get("listingCount", 0) or 0)

        candidates.append(
            CandidateItem(
                name=item_name,
                base_name=base_type or item_name,
                slot=slot,
                rarity="unique",
                level_req=int(price_info.get("levelRequired", 0) or 0),
                attr_req=_parse_attr_req(price_info),
                key_mods=[],  # poe.ninja overview doesn't list mods
                price_divine=divine_val if divine_val > 0 else None,
                price_confidence=_confidence_from_count(listing_count),
                relevance_score=0.3,  # poe.ninja uniques get base score
                source="poe.ninja_unique",
            )
        )

    return candidates


def _shield_matches_defense_style(tags: list[str], defense_style: str) -> bool:
    """Return True if a shield base type is appropriate for the defense style.

    RePoE base_items.json uses the following discriminating tags for shields:
      - ``str_shield``     → Tower Shields (armour)
      - ``dex_shield``     → Bucklers (evasion)
      - ``str_dex_shield`` → Round Shields (armour/evasion hybrid)
      - ``str_int_shield`` → Kite Shields (armour/ES hybrid)
      - ``dex_int_shield`` → Spiked Shields (evasion/ES hybrid)
      - ``focus``          → Spirit Shields (ES)

    Life builds are Str-based and benefit from armour-layer shields.
    ES / CI builds are Int-based and benefit from Spirit Shields.
    """
    tag_set = set(tags)
    if defense_style == "life":
        # Str-based: Tower Shields, Round Shields, Kite Shields — anything
        # that has a strength component.  Exclude pure evasion (Bucklers) and
        # pure ES (Spirit Shields).
        return bool(tag_set & {"str_shield", "str_dex_shield", "str_int_shield"})
    if defense_style in ("es", "ci", "lowlife"):
        # Int-based: Spirit Shields, Spiked Shields, Kite Shields — anything
        # that has an intelligence component.
        return bool(tag_set & {"focus", "dex_int_shield", "str_int_shield"})
    if defense_style == "hybrid":
        # Life + ES hybrid: exclude pure evasion shields (Bucklers) but allow
        # both armour and ES options.
        return "dex_shield" not in tag_set
    # Unknown / other defense style: no filtering
    return True


# Item classes whose defensive-type tags should be filtered by defense style.
_ARMOUR_CLASSES: frozenset[str] = frozenset(
    {"Body Armour", "Shield", "Helmet", "Gloves", "Boots"}
)


def _armour_matches_defense_style(tags: list[str], defense_style: str) -> bool:
    """Return True if an armour-type base is suitable for the defense style.

    Applies to all armour-class equipment (Body Armour, Helmet, Gloves,
    Boots, and Shields).  Uses the same discriminating tag prefixes as
    :func:`_shield_matches_defense_style`:

    * ``str_armour``         → Strength / armour layer
    * ``dex_armour``         → Dexterity / evasion layer
    * ``int_armour``         → Intelligence / ES layer
    * ``str_dex_armour``     → Str+Dex hybrid (armour+evasion)
    * ``str_int_armour``     → Str+Int hybrid (armour+ES)
    * ``dex_int_armour``     → Dex+Int hybrid (evasion+ES)
    * ``str_dex_int_armour`` → Triple hybrid — allowed for all styles
    * ``ward_armour``        → Ward layer (treated like ES)
    * ``focus``              → Spirit Shields (ES)
    * ``str_shield`` / ``dex_shield`` / ``str_dex_shield`` / ``str_int_shield``
      / ``dex_int_shield``   → Shield-specific variants (same logic)

    Items with no matching discriminating tag (e.g. demigod pieces) pass
    through unconditionally.
    """
    tag_set = set(tags)
    # Triple-hybrid and items without a discriminating tag: always pass
    if "str_dex_int_armour" in tag_set:
        return True

    if defense_style == "life":
        # Armour (Str) layer — prefer pieces that contribute armour rating.
        # Allow Str-only, Str+Dex, and Str+Int bases; exclude pure evasion
        # and pure ES.
        str_tags = {
            "str_armour", "str_dex_armour", "str_int_armour",
            "str_shield", "str_dex_shield", "str_int_shield",
        }
        if tag_set & str_tags:
            return True
        # If the item has no armour discriminator at all we allow it through
        # (e.g. items with only generic 'helmet'/'gloves' tags).
        armour_discriminators = {
            "str_armour", "dex_armour", "int_armour",
            "str_dex_armour", "str_int_armour", "dex_int_armour",
            "str_shield", "dex_shield", "str_dex_shield",
            "str_int_shield", "dex_int_shield",
            "focus", "ward_armour",
        }
        return not bool(tag_set & armour_discriminators)

    if defense_style in ("es", "ci", "lowlife"):
        int_tags = {
            "int_armour", "ward_armour", "focus",
            "str_int_armour", "dex_int_armour",
            "str_int_shield", "dex_int_shield",
        }
        if tag_set & int_tags:
            return True
        armour_discriminators = {
            "str_armour", "dex_armour", "int_armour",
            "str_dex_armour", "str_int_armour", "dex_int_armour",
            "str_shield", "dex_shield", "str_dex_shield",
            "str_int_shield", "dex_int_shield",
            "focus", "ward_armour",
        }
        return not bool(tag_set & armour_discriminators)

    if defense_style == "hybrid":
        # Life + ES: exclude pure evasion pieces.
        pure_evasion = {"dex_armour", "dex_shield"}
        return not bool(tag_set & pure_evasion)

    return True


def _candidates_from_repoe(
    build: BuildData,
    slot: str,
    target_classes: list[str],
    archetype: Archetype,
) -> list[CandidateItem]:
    """Build candidate list from RePoE base items.

    Generates skeleton rare candidates from viable base items.

    Args:
        build: Build data.
        slot: Target slot.
        target_classes: Item classes valid for this slot.
        archetype: Build archetype.

    Returns:
        Candidate items sourced from RePoE base data.
    """
    base_items = load_base_items()
    candidates: list[CandidateItem] = []

    # Pre-compute slot-specific archetype template mods — these represent the
    # best explicit mods a well-crafted rare of this archetype and slot would
    # carry.  Slot-aware mods prevent every slot from producing the same DPS
    # delta (which occurs when a damage mod is injected into a body-armour or
    # shield candidate that wouldn't realistically carry such a mod).
    template_mods = _slot_template_mods(archetype, slot)
    template_relevance = score_mod_relevance(template_mods, archetype)
    # Ensure at least a minimal relevance value for items that get template mods
    template_relevance = max(template_relevance, 0.5)

    # Minimum level requirement for a base to be a sensible upgrade candidate:
    # skip bases that are more than _MIN_BASE_ILVL_DELTA levels below the
    # character so that low-tier items (Shabby Jerkin for a level-99 build)
    # are never suggested.
    min_level_req = max(1, build.level - _MIN_BASE_ILVL_DELTA)

    for _item_id, item in base_items.items():
        if item.item_class not in target_classes:
            continue
        if not item.name:
            continue
        # Skip items that can't exist as regular rares: unique_only bases
        # (demigod trophies, threshold jewels, etc.) and unreleased items.
        if item.release_state and item.release_state not in ("released", "legacy"):
            continue

        # Filter armour-class items to match the build's defensive archetype so
        # that, for example, evasion shields/body armours are not suggested for
        # armour/life builds and Spirit Shields are not suggested for life
        # builds.  All armour-type item classes (Body Armour, Shield, Helmet,
        # Gloves, Boots) are covered by the shared discriminator function.
        if item.item_class in _ARMOUR_CLASSES and not _armour_matches_defense_style(
            item.tags, archetype.defense_style
        ):
            continue

        level_req = int(item.requirements.get("level", 0) or 0)

        # Exclude bases whose level requirement is too low for the character.
        # level_req == 0 means the base has no level requirement (white flasks,
        # low-level jewels, etc.) — allow these through unconditionally.
        if level_req > 0 and level_req < min_level_req:
            continue
        attr_req = ItemAttrReq(**{
            "str": int(item.requirements.get("str", 0) or 0),
            "dex": int(item.requirements.get("dex", 0) or 0),
            "int": int(item.requirements.get("int", 0) or 0),
        })

        # Use archetype template mods for simulation (represents the best
        # explicit mods this base type could carry for the archetype).
        # Include any implicit mods the base has as additional context.
        implicit_mods = list(item.implicit_mods)
        implicit_relevance = score_mod_relevance(implicit_mods, archetype)
        # If the item has archetype-relevant implicits, score them extra.
        relevance = max(template_relevance, implicit_relevance)
        key_mods = template_mods[:]

        candidates.append(
            CandidateItem(
                name="",
                base_name=item.name,
                slot=slot,
                rarity="rare",
                level_req=level_req,
                attr_req=attr_req,
                key_mods=key_mods,
                price_divine=None,
                price_confidence="low",
                relevance_score=relevance,
                source="repoe",
            )
        )

    return candidates


def _passes_hard_constraints(
    build: BuildData,
    candidate: CandidateItem,
) -> bool:
    """Return True if the candidate passes all hard character constraints.

    Hard constraints:
    * Level requirement ≤ character level.
    * Attribute requirements ≤ character attributes.

    Borderline cases that are within tolerance are NOT excluded here;
    they show up as warnings in :func:`validate_constraints`.

    Args:
        build: Build data.
        candidate: Candidate item.

    Returns:
        True if the candidate is equippable.
    """
    if candidate.level_req > build.level:
        return False

    attrs = build.attrs
    req = candidate.attr_req
    if req.str > 0 and attrs.str < req.str:
        return False
    if req.dex > 0 and attrs.dex < req.dex:
        return False
    if req.int_ > 0 and attrs.int_ < req.int_:
        return False

    return True


def _parse_attr_req(price_info: dict[str, Any]) -> ItemAttrReq:
    """Extract attribute requirements from a poe.ninja price entry.

    poe.ninja doesn't always provide attribute requirements in the
    ItemOverview endpoint; defaults to 0 when absent.

    Args:
        price_info: Price entry dict from poe.ninja.

    Returns:
        Parsed ItemAttrReq.
    """
    return ItemAttrReq(**{
        "str": int(price_info.get("strReq", 0) or 0),
        "dex": int(price_info.get("dexReq", 0) or 0),
        "int": int(price_info.get("intReq", 0) or 0),
    })


# ---------------------------------------------------------------------------
# Internal helpers — gem candidate generation
# ---------------------------------------------------------------------------


def _generate_support_candidates(
    build: BuildData,
    main_skill_tags: list[str],
    equipped_names_lower: set[str],
    archetype: Archetype,
    prices: dict[str, Any],
) -> list[CandidateGem]:
    """Generate support gem candidates for a skill group.

    Finds all support gems in RePoE that share at least one tag with the
    main skill and aren't already equipped.

    Args:
        build: Build data (for level / attr constraints).
        main_skill_tags: Tags of the main active skill gem.
        equipped_names_lower: Lower-case names of already-equipped gems.
        archetype: Build archetype.
        prices: poe.ninja price dict.

    Returns:
        List of up to 20 support gem candidates.
    """
    gems_data = load_gems()
    candidates: list[CandidateGem] = []
    tags_set = set(main_skill_tags)

    for _gem_id, gem in gems_data.items():
        if not gem.is_support:
            continue
        if not gem.base_item:
            continue
        display = gem.base_item.display_name
        if not display:
            continue
        if gemstate := gem.base_item.release_state:
            if gemstate not in ("released", "legacy"):
                continue

        # Skip already-equipped gems
        if display.lower() in equipped_names_lower:
            continue

        # Tag match: support gem must share at least one tag with main skill
        # (or no tag overlap required as a fallback when tags_set is empty)
        gem_tags = set(gem.tags or [])
        if tags_set and not tags_set.intersection(gem_tags):
            continue

        price = _lookup_gem_price(display, prices)

        candidates.append(
            CandidateGem(
                name=display,
                level_req=1,  # gems have level 1 as base req
                attr_req=ItemAttrReq(),
                tags=gem.tags or [],
                is_support=True,
                price_divine=price,
            )
        )

    return candidates[:20]


def _generate_skill_alternatives(
    build: BuildData,
    archetype: Archetype,
    equipped_names_lower: set[str],
    prices: dict[str, Any],
    max_alternatives: int = 5,
) -> list[CandidateGem]:
    """Generate alternative active skill suggestions for the archetype.

    Scans RePoE active skill gems for those whose tags align with the
    archetype's damage type and playstyle.

    Args:
        build: Build data.
        archetype: Detected archetype.
        equipped_names_lower: Lower-case names of already-equipped gems.
        prices: poe.ninja price dict.
        max_alternatives: Maximum number of suggestions to return.

    Returns:
        List of up to *max_alternatives* alternative skill candidates.
    """
    gems_data = load_gems()
    damage_tag_map: dict[str, list[str]] = {
        "fire": ["fire", "spell", "projectile"],
        "cold": ["cold", "spell", "projectile"],
        "lightning": ["lightning", "spell", "projectile"],
        "chaos": ["chaos", "spell"],
        "physical": ["attack", "melee"],
        "minion": ["minion", "spell"],
        "totem": ["totem"],
        "trap": ["trap", "mine"],
    }
    desired_tags = set(
        damage_tag_map.get(archetype.damage_type, ["attack"])
    )

    alternatives: list[tuple[int, CandidateGem]] = []

    for _gem_id, gem in gems_data.items():
        if gem.is_support:
            continue
        if not gem.base_item:
            continue
        display = gem.base_item.display_name
        if not display:
            continue
        if gem.base_item.release_state not in ("released", "legacy"):
            continue
        if display.lower() in equipped_names_lower:
            continue

        gem_tags = set(gem.tags or [])
        overlap = len(desired_tags.intersection(gem_tags))
        if overlap == 0:
            continue

        price = _lookup_gem_price(display, prices)
        alternatives.append((
            overlap,
            CandidateGem(
                name=display,
                level_req=1,
                attr_req=ItemAttrReq(),
                tags=gem.tags or [],
                is_support=False,
                price_divine=price,
            ),
        ))

    # Sort by tag-overlap descending, take top N
    alternatives.sort(key=lambda t: t[0], reverse=True)
    return [gem for _, gem in alternatives[:max_alternatives]]


def _lookup_gem_price(
    gem_name: str,
    prices: dict[str, Any],
) -> float | None:
    """Look up a gem's divine price from the poe.ninja price dict.

    Args:
        gem_name: Gem display name.
        prices: poe.ninja price dict.

    Returns:
        Divine price as float, or None if not found.
    """
    entry = prices.get(gem_name)
    if not entry or not isinstance(entry, dict):
        return None
    val = float(entry.get("divineValue", 0) or 0)
    return val if val > 0 else None

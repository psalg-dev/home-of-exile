"""Archetype detection for Path of Exile builds.

Classifies a build into a primary damage type, defensive layer, and
playstyle based on equipped gems, passive tree keystones, and stats.
The resulting :class:`~app.models.candidate.Archetype` is used by the
candidate pipeline to score and rank upgrade candidates.

Design notes:
- Multiple signal types are combined to improve accuracy on hybrid builds.
- Each detection function returns the best single-value classification.
  Future work can extend this to multi-label archetypes.
"""

from __future__ import annotations

import re

from app.models.candidate import Archetype, BuildData

# ---------------------------------------------------------------------------
# Gem / skill keyword maps
# ---------------------------------------------------------------------------

# Lower-cased skill name substrings that imply a damage type.
_DAMAGE_KEYWORDS: dict[str, list[str]] = {
    "fire": [
        "fireball", "flameblast", "incinerate", "flame surge",
        "burning arrow", "ignite", "magma orb", "cremation",
        "righteous fire", "fire trap", "flame dash", "molten strike",
        "explosive arrow", "combustion", "infernal blow",
        "firestorm", "volcanic fissure", "scalding rains",
        "immolate", "added fire",
    ],
    "cold": [
        "ice nova", "freezing pulse", "frostbolt", "cold snap",
        "vortex", "frost blades", "glacial hammer", "arctic armour",
        "ice spear", "arctic breath", "cyclone of tumult",
        "added cold", "bonechill", "hypothermia",
        "winter orb", "cold skills", "ice crash",
    ],
    "lightning": [
        "arc", "ball lightning", "storm call", "lightning strike",
        "volt", "wild strike", "discharge", "shock nova",
        "added lightning", "stormblast", "herald of thunder",
        "spark", "conductivity", "lightning arrow", "power siphon",
        "tornado shot", "galvanic arrow", "charged", "electrocute",
    ],
    "chaos": [
        "essence drain", "contagion", "blight", "dark pact",
        "vaal blight", "soulrend", "power siphon chaos",
        "withering", "caustic arrow", "toxic rain", "wither",
        "degen", "chaos res", "unearth",
    ],
    "physical": [
        "heavy strike", "double strike", "cleave", "lacerate",
        "sunder", "ground slam", "shockwave", "bladestorm",
        "melee physical", "pure physical", "fortify",
        "viper strike", "earthquake", "perforate",
        "ambush", "puncture",
    ],
    "minion": [
        "raise zombie", "raise spectre", "summon skeleton",
        "summon raging spirit", "summon golem", "summon",
        "animate weapon", "animate guardian", "minion",
        "necromancer", "lich",
    ],
    "totem": [
        "totem", "hierophant", "shockwave totem",
        "ancestral warchief", "ballista", "flame totem",
        "holy flame totem",
    ],
    "trap": [
        "trap", "mine", "seismic trap", "lightning spire trap",
        "cluster trap", "sabo", "saboteur",
    ],
}

# Character class / ascendancy names associated with damage types.
_CLASS_DAMAGE_HINTS: dict[str, str] = {
    "necromancer": "minion",
    "elementalist": "fire",
    "occultist": "chaos",
    "saboteur": "trap",
    "pathfinder": "chaos",
    "chieftain": "fire",
    "juggernaut": "physical",
    "gladiator": "physical",
    "slayer": "physical",
    "assassin": "physical",
    "deadeye": "lightning",
    "raider": "physical",
    "berserker": "physical",
    "champion": "physical",
    "guardian": "minion",
    "hierophant": "totem",
    "inquisitor": "fire",
    "trickster": "chaos",
    "arakaali": "chaos",
    "shaper of storms": "lightning",
    "shaper of winter": "cold",
    "shaper of flames": "fire",
}

# ---------------------------------------------------------------------------
# Playstyle keyword maps
# ---------------------------------------------------------------------------

_MELEE_KEYWORDS: list[str] = [
    "heavy strike", "double strike", "cleave", "lacerate", "sunder",
    "ground slam", "shockwave", "bladestorm", "blade flurry",
    "blade vortex", "reave", "flicker", "cyclone", "molten strike",
    "glacial hammer", "frost blades", "static strike", "lightning strike",
    "viper strike", "earthquake", "perforate",
]

_RANGED_KEYWORDS: list[str] = [
    "arrow", "bow", "barrage", "deadeye", "split shot",
    "chain", "tornado shot", "rain of arrows", "burning arrow",
    "caustic arrow", "toxic rain", "galvanic",
    "power siphon", "kinetic blast", "ethereal knives",
]

_CASTER_KEYWORDS: list[str] = [
    "ball lightning", "arc", "fireball", "flameblast", "incinerate",
    "ice nova", "freezing pulse", "frostbolt", "spark", "shock nova",
    "essence drain", "blight", "soulrend", "cremation", "vortex",
    "cold snap", "discharge", "righteous fire", "magma orb",
    "storm call", "winter orb", "dark pact",
]

_SUMMONER_KEYWORDS: list[str] = [
    "raise zombie", "raise spectre", "summon skeleton", "summon raging",
    "summon golem", "animate weapon", "animate guardian", "minion",
    "summon", "necromancer",
]

# ---------------------------------------------------------------------------
# Passive tree keystones associated with defence / damage
# ---------------------------------------------------------------------------

# Node IDs that represent well-known keystones (numbers from the PoE passive
# tree; a curated subset is sufficient for detection purposes).
_CI_KEYSTONES: frozenset[int] = frozenset({
    # Chaos Inoculation (multiple versions across different tree layouts)
    48768, 61462, 44683,
})

_LOWLIFE_KEYSTONES: frozenset[int] = frozenset({
    # Blood Magic (proxy for low-life setups) and Pain Attunement
    34098, 15474,
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_archetype(build: BuildData) -> Archetype:
    """Classify a build into an Archetype.

    Uses three independent classification passes — one per Archetype
    dimension — then combines them.

    Args:
        build: Fully parsed :class:`~app.models.candidate.BuildData`.

    Returns:
        An :class:`~app.models.candidate.Archetype` with ``damage_type``,
        ``defense_style``, and ``playstyle`` populated.
    """
    damage_type = _detect_damage_type(build)
    defense_style = _detect_defense_style(build)
    playstyle = _detect_playstyle(build)

    return Archetype(
        damage_type=damage_type,
        defense_style=defense_style,
        playstyle=playstyle,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _gem_names_lower(build: BuildData) -> list[str]:
    """Return all gem display names in lower-case."""
    return [name.lower() for name in build.all_gem_names]


def _keyword_score(text: str, keywords: list[str]) -> int:
    """Count how many keywords appear as substrings in *text*."""
    return sum(1 for kw in keywords if kw in text)


def _detect_damage_type(build: BuildData) -> str:
    """Determine the primary damage type for the build.

    Scoring strategy:
    1. Sum keyword hits across all active gem names.
    2. Add a class/ascendancy hint if available.
    3. Return the damage type with the highest score; default to
       'physical' when ambiguous.

    Args:
        build: Parsed build data.

    Returns:
        One of: physical, fire, cold, lightning, chaos, minion, totem, trap.
    """
    gem_text = " ".join(_gem_names_lower(build))
    main_skill_lower = build.main_skill.lower()

    # Include the ascendancy name as a text signal.
    asc_lower = build.ascendancy.lower()

    scores: dict[str, int] = dict.fromkeys(_DAMAGE_KEYWORDS, 0)

    for damage_type, keywords in _DAMAGE_KEYWORDS.items():
        scores[damage_type] += _keyword_score(gem_text, keywords)
        scores[damage_type] += _keyword_score(main_skill_lower, keywords) * 2

    # Class / ascendancy hints
    for class_kw, hint_type in _CLASS_DAMAGE_HINTS.items():
        if class_kw in asc_lower or class_kw in build.char_class.lower():
            scores[hint_type] += 3

    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "physical"


def _detect_defense_style(build: BuildData) -> str:
    """Determine the defensive layer of the build.

    Priority order:
    1. Chaos Inoculation keystone → 'ci' (life == 1)
    2. Life == 1 heuristic → 'ci'
    3. Both life and ES meaningful → 'hybrid'
    4. ES >> life → 'es'
    5. Low-life threshold → 'lowlife' (life < 35% of ES)
    6. Default → 'life'

    Args:
        build: Parsed build data.

    Returns:
        One of: ci, lowlife, es, hybrid, life.
    """
    life = build.stats.life
    es = build.stats.energy_shield

    # Chaos Inoculation: life is reduced to 1
    if life <= 1:
        return "ci"

    # Low-life: life is less than 35% of ES (common low-life threshold)
    if es > 0 and life < es * 0.35:
        return "lowlife"

    # ES-based: ES is at least 3x life
    if es >= life * 3 and es > 500:
        return "es"

    # Hybrid: both stats are significant (each ≥ 1 k)
    if life >= 1000 and es >= 1000:
        return "hybrid"

    # Passive tree keystones: CI or low-life markers
    tree_nodes = set(build.passive_tree)
    if tree_nodes & _CI_KEYSTONES:
        return "ci"
    if tree_nodes & _LOWLIFE_KEYSTONES:
        return "lowlife"

    return "life"


def _detect_playstyle(build: BuildData) -> str:
    """Determine the playstyle of the build.

    Order of precedence (highest wins):
    1. Summoner — any summoner gem present
    2. Melee — melee skill gem present and no dominant ranged signal
    3. Ranged — bow / projectile skill detected
    4. Caster — spell gem as primary skill

    Args:
        build: Parsed build data.

    Returns:
        One of: melee, ranged, caster, summoner.
    """
    gem_text = " ".join(_gem_names_lower(build))
    main_skill_lower = build.main_skill.lower()
    combined = gem_text + " " + main_skill_lower

    summoner_score = _keyword_score(combined, _SUMMONER_KEYWORDS)
    melee_score = _keyword_score(combined, _MELEE_KEYWORDS)
    ranged_score = _keyword_score(combined, _RANGED_KEYWORDS)
    caster_score = _keyword_score(combined, _CASTER_KEYWORDS)

    # Summoner takes top priority
    if summoner_score >= 2:
        return "summoner"

    scores = {
        "melee": melee_score,
        "ranged": ranged_score,
        "caster": caster_score,
        "summoner": summoner_score,
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "caster"


# ---------------------------------------------------------------------------
# Archetype-driven mod priority keywords
# ---------------------------------------------------------------------------


def archetype_mod_keywords(archetype: Archetype) -> list[str]:
    """Return a ranked list of mod keywords relevant to an archetype.

    These keywords are matched against item mod lines to compute a
    relevance score during candidate generation.

    Args:
        archetype: The detected build archetype.

    Returns:
        List of lower-case keyword strings (order = priority).
    """
    keywords: list[str] = []

    # Defense-style keywords
    if archetype.defense_style in ("ci", "es", "lowlife"):
        keywords += ["energy shield", "maximum energy shield", "es"]
    elif archetype.defense_style == "hybrid":
        keywords += [
            "maximum life", "life", "energy shield", "maximum energy shield",
        ]
    else:  # life
        keywords += ["maximum life", "life", "life regeneration"]

    # Resistance keywords (always relevant)
    keywords += [
        "fire resistance", "cold resistance", "lightning resistance",
        "resistances", "all resistances",
    ]

    # Damage-type keywords
    damage_kw_map: dict[str, list[str]] = {
        "fire": [
            "fire damage", "burning damage", "ignite",
            "fire spell damage", "fire over time",
        ],
        "cold": [
            "cold damage", "freeze", "chill", "cold spell damage",
        ],
        "lightning": [
            "lightning damage", "shock", "lightning spell damage",
        ],
        "chaos": [
            "chaos damage", "chaos over time", "poison",
        ],
        "physical": [
            "physical damage", "attack damage", "melee damage",
        ],
        "minion": [
            "minion damage", "minion life", "minion speed",
            "summon", "undead",
        ],
        "totem": [
            "totem damage", "totem life", "placed", "totem placement",
        ],
        "trap": [
            "trap damage", "mine damage", "trap trigger",
        ],
    }
    keywords += damage_kw_map.get(archetype.damage_type, [])

    # Playstyle-specific keywords
    playstyle_kw_map: dict[str, list[str]] = {
        "melee": ["attack speed", "movement speed", "armour", "evasion"],
        "ranged": ["attack speed", "projectile speed", "accuracy"],
        "caster": ["cast speed", "spell damage", "crit chance", "crit multi"],
        "summoner": ["minion", "aura effect", "reduced mana"],
    }
    keywords += playstyle_kw_map.get(archetype.playstyle, [])

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw.lower())
    return unique


def score_mod_relevance(
    mods: list[str],
    archetype: Archetype,
) -> float:
    """Score item mods for relevance to an archetype.

    Counts keyword hits across all mod lines; normalises to [0, 1] based
    on the number of keywords checked and the number of mods.  Returns 0.0
    when there are no mods or keywords.

    Args:
        mods: List of item mod text lines.
        archetype: Build archetype for keyword selection.

    Returns:
        Relevance score in [0.0, 1.0].
    """
    keywords = archetype_mod_keywords(archetype)
    if not mods or not keywords:
        return 0.0

    mod_text = " ".join(m.lower() for m in mods)
    hits = sum(1 for kw in keywords if kw in mod_text)

    # Normalise: expect ~3 relevant keywords per item; cap at 1.0
    return min(hits / 3.0, 1.0)


def extract_key_mods(
    mods: list[str],
    archetype: Archetype,
    max_mods: int = 5,
) -> list[str]:
    """Return the most archetype-relevant mod lines from an item.

    Filters *mods* to those containing at least one archetype keyword,
    then returns up to *max_mods* results.

    Args:
        mods: Raw mod text lines.
        archetype: Build archetype for keyword selection.
        max_mods: Maximum number of mods to return.

    Returns:
        Filtered list of relevant mod strings.
    """
    keywords = archetype_mod_keywords(archetype)
    relevant: list[str] = []
    for mod in mods:
        mod_lower = mod.lower()
        if any(kw in mod_lower for kw in keywords):
            relevant.append(mod)
        if len(relevant) >= max_mods:
            break
    return relevant


def _normalise_mod_line(raw: str) -> str:
    """Replace numeric values in a mod line with '#' for matching.

    E.g. '+45 to maximum Life' → '+# to maximum Life'.

    Used internally to normalise mods before keyword matching.

    Args:
        raw: Raw mod text.

    Returns:
        Normalised mod string.
    """
    return re.sub(r"\d+(\.\d+)?", "#", raw)

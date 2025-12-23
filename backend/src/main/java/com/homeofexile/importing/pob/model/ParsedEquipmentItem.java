package com.homeofexile.importing.pob.model;

import java.util.List;

public record ParsedEquipmentItem(
    String slot,
    String name,
    String rarity,
    String raw,
    List<String> implicitMods,
    List<String> prefixMods,
    List<String> suffixMods,
    List<String> explicitMods
) {}

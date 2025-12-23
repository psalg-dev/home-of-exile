package com.homeofexile.importing.pob.dto;

import java.util.List;

public record EquipmentItemDto(
    String slot,
    String name,
    String rarity,
    String raw,
    List<String> implicitMods,
    List<String> prefixMods,
    List<String> suffixMods,
    List<String> explicitMods
) {}

package com.homeofexile.importing.pob.model;

public record ParsedEquipmentItem(
    String slot,
    String name,
    String rarity,
    String raw
) {}

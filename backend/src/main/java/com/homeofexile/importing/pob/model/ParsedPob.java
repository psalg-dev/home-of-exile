package com.homeofexile.importing.pob.model;

import java.util.List;

public record ParsedPob(
    ParsedCharacter character,
    ParsedMainSkill mainSkill,
    List<ParsedEquipmentItem> equipment,
    List<String> warnings,
    String xmlVersion
) {}

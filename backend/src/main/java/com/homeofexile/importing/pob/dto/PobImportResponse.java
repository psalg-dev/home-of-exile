package com.homeofexile.importing.pob.dto;

import java.util.List;

public record PobImportResponse(
    CharacterDto character,
    MainSkillDto mainSkill,
    List<EquipmentItemDto> equipment,
    RawMetaDto raw
) {}

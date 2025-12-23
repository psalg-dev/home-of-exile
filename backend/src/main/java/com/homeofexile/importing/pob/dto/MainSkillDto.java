package com.homeofexile.importing.pob.dto;

import java.util.List;

public record MainSkillDto(
    String name,
    String group,
    List<String> supportGems,
    String confidence
) {}

package com.homeofexile.importing.pob.model;

import java.util.List;

public record ParsedMainSkill(
    String name,
    String group,
    List<String> supportGems,
    Confidence confidence
) {}

package com.homeofexile.importing.pob.model;

public record ParsedCharacter(
    String name,
    String clazz,
    String ascendancy,
    Integer level
) {}

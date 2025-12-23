package com.homeofexile.importing.pob.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record CharacterDto(
    String name,
    @JsonProperty("class") String clazz,
    String ascendancy,
    Integer level
) {}

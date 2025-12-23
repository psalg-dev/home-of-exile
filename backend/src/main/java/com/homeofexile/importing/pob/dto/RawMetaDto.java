package com.homeofexile.importing.pob.dto;

import java.util.List;

public record RawMetaDto(
    String xmlVersion,
    List<String> warnings,
    String source
) {}

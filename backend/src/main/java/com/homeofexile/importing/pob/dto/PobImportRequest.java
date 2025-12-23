package com.homeofexile.importing.pob.dto;

import jakarta.validation.constraints.NotBlank;

public record PobImportRequest(
    @NotBlank(message = "exportCode is required") String exportCode
) {}

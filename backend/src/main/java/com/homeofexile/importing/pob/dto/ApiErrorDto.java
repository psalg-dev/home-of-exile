package com.homeofexile.importing.pob.dto;

import java.util.List;

public record ApiErrorDto(
    String code,
    String message,
    List<String> details
) {}

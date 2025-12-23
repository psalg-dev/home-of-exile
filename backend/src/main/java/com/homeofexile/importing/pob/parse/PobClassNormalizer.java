package com.homeofexile.importing.pob.parse;

import java.util.Locale;
import java.util.Map;
import java.util.Optional;

public class PobClassNormalizer {
  private static final Map<String, String> MAP = Map.of(
      "witch", "Witch",
      "templar", "Templar",
      "shadow", "Shadow",
      "duelist", "Duelist",
      "marauder", "Marauder",
      "ranger", "Ranger",
      "scion", "Scion"
  );

  public Optional<String> normalize(String raw) {
    if (raw == null || raw.isBlank()) {
      return Optional.empty();
    }
    String v = raw.trim().toLowerCase(Locale.ROOT);
    return Optional.ofNullable(MAP.get(v));
  }
}

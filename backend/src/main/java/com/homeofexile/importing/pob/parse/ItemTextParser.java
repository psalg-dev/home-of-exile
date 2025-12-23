package com.homeofexile.importing.pob.parse;

import java.util.Locale;
import java.util.Optional;

public class ItemTextParser {

  public Optional<String> parseRarity(String raw) {
    if (raw == null || raw.isBlank()) {
      return Optional.empty();
    }
    for (String line : raw.replace("\r\n", "\n").split("\n")) {
      String trimmed = line.trim();
      if (trimmed.toLowerCase(Locale.ROOT).startsWith("rarity:")) {
        String value = trimmed.substring("rarity:".length()).trim();
        return value.isBlank() ? Optional.empty() : Optional.of(value.toUpperCase(Locale.ROOT));
      }
    }
    return Optional.empty();
  }

  public Optional<String> parseName(String raw) {
    if (raw == null || raw.isBlank()) {
      return Optional.empty();
    }

    String[] lines = raw.replace("\r\n", "\n").split("\n");
    for (int i = 0; i < lines.length; i++) {
      String line = lines[i].trim();
      if (line.toLowerCase(Locale.ROOT).startsWith("rarity:")) {
        String n1 = nextNonBlank(lines, i + 1).orElse(null);
        String n2 = nextNonBlank(lines, i + 2).orElse(null);
        if (n2 != null) {
          return Optional.of(n1 + " " + n2);
        }
        return Optional.ofNullable(n1);
      }
    }

    return nextNonBlank(lines, 0);
  }

  private Optional<String> nextNonBlank(String[] lines, int startIndex) {
    for (int i = startIndex; i < lines.length; i++) {
      String t = lines[i] == null ? "" : lines[i].trim();
      if (!t.isBlank()) {
        return Optional.of(t);
      }
    }
    return Optional.empty();
  }
}

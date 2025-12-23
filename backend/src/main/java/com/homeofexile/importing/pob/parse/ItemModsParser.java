package com.homeofexile.importing.pob.parse;

import com.homeofexile.importing.pob.xml.TextSupport;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class ItemModsParser {

  public ItemMods parse(String raw) {
    if (raw == null || raw.isBlank()) {
      return ItemMods.empty();
    }

    String normalized = raw.replace("\r\n", "\n");
    String[] lines = normalized.split("\n");

    List<String> implicit = new ArrayList<>();
    List<String> explicit = new ArrayList<>();
    List<String> prefixes = new ArrayList<>();
    List<String> suffixes = new ArrayList<>();

    // Split by PoE item text separators.
    List<List<String>> sections = splitSections(lines);

    // 1) Parse implicits from any section that contains "Implicits: N".
    for (List<String> section : sections) {
      int implicitsIndex = indexOfImplicitsHeader(section);
      if (implicitsIndex < 0) {
        continue;
      }

      int count = parseImplicitsCount(section.get(implicitsIndex));
      for (int i = implicitsIndex + 1; i < section.size(); i++) {
        String line = normalizeModLine(section.get(i));
        if (line == null) {
          continue;
        }
        implicit.add(line);
        if (count > 0 && implicit.size() >= count) {
          break;
        }
      }
    }

    // 2) Parse explicit mods: prefer the last section (where PoE usually prints mods),
    // but fall back to scanning all sections if needed.
    List<String> modSection = sections.isEmpty() ? List.of() : sections.get(sections.size() - 1);
    addExplicitFromSection(modSection, implicit, prefixes, suffixes, explicit);

    if (explicit.isEmpty() && prefixes.isEmpty() && suffixes.isEmpty()) {
      for (List<String> section : sections) {
        addExplicitFromSection(section, implicit, prefixes, suffixes, explicit);
      }
    }

    return new ItemMods(
        List.copyOf(implicit),
        List.copyOf(prefixes),
        List.copyOf(suffixes),
        List.copyOf(explicit)
    );
  }

  private static void addExplicitFromSection(
      List<String> section,
      List<String> implicit,
      List<String> prefixes,
      List<String> suffixes,
      List<String> explicit
  ) {
    for (String rawLine : section) {
      String line = normalizeModLine(rawLine);
      if (line == null) {
        continue;
      }

      if (isMetadataLine(line)) {
        continue;
      }

      // Skip implicits header line itself.
      if (line.toLowerCase(Locale.ROOT).startsWith("implicits:")) {
        continue;
      }

      // Avoid duplicating implicit lines if the section includes them.
      if (implicit.contains(line)) {
        continue;
      }

      // Best-effort prefix/suffix extraction if the text includes markers.
      AffixLine affix = splitAffix(line);
      if (affix != null) {
        if (affix.kind == AffixKind.PREFIX) {
          prefixes.add(affix.value);
        } else {
          suffixes.add(affix.value);
        }
        explicit.add(affix.value);
        continue;
      }

      explicit.add(line);
    }
  }

  private static List<List<String>> splitSections(String[] lines) {
    List<List<String>> sections = new ArrayList<>();
    List<String> current = new ArrayList<>();

    for (String line : lines) {
      String trimmed = line == null ? "" : line.trim();
      if (trimmed.equals("--------")) {
        if (!current.isEmpty()) {
          sections.add(current);
        }
        current = new ArrayList<>();
        continue;
      }
      current.add(trimmed);
    }

    if (!current.isEmpty()) {
      sections.add(current);
    }

    // Drop the header section (item class/rarity/name/base) if we have more than one.
    if (sections.size() > 1) {
      return sections.subList(1, sections.size());
    }

    // Some PoB exports omit the "--------" separators. In that case, the header
    // (rarity + name/base lines) is in the same section as the mods.
    if (sections.size() == 1) {
      List<String> stripped = stripHeaderWhenNoSeparators(sections.get(0));
      if (!stripped.isEmpty()) {
        return List.of(stripped);
      }
    }

    return sections;
  }

  private static List<String> stripHeaderWhenNoSeparators(List<String> section) {
    if (section == null || section.isEmpty()) {
      return List.of();
    }

    int rarityIndex = -1;
    for (int i = 0; i < section.size(); i++) {
      String t = section.get(i) == null ? "" : section.get(i).trim();
      if (t.toLowerCase(Locale.ROOT).startsWith("rarity:")) {
        rarityIndex = i;
        break;
      }
    }
    if (rarityIndex < 0) {
      return section;
    }

    int idx = rarityIndex + 1;
    int skippedNameLines = 0;
    while (idx < section.size() && skippedNameLines < 3) {
      String line = section.get(idx) == null ? "" : section.get(idx).trim();
      if (line.isBlank()) {
        idx++;
        continue;
      }

      String lower = line.toLowerCase(Locale.ROOT);
      if (lower.equals("--------")
          || lower.startsWith("requirements:")
          || lower.startsWith("item level:")
          || lower.startsWith("implicits:")
          || lower.startsWith("sockets:")) {
        break;
      }

      // Stop stripping when the line already looks like a mod.
      if (line.contains(":") || line.matches(".*\\d.*") || line.contains("+") || line.contains("%")) {
        break;
      }

      // Otherwise treat as name/base header line.
      skippedNameLines++;
      idx++;
    }

    if (idx >= section.size()) {
      return List.of();
    }

    return section.subList(idx, section.size());
  }

  private static int indexOfImplicitsHeader(List<String> section) {
    for (int i = 0; i < section.size(); i++) {
      String t = section.get(i) == null ? "" : section.get(i).trim();
      if (t.toLowerCase(Locale.ROOT).startsWith("implicits:")) {
        return i;
      }
    }
    return -1;
  }

  private static int parseImplicitsCount(String implicitsLine) {
    if (TextSupport.isBlank(implicitsLine)) {
      return -1;
    }
    String[] parts = implicitsLine.split(":", 2);
    if (parts.length < 2) {
      return -1;
    }
    String right = parts[1].trim();
    try {
      return Integer.parseInt(right);
    } catch (NumberFormatException ignored) {
      return -1;
    }
  }

  private static String normalizeModLine(String rawLine) {
    if (rawLine == null) {
      return null;
    }
    String t = rawLine.trim();
    if (t.isBlank()) {
      return null;
    }

    // Remove PoB/PoE tag braces like "{crafted}" while preserving the mod text.
    // Example: "+# to maximum Life {crafted}".
    t = t.replaceAll("\\s*\\{[^}]+}\\s*", " ").trim();

    return t.isBlank() ? null : t;
  }

  private static boolean isMetadataLine(String line) {
    String lower = line.toLowerCase(Locale.ROOT);

    // Common non-mod lines in PoE item text.
    return lower.startsWith("item class:")
        || lower.startsWith("rarity:")
        || lower.startsWith("quality:")
        || lower.startsWith("armour:")
        || lower.startsWith("evasion rating:")
        || lower.startsWith("energy shield:")
        || lower.startsWith("ward:")
        || lower.startsWith("physical damage:")
        || lower.startsWith("elemental damage:")
        || lower.startsWith("critical strike chance:")
        || lower.startsWith("attacks per second:")
        || lower.startsWith("weapon range:")
        || lower.startsWith("requirements:")
        || lower.equals("sockets:")
        || lower.startsWith("sockets:")
        || lower.startsWith("item level:")
        || lower.startsWith("level:")
        || lower.startsWith("str:")
        || lower.startsWith("dex:")
        || lower.startsWith("int:")
          || lower.startsWith("unique id:")
        || lower.startsWith("note:");
  }

  private static AffixLine splitAffix(String line) {
    String lower = line.toLowerCase(Locale.ROOT);

    // "Prefix: +# to maximum Life" or "Suffix: +#% to Fire Resistance"
    if (lower.startsWith("prefix:") || lower.startsWith("prefix :")) {
      String value = line.substring(line.indexOf(':') + 1).trim();
      return TextSupport.isBlank(value) ? null : new AffixLine(AffixKind.PREFIX, value);
    }
    if (lower.startsWith("suffix:") || lower.startsWith("suffix :")) {
      String value = line.substring(line.indexOf(':') + 1).trim();
      return TextSupport.isBlank(value) ? null : new AffixLine(AffixKind.SUFFIX, value);
    }

    // "... (Prefix)" / "... (Suffix)"
    if (lower.endsWith("(prefix)")) {
      String value = line.substring(0, line.length() - "(Prefix)".length()).trim();
      return TextSupport.isBlank(value) ? null : new AffixLine(AffixKind.PREFIX, value);
    }
    if (lower.endsWith("(suffix)")) {
      String value = line.substring(0, line.length() - "(Suffix)".length()).trim();
      return TextSupport.isBlank(value) ? null : new AffixLine(AffixKind.SUFFIX, value);
    }

    return null;
  }

  private enum AffixKind {
    PREFIX,
    SUFFIX
  }

  private record AffixLine(AffixKind kind, String value) {}

  public record ItemMods(
      List<String> implicitMods,
      List<String> prefixMods,
      List<String> suffixMods,
      List<String> explicitMods
  ) {
    static ItemMods empty() {
      return new ItemMods(List.of(), List.of(), List.of(), List.of());
    }
  }
}

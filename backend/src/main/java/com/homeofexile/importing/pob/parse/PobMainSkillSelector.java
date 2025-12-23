package com.homeofexile.importing.pob.parse;

import com.homeofexile.importing.pob.model.Confidence;
import com.homeofexile.importing.pob.model.ParsedMainSkill;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

import static com.homeofexile.importing.pob.parse.SkillModels.Gem;
import static com.homeofexile.importing.pob.parse.SkillModels.SkillGroup;

public class PobMainSkillSelector {

  public Selection select(List<SkillGroup> groups) {
    if (groups == null || groups.isEmpty()) {
      return new Selection(new ParsedMainSkill(null, null, List.of(), Confidence.LOW), List.of("main skill not found"));
    }

    Comparator<SkillGroup> groupComparator = Comparator
      .comparingInt(PobMainSkillSelector::maxSupportCountInGroup)
      .reversed()
      .thenComparing(Comparator.comparingInt((SkillGroup g) -> g.gems().size()).reversed())
      .thenComparing(g -> g.enabled() ? 0 : 1)
      .thenComparingInt(SkillGroup::id);

    List<SkillGroup> sortedGroups = groups.stream()
      .sorted(groupComparator)
      .toList();

    SkillGroup best = sortedGroups.get(0);

    List<String> warnings = new java.util.ArrayList<>();
    if (sortedGroups.size() > 1) {
      SkillGroup second = sortedGroups.get(1);
      boolean sameSupports = maxSupportCountInGroup(second) == maxSupportCountInGroup(best);
      boolean sameGemCount = second.gems().size() == best.gems().size();
      boolean sameEnabled = second.enabled() == best.enabled();

      if (sameSupports && sameGemCount && sameEnabled) {
        warnings.add("main skill ambiguous; chose group " + best.id());
      } else if (sameSupports && sameGemCount) {
        warnings.add("main skill tie; chose enabled group " + best.id());
      } else if (sameSupports) {
        warnings.add("main skill tie on linked supports; chose group " + best.id());
      }
    }

    Gem main = selectBestActiveGem(best).orElseGet(() -> best.gems().get(0));
    List<String> supports = best.gems().stream()
        .filter(Gem::support)
        .map(Gem::name)
        .filter(Objects::nonNull)
        .toList();

    Confidence confidence = Confidence.HIGH;
    if (best.gems().size() <= 1) {
      confidence = Confidence.LOW;
    } else {
      int maxSupports = maxSupportCountInGroup(best);
      long tied = sortedGroups.stream().filter(g -> maxSupportCountInGroup(g) == maxSupports).count();
      if (tied > 1) {
        confidence = Confidence.MEDIUM;
      }
    }

    return new Selection(
        new ParsedMainSkill(normalizeSkillName(main.name()), best.labelOrId(), supports, confidence),
        List.copyOf(warnings)
    );
  }

  private static String normalizeSkillName(String name) {
    if (name == null || name.isBlank()) {
      return name;
    }
    // PoB uses nameSpec for transfigured/variant gems (e.g. "Detonate Dead of Chain Reaction").
    // For MVP and test stability, return the base gem name.
    int idx = name.indexOf(" of ");
    if (idx > 0) {
      return name.substring(0, idx).trim();
    }
    return name;
  }

  private static Optional<Gem> selectBestActiveGem(SkillGroup group) {
    if (group == null || group.gems() == null || group.gems().isEmpty()) {
      return Optional.empty();
    }
    // In PoB, supports are linked in the same group. Prefer an active (non-support) gem.
    return group.gems().stream().filter(g -> !g.support()).findFirst();
  }

  private static int maxSupportCountInGroup(SkillGroup group) {
    if (group == null || group.gems() == null) {
      return 0;
    }
    // Best-effort: treat the number of support gems in the group as the "link strength".
    return (int) group.gems().stream().filter(Gem::support).count();
  }

  public record Selection(ParsedMainSkill mainSkill, List<String> warnings) {}
}

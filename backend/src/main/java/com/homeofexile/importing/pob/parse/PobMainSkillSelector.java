package com.homeofexile.importing.pob.parse;

import com.homeofexile.importing.pob.model.Confidence;
import com.homeofexile.importing.pob.model.ParsedMainSkill;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;

import static com.homeofexile.importing.pob.parse.SkillModels.Gem;
import static com.homeofexile.importing.pob.parse.SkillModels.SkillGroup;

public class PobMainSkillSelector {

  public Selection select(List<SkillGroup> groups) {
    if (groups == null || groups.isEmpty()) {
      return new Selection(new ParsedMainSkill(null, null, List.of(), Confidence.LOW), List.of("main skill not found"));
    }

    List<SkillGroup> sorted = groups.stream()
        .sorted(Comparator
            .comparingInt((SkillGroup g) -> g.gems().size()).reversed()
            .thenComparing(g -> g.enabled() ? 0 : 1)
            .thenComparingInt(SkillGroup::id)
        )
        .toList();

    SkillGroup best = sorted.get(0);

    List<String> warnings = new java.util.ArrayList<>();
    if (sorted.size() > 1) {
      SkillGroup second = sorted.get(1);
      if (second.gems().size() == best.gems().size() && second.enabled() == best.enabled()) {
        warnings.add("main skill ambiguous; chose group " + best.id());
      } else if (second.gems().size() == best.gems().size()) {
        warnings.add("main skill tie; chose enabled group " + best.id());
      }
    }

    Gem main = best.gems().stream().filter(g -> !g.support()).findFirst().orElse(best.gems().get(0));
    List<String> supports = best.gems().stream()
        .filter(Gem::support)
        .map(Gem::name)
        .filter(Objects::nonNull)
        .toList();

    Confidence confidence = Confidence.HIGH;
    if (best.gems().size() <= 1) {
      confidence = Confidence.LOW;
    } else {
      int max = best.gems().size();
      long tied = sorted.stream().filter(g -> g.gems().size() == max).count();
      if (tied > 1) {
        confidence = Confidence.MEDIUM;
      }
    }

    return new Selection(
        new ParsedMainSkill(main.name(), best.labelOrId(), supports, confidence),
        List.copyOf(warnings)
    );
  }

  public record Selection(ParsedMainSkill mainSkill, List<String> warnings) {}
}

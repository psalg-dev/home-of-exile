package com.homeofexile.importing.pob.parse;

import java.util.List;

public final class SkillModels {
  private SkillModels() {}

  public record Gem(String name, boolean support) {}

  public record SkillGroup(int id, String label, boolean enabled, List<Gem> gems) {
    public String labelOrId() {
      if (label != null && !label.isBlank()) {
        return label;
      }
      return "Group " + id;
    }
  }
}

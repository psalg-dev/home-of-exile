package com.homeofexile.importing.pob.parse;

import com.homeofexile.importing.pob.model.Confidence;
import org.junit.jupiter.api.Test;

import java.util.List;

import static com.homeofexile.importing.pob.parse.SkillModels.Gem;
import static com.homeofexile.importing.pob.parse.SkillModels.SkillGroup;
import static org.junit.jupiter.api.Assertions.*;

class PobMainSkillSelectorTest {

  @Test
  void choosesLargestGroupAndSetsHighConfidence() {
    PobMainSkillSelector selector = new PobMainSkillSelector();

    List<SkillGroup> groups = List.of(
        new SkillGroup(1, "A", true, List.of(new Gem("A1", false))),
        new SkillGroup(2, "B", true, List.of(new Gem("B1", false), new Gem("B2", true)))
    );

    var sel = selector.select(groups);
    assertEquals("B1", sel.mainSkill().name());
    assertEquals(Confidence.HIGH, sel.mainSkill().confidence());
    assertTrue(sel.warnings().isEmpty());
  }

  @Test
  void tieProducesWarningAndMediumConfidence() {
    PobMainSkillSelector selector = new PobMainSkillSelector();

    List<SkillGroup> groups = List.of(
        new SkillGroup(1, "A", true, List.of(new Gem("A1", false), new Gem("A2", true))),
        new SkillGroup(2, "B", true, List.of(new Gem("B1", false), new Gem("B2", true)))
    );

    var sel = selector.select(groups);
    assertEquals(Confidence.MEDIUM, sel.mainSkill().confidence());
    assertFalse(sel.warnings().isEmpty());
  }

  @Test
  void prefersMoreLinkedSupportsOverMoreTotalGems() {
    PobMainSkillSelector selector = new PobMainSkillSelector();

    List<SkillGroup> groups = List.of(
        // More total gems, but fewer supports
        new SkillGroup(1, "Aura", true, List.of(new Gem("Hatred", false), new Gem("Grace", false), new Gem("Enlighten", true))),
        // Fewer total gems, but more supports (more likely the main skill)
        new SkillGroup(2, "Main", true, List.of(new Gem("Detonate Dead", false), new Gem("Spell Cascade", true), new Gem("Elemental Focus", true)))
    );

    var sel = selector.select(groups);
    assertEquals("Detonate Dead", sel.mainSkill().name());
  }

  @Test
  void singleGemIsLowConfidence() {
    PobMainSkillSelector selector = new PobMainSkillSelector();
    var sel = selector.select(List.of(new SkillGroup(1, "A", true, List.of(new Gem("A1", false)))));
    assertEquals(Confidence.LOW, sel.mainSkill().confidence());
  }
}

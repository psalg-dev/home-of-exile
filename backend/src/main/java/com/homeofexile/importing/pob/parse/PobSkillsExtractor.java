package com.homeofexile.importing.pob.parse;

import com.homeofexile.importing.pob.xml.DomSupport;
import com.homeofexile.importing.pob.xml.TextSupport;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;

import static com.homeofexile.importing.pob.parse.SkillModels.Gem;
import static com.homeofexile.importing.pob.parse.SkillModels.SkillGroup;

public class PobSkillsExtractor {

  public List<SkillGroup> extract(Document doc) {
    List<SkillGroup> skillSets = fromSkillSets(doc);
    if (!skillSets.isEmpty()) {
      return skillSets;
    }

    List<SkillGroup> groups = fromGroups(doc);
    if (!groups.isEmpty()) {
      return groups;
    }
    return fromSkills(doc);
  }

  private List<SkillGroup> fromSkillSets(Document doc) {
    NodeList skillsNodes = doc.getElementsByTagName("Skills");
    if (skillsNodes.getLength() == 0 || !(skillsNodes.item(0) instanceof Element skillsEl)) {
      return List.of();
    }

    String activeSetId = TextSupport.nullIfBlank(skillsEl.getAttribute("activeSkillSet"));

    Element selectedSet = null;
    NodeList sets = skillsEl.getElementsByTagName("SkillSet");
    for (int i = 0; i < sets.getLength(); i++) {
      if (!(sets.item(i) instanceof Element setEl)) {
        continue;
      }
      if (activeSetId != null && activeSetId.equals(setEl.getAttribute("id"))) {
        selectedSet = setEl;
        break;
      }
      if (selectedSet == null) {
        selectedSet = setEl;
      }
    }

    if (selectedSet == null) {
      return List.of();
    }

    List<SkillGroup> groups = new ArrayList<>();
    int index = 0;
    NodeList skills = selectedSet.getElementsByTagName("Skill");
    for (int i = 0; i < skills.getLength(); i++) {
      if (!(skills.item(i) instanceof Element skillEl)) {
        continue;
      }

      boolean enabled = parseBoolean(skillEl.getAttribute("enabled")).orElse(true);
      List<Gem> gems = extractGems(skillEl);
      if (gems.isEmpty()) {
        continue;
      }

      String label = TextSupport.firstNonBlank(skillEl.getAttribute("label"), skillEl.getAttribute("name"));
      if (TextSupport.isBlank(label)) {
        // PoB often leaves Skill labels blank; use the first active gem name as the group label.
        label = gems.stream().filter(g -> !g.support()).map(Gem::name).filter(n -> n != null && !n.isBlank()).findFirst().orElse(null);
      }

      groups.add(new SkillGroup(++index, TextSupport.nullIfBlank(label), enabled, gems));
    }

    return groups;
  }

  private List<SkillGroup> fromGroups(Document doc) {
    List<SkillGroup> groups = new ArrayList<>();
    int index = 0;
    for (Element groupEl : DomSupport.elementsByTag(doc, "Group")) {
      String label = TextSupport.firstNonBlank(groupEl.getAttribute("label"), groupEl.getAttribute("name"));
      boolean enabled = parseBoolean(groupEl.getAttribute("enabled")).orElse(true);
      List<Gem> gems = extractGems(groupEl);
      if (!gems.isEmpty()) {
        groups.add(new SkillGroup(++index, label, enabled, gems));
      }
    }
    return groups;
  }

  private List<SkillGroup> fromSkills(Document doc) {
    List<SkillGroup> groups = new ArrayList<>();
    int index = 0;
    for (Element skillEl : DomSupport.elementsByTag(doc, "Skill")) {
      List<Gem> gems = extractGems(skillEl);
      if (!gems.isEmpty()) {
        String label = TextSupport.firstNonBlank(skillEl.getAttribute("label"), skillEl.getAttribute("name"));
        boolean enabled = parseBoolean(skillEl.getAttribute("enabled")).orElse(true);
        groups.add(new SkillGroup(++index, label, enabled, gems));
      }
    }
    return groups;
  }

  private List<Gem> extractGems(Element container) {
    List<Gem> gems = new ArrayList<>();

    NodeList children = container.getElementsByTagName("Gem");
    for (int i = 0; i < children.getLength(); i++) {
      Node node = children.item(i);
      if (node.getNodeType() == Node.ELEMENT_NODE) {
        Element el = (Element) node;
        boolean enabled = parseBoolean(el.getAttribute("enabled")).orElse(true);
        if (!enabled) {
          continue;
        }

        String name = TextSupport.firstNonBlank(el.getAttribute("name"), el.getAttribute("skillName"), el.getAttribute("nameSpec"));

        boolean support = parseBoolean(el.getAttribute("support")).orElseGet(() -> inferSupport(el));
        gems.add(new Gem(TextSupport.nullIfBlank(name), support));
      }
    }

    if (!gems.isEmpty()) {
      return gems;
    }

    NodeList skills = container.getElementsByTagName("SkillGem");
    for (int i = 0; i < skills.getLength(); i++) {
      Node node = skills.item(i);
      if (node.getNodeType() == Node.ELEMENT_NODE) {
        Element el = (Element) node;
        boolean enabled = parseBoolean(el.getAttribute("enabled")).orElse(true);
        if (!enabled) {
          continue;
        }
        String name = TextSupport.firstNonBlank(el.getAttribute("name"), el.getAttribute("skillName"), el.getAttribute("nameSpec"));
        boolean support = parseBoolean(el.getAttribute("support")).orElseGet(() -> inferSupport(el));
        gems.add(new Gem(TextSupport.nullIfBlank(name), support));
      }
    }

    return gems;
  }

  private boolean inferSupport(Element gemEl) {
    if (gemEl == null) {
      return false;
    }
    String gemId = TextSupport.nullIfBlank(gemEl.getAttribute("gemId"));
    if (gemId != null && gemId.toLowerCase(Locale.ROOT).contains("supportgem")) {
      return true;
    }
    String skillId = TextSupport.nullIfBlank(gemEl.getAttribute("skillId"));
    return skillId != null && skillId.toLowerCase(Locale.ROOT).startsWith("support");
  }

  private Optional<Boolean> parseBoolean(String s) {
    if (TextSupport.isBlank(s)) {
      return Optional.empty();
    }
    String v = s.trim().toLowerCase(Locale.ROOT);
    if (v.equals("true") || v.equals("1") || v.equals("yes")) {
      return Optional.of(true);
    }
    if (v.equals("false") || v.equals("0") || v.equals("no")) {
      return Optional.of(false);
    }
    return Optional.empty();
  }
}

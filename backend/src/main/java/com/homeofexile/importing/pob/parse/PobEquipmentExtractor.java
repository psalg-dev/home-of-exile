package com.homeofexile.importing.pob.parse;

import com.homeofexile.importing.pob.model.ParsedEquipmentItem;
import com.homeofexile.importing.pob.xml.DomSupport;
import com.homeofexile.importing.pob.xml.TextSupport;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class PobEquipmentExtractor {
  private final ItemTextParser itemTextParser;
  private final ItemModsParser itemModsParser;
  private static final Pattern INDEXED_SLOT_PATTERN = Pattern.compile("^(.+?)\\s+(\\d+)(.*)$");

  public PobEquipmentExtractor(ItemTextParser itemTextParser, ItemModsParser itemModsParser) {
    this.itemTextParser = itemTextParser;
    this.itemModsParser = itemModsParser;
  }

  public List<ParsedEquipmentItem> extract(Document doc) {
    List<ParsedEquipmentItem> out = new ArrayList<>();

    Map<String, String> itemIdToSlotName = extractActiveItemSetSlotMap(doc);
    boolean hasItemSetMapping = !itemIdToSlotName.isEmpty();

    for (Element itemEl : DomSupport.elementsByTag(doc, "Item")) {
      String itemId = TextSupport.firstNonBlank(itemEl.getAttribute("id"), itemEl.getAttribute("itemId"));

      String slot = TextSupport.firstNonBlank(
          itemEl.getAttribute("slot"),
          itemEl.getAttribute("slotName"),
          itemEl.getAttribute("inventoryId")
      );

      if (!TextSupport.isBlank(itemId) && itemIdToSlotName.containsKey(itemId)) {
        slot = itemIdToSlotName.get(itemId);
      }

      String raw = DomSupport.textContentOrEmpty(itemEl).trim();

      String rarity = itemTextParser.parseRarity(raw).orElse(null);
      String name = itemTextParser.parseName(raw).orElse(null);

      ItemModsParser.ItemMods mods = itemModsParser.parse(raw);

      boolean looksLikeJewel = looksLikeJewelItem(raw);
      if (TextSupport.isBlank(slot) && looksLikeJewel) {
        slot = "Jewel";
      }

      if (hasItemSetMapping) {
        boolean mapped = !TextSupport.isBlank(itemId) && itemIdToSlotName.containsKey(itemId);
        if (!mapped && !looksLikeJewel) {
          // In many PoB exports, Items contain more than currently equipped gear.
          // When we have an ItemSet mapping, treat it as the source of truth for what's equipped.
          continue;
        }
      }

      slot = normalizeSlotLabel(slot);

      if (!TextSupport.isBlank(raw) || !TextSupport.isBlank(name) || !TextSupport.isBlank(slot)) {
        out.add(new ParsedEquipmentItem(
            TextSupport.nullIfBlank(slot),
            TextSupport.nullIfBlank(name),
            TextSupport.nullIfBlank(rarity),
            raw.isBlank() ? null : raw,
            mods.implicitMods(),
            mods.prefixMods(),
            mods.suffixMods(),
            mods.explicitMods()
        ));
      }
    }

    return out;
  }

  private static Map<String, String> extractActiveItemSetSlotMap(Document doc) {
    Element activeSet = selectActiveOrMostEquippedItemSet(doc);
    if (activeSet == null) {
      return Map.of();
    }

    Map<String, String> out = new HashMap<>();
    NodeList children = activeSet.getChildNodes();
    for (int i = 0; i < children.getLength(); i++) {
      Node n = children.item(i);
      if (n.getNodeType() != Node.ELEMENT_NODE) {
        continue;
      }
      Element el = (Element) n;
      if (!"Slot".equals(el.getTagName())) {
        continue;
      }

      String itemId = TextSupport.firstNonBlank(el.getAttribute("itemId"), el.getAttribute("id"), el.getAttribute("item"));
      if (TextSupport.isBlank(itemId) || "0".equals(itemId)) {
        continue;
      }

      String slotName = TextSupport.nullIfBlank(TextSupport.firstNonBlank(el.getAttribute("name"), el.getAttribute("slotName"), el.getAttribute("slot")));
      if (slotName == null) {
        continue;
      }
      out.put(itemId, slotName);
    }

    return out;
  }

  private static Element selectActiveOrMostEquippedItemSet(Document doc) {
    NodeList buildList = doc.getElementsByTagName("Build");
    String activeId = null;
    if (buildList.getLength() > 0 && buildList.item(0) instanceof Element) {
      Element build = (Element) buildList.item(0);
      activeId = TextSupport.nullIfBlank(build.getAttribute("activeItemSet"));
    }

    NodeList itemSets = doc.getElementsByTagName("ItemSet");
    if (itemSets.getLength() == 0) {
      return null;
    }

    Element best = null;
    int bestEquippedSlots = -1;

    for (int i = 0; i < itemSets.getLength(); i++) {
      if (!(itemSets.item(i) instanceof Element)) {
        continue;
      }
      Element setEl = (Element) itemSets.item(i);

      if (activeId != null && activeId.equals(setEl.getAttribute("id"))) {
        return setEl;
      }

      int equipped = countEquippedSlots(setEl);
      if (equipped > bestEquippedSlots) {
        bestEquippedSlots = equipped;
        best = setEl;
      }
    }

    return best;
  }

  private static int countEquippedSlots(Element itemSet) {
    int count = 0;
    NodeList children = itemSet.getChildNodes();
    for (int i = 0; i < children.getLength(); i++) {
      Node n = children.item(i);
      if (n.getNodeType() != Node.ELEMENT_NODE) {
        continue;
      }
      Element el = (Element) n;
      if (!"Slot".equals(el.getTagName())) {
        continue;
      }
      String itemId = TextSupport.firstNonBlank(el.getAttribute("itemId"), el.getAttribute("id"), el.getAttribute("item"));
      if (!TextSupport.isBlank(itemId) && !"0".equals(itemId)) {
        count++;
      }
    }
    return count;
  }

  private static boolean looksLikeJewelItem(String raw) {
    if (raw == null || raw.isBlank()) {
      return false;
    }
    // PoE item text for jewels typically includes "Item Class: Jewels" (or Abyss jewels) and/or base names ending with "Jewel".
    String lower = raw.toLowerCase();
    return lower.contains("item class: jewels") || lower.contains("jewel");
  }

  private static String normalizeSlotLabel(String slotName) {
    if (TextSupport.isBlank(slotName)) {
      return null;
    }
    String s = slotName.trim();

    String lower = s.toLowerCase();
    if (lower.startsWith("flask")) {
      return "Flask Slot";
    }
    if (lower.startsWith("amulet")) {
      return "Amulet Slot";
    }
    if (lower.startsWith("jewel")) {
      return "Jewel Slot";
    }

    Matcher m = INDEXED_SLOT_PATTERN.matcher(s);
    if (m.matches()) {
      String base = m.group(1).trim();
      String idx = m.group(2).trim();
      String suffix = m.group(3) == null ? "" : m.group(3).trim();
      if (suffix.isEmpty()) {
        return base + " Slot (" + idx + ")";
      }
      return base + " Slot (" + idx + " " + suffix + ")";
    }

    return s + " Slot";
  }
}

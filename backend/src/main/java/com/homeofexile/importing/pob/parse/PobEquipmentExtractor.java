package com.homeofexile.importing.pob.parse;

import com.homeofexile.importing.pob.model.ParsedEquipmentItem;
import com.homeofexile.importing.pob.xml.DomSupport;
import com.homeofexile.importing.pob.xml.TextSupport;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

import java.util.ArrayList;
import java.util.List;

public class PobEquipmentExtractor {
  private final ItemTextParser itemTextParser;

  public PobEquipmentExtractor(ItemTextParser itemTextParser) {
    this.itemTextParser = itemTextParser;
  }

  public List<ParsedEquipmentItem> extract(Document doc) {
    List<ParsedEquipmentItem> out = new ArrayList<>();

    for (Element itemEl : DomSupport.elementsByTag(doc, "Item")) {
      String slot = TextSupport.firstNonBlank(
          itemEl.getAttribute("slot"),
          itemEl.getAttribute("slotName"),
          itemEl.getAttribute("inventoryId")
      );
      String raw = DomSupport.textContentOrEmpty(itemEl).trim();

      String rarity = itemTextParser.parseRarity(raw).orElse(null);
      String name = itemTextParser.parseName(raw).orElse(null);

      if (!TextSupport.isBlank(raw) || !TextSupport.isBlank(name) || !TextSupport.isBlank(slot)) {
        out.add(new ParsedEquipmentItem(
            TextSupport.nullIfBlank(slot),
            TextSupport.nullIfBlank(name),
            TextSupport.nullIfBlank(rarity),
            raw.isBlank() ? null : raw
        ));
      }
    }

    return out;
  }
}

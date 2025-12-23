package com.homeofexile.importing.pob.parse;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ItemModsParserTest {

  @Test
  void extractsImplicitsAndExplicitModsFromTypicalItemText() {
    String raw = """
        Item Class: Amulets
        Rarity: Rare
        Doom Collar
        Citrine Amulet
        --------
        Requirements:
        Level: 16
        --------
        Item Level: 83
        --------
        Implicits: 1
        +16 to Strength
        --------
        Prefix: +55 to maximum Life
        Suffix: +35% to Fire Resistance
        +33% to Lightning Resistance {crafted}
        Corrupted
        """;

    ItemModsParser parser = new ItemModsParser();
    var mods = parser.parse(raw);

    assertTrue(mods.implicitMods().contains("+16 to Strength"));

    assertTrue(mods.prefixMods().contains("+55 to maximum Life"));
    assertTrue(mods.suffixMods().contains("+35% to Fire Resistance"));

    assertTrue(mods.explicitMods().contains("+55 to maximum Life"));
    assertTrue(mods.explicitMods().contains("+35% to Fire Resistance"));
    assertTrue(mods.explicitMods().contains("+33% to Lightning Resistance"));
    assertTrue(mods.explicitMods().contains("Corrupted"));
  }

  @Test
  void emptyInputReturnsEmptyLists() {
    ItemModsParser parser = new ItemModsParser();
    var mods = parser.parse(" ");
    assertTrue(mods.implicitMods().isEmpty());
    assertTrue(mods.explicitMods().isEmpty());
  }
}

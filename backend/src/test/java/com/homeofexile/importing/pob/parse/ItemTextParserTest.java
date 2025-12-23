package com.homeofexile.importing.pob.parse;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ItemTextParserTest {

  @Test
  void parsesRarityAndName() {
    String raw = """
        Item Class: One Hand Maces
        Rarity: Rare
        Void Sceptre
        Opal Sceptre
        """;

    ItemTextParser parser = new ItemTextParser();

    assertEquals("RARE", parser.parseRarity(raw).orElseThrow());
    assertEquals("Void Sceptre Opal Sceptre", parser.parseName(raw).orElseThrow());
  }

  @Test
  void handlesEmpty() {
    ItemTextParser parser = new ItemTextParser();
    assertTrue(parser.parseName(" ").isEmpty());
    assertTrue(parser.parseRarity(null).isEmpty());
  }
}

package com.homeofexile.importing.pob;

import com.homeofexile.importing.pob.model.Confidence;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PobXmlParserTest {

  @Test
  void extractsCharacterEquipmentAndMainSkill() {
    String xml = """
        <PathOfBuilding>
          <Build level=\"92\" className=\"Witch\" ascendClassName=\"Occultist\" />
          <Items>
            <Item slot=\"Weapon\"><![CDATA[
Item Class: One Hand Maces
Rarity: Rare
Void Sceptre
Opal Sceptre
            ]]></Item>
          </Items>
          <Skills>
            <Group label=\"Main\" enabled=\"true\">
              <Gem name=\"Freezing Pulse\" support=\"false\" />
              <Gem name=\"Spell Echo\" support=\"true\" />
              <Gem name=\"Controlled Destruction\" support=\"true\" />
            </Group>
          </Skills>
        </PathOfBuilding>
        """;

    PobXmlParser parser = new PobXmlParser();
    var parsed = parser.parse(xml);

    assertEquals("Witch", parsed.character().clazz());
    assertEquals("Occultist", parsed.character().ascendancy());
    assertEquals(92, parsed.character().level());

    assertEquals(1, parsed.equipment().size());
    assertEquals("Weapon", parsed.equipment().get(0).slot());
    assertNotNull(parsed.equipment().get(0).name());
    assertEquals("RARE", parsed.equipment().get(0).rarity());

    assertEquals("Freezing Pulse", parsed.mainSkill().name());
    assertEquals(Confidence.HIGH, parsed.mainSkill().confidence());
    assertTrue(parsed.mainSkill().supportGems().contains("Spell Echo"));
  }

  @Test
  void returnsWarningsWhenMissing() {
    PobXmlParser parser = new PobXmlParser();
    var parsed = parser.parse("<a/>");

    assertFalse(parsed.warnings().isEmpty());
    assertNotNull(parsed.mainSkill());
  }
}

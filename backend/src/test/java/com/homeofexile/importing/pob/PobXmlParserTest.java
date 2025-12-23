package com.homeofexile.importing.pob;

import com.homeofexile.importing.pob.model.Confidence;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

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
    assertEquals("Weapon Slot", parsed.equipment().get(0).slot());
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

  @Test
  void extractsEquipmentSlotsFromItemSetMapping_cwsWitch() throws Exception {
    String exportCode = Files.readString(Path.of("src/test/resources/cws-witch.txt"));
    String xml = new PobDecoder(2 * 1024 * 1024).decodeToXml(exportCode);

    PobXmlParser parser = new PobXmlParser();
    var parsed = parser.parse(xml);

    assertFalse(parsed.equipment().isEmpty(), "expected equipment to be extracted");

    Set<String> slots = parsed.equipment().stream()
      .map(i -> i.slot() == null ? "" : i.slot())
      .collect(Collectors.toSet());

    assertTrue(slots.contains("Jewel Slot"), "expected Jewel Slot");
    assertTrue(slots.contains("Amulet Slot"), "expected Amulet Slot");
    assertTrue(slots.contains("Flask Slot"), "expected Flask Slot");

    assertEquals("Detonate Dead", parsed.mainSkill().name(), "expected main skill to be Detonate Dead for cws-witch");

    assertTrue(
      parsed.equipment().stream().anyMatch(i -> i.explicitMods() != null && !i.explicitMods().isEmpty()),
      "expected at least one item to have explicit mods extracted"
    );

    assertTrue(parsed.equipment().stream().noneMatch(i -> i.slot() == null || i.slot().isBlank()), "expected no blank slots");
    assertTrue(parsed.equipment().stream().noneMatch(i -> i.slot().contains("Unknown")), "expected no Unknown slot labels");
    assertTrue(parsed.equipment().stream().noneMatch(i -> i.slot().startsWith("Flask Slot") && i.slot().contains("(")), "expected Flask Slot without index");
  }
}

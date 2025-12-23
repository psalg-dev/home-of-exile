package com.homeofexile.importing.pob;

import com.homeofexile.importing.pob.parse.ItemTextParser;
import com.homeofexile.importing.pob.parse.PobCharacterExtractor;
import com.homeofexile.importing.pob.parse.PobClassNormalizer;
import com.homeofexile.importing.pob.parse.PobEquipmentExtractor;
import com.homeofexile.importing.pob.parse.PobMainSkillSelector;
import com.homeofexile.importing.pob.parse.PobSkillsExtractor;
import com.homeofexile.importing.pob.exception.PobParseException;
import com.homeofexile.importing.pob.model.Confidence;
import com.homeofexile.importing.pob.model.ParsedCharacter;
import com.homeofexile.importing.pob.model.ParsedEquipmentItem;
import com.homeofexile.importing.pob.model.ParsedMainSkill;
import com.homeofexile.importing.pob.model.ParsedPob;
import com.homeofexile.importing.pob.xml.SecureXml;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;

import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import javax.xml.parsers.DocumentBuilder;

public class PobXmlParser {

  private final PobCharacterExtractor characterExtractor;
  private final PobEquipmentExtractor equipmentExtractor;
  private final PobSkillsExtractor skillsExtractor;
  private final PobMainSkillSelector mainSkillSelector;

  public PobXmlParser() {
    PobClassNormalizer classNormalizer = new PobClassNormalizer();
    this.characterExtractor = new PobCharacterExtractor(classNormalizer);
    this.equipmentExtractor = new PobEquipmentExtractor(new ItemTextParser());
    this.skillsExtractor = new PobSkillsExtractor();
    this.mainSkillSelector = new PobMainSkillSelector();
  }

  public ParsedPob parse(String xml) {
    if (xml == null || xml.isBlank()) {
      throw new PobParseException("PoB XML is empty", List.of("xml is blank"));
    }

    Document doc;
    try {
      DocumentBuilder builder = SecureXml.newDocumentBuilder();
      doc = builder.parse(new InputSource(new StringReader(xml)));
    } catch (Exception e) {
      throw new PobParseException("Could not parse PoB XML", List.of("xml parse failed"));
    }

    List<String> warnings = new ArrayList<>();
    String xmlVersion = doc.getXmlVersion();

    ParsedCharacter character = characterExtractor.extract(doc).orElseGet(() -> {
      warnings.add("character metadata not found");
      return new ParsedCharacter(null, null, null, null);
    });

    List<ParsedEquipmentItem> equipment = equipmentExtractor.extract(doc);
    if (equipment.isEmpty()) {
      warnings.add("no equipment found");
    }

    PobMainSkillSelector.Selection selection = mainSkillSelector.select(skillsExtractor.extract(doc));
    warnings.addAll(selection.warnings());
    ParsedMainSkill mainSkill = selection.mainSkill();
    if (mainSkill.name() == null && mainSkill.group() == null) {
      // Keep contract stable: still return a mainSkill object even when missing.
      mainSkill = new ParsedMainSkill(null, null, List.of(), Confidence.LOW);
    }

    return new ParsedPob(character, mainSkill, equipment, List.copyOf(warnings), xmlVersion);
  }
}

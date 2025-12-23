package com.homeofexile.importing.pob;

import org.junit.jupiter.api.Test;

import static com.homeofexile.importing.pob.testsupport.PobTestSupport.exportCodeFromXml;
import static org.junit.jupiter.api.Assertions.*;

class PobImportServiceTest {

  @Test
  void wiresDecoderAndParser() {
    PobDecoder decoder = new PobDecoder(1024 * 1024);
    PobXmlParser parser = new PobXmlParser();
    PobImportService service = new PobImportService(decoder, parser);

    String xml = "<PathOfBuilding><Build level=\"80\" className=\"Templar\"/></PathOfBuilding>";
    String exportCode = exportCodeFromXml(xml);

    var parsed = service.importExportCode(exportCode);
    assertEquals("Templar", parsed.character().clazz());
    assertEquals(80, parsed.character().level());
  }
}

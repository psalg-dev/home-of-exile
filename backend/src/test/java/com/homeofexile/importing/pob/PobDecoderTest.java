package com.homeofexile.importing.pob;

import com.homeofexile.importing.pob.exception.InvalidPobExportCodeException;
import org.junit.jupiter.api.Test;

import static com.homeofexile.importing.pob.testsupport.PobTestSupport.exportCodeFromXml;
import static org.junit.jupiter.api.Assertions.*;

class PobDecoderTest {

  @Test
  void decodesZlibCompressedBase64ToXml() {
    String xml = "<PathOfBuilding><Build level=\"92\" className=\"Witch\"/></PathOfBuilding>";
    String exportCode = exportCodeFromXml(xml);

    PobDecoder decoder = new PobDecoder(1024 * 1024);
    String decoded = decoder.decodeToXml(exportCode);

    assertEquals(xml, decoded);
  }

  @Test
  void rejectsBlank() {
    PobDecoder decoder = new PobDecoder(1024);
    assertThrows(InvalidPobExportCodeException.class, () -> decoder.decodeToXml("  "));
  }

  @Test
  void rejectsInvalidBase64() {
    PobDecoder decoder = new PobDecoder(1024);
    assertThrows(InvalidPobExportCodeException.class, () -> decoder.decodeToXml("not-base64!!!"));
  }

  @Test
  void enforcesSizeLimit() {
    StringBuilder sb = new StringBuilder();
    sb.append("<a>");
    for (int i = 0; i < 5000; i++) {
      sb.append("xxxxxxxxxx");
    }
    sb.append("</a>");

    String exportCode = exportCodeFromXml(sb.toString());
    PobDecoder decoder = new PobDecoder(100);

    InvalidPobExportCodeException ex = assertThrows(InvalidPobExportCodeException.class, () -> decoder.decodeToXml(exportCode));
    assertTrue(ex.details().stream().anyMatch(d -> d.contains("size")));
  }
}

package com.homeofexile.importing.pob;

import com.homeofexile.importing.pob.model.ParsedPob;

import java.util.Objects;

public class PobImportService {
  private final PobDecoder decoder;
  private final PobXmlParser parser;

  public PobImportService(PobDecoder decoder, PobXmlParser parser) {
    this.decoder = Objects.requireNonNull(decoder);
    this.parser = Objects.requireNonNull(parser);
  }

  public ParsedPob importExportCode(String exportCode) {
    String xml = decoder.decodeToXml(exportCode);
    return parser.parse(xml);
  }
}

package com.homeofexile.importing.pob.api;

import com.homeofexile.importing.pob.PobDecoder;
import com.homeofexile.importing.pob.PobImportService;
import com.homeofexile.importing.pob.PobXmlParser;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PobImportConfig {

  @Bean
  PobDecoder pobDecoder() {
    // Defensive limit against abuse; PoB XML is typically far smaller.
    return new PobDecoder(2 * 1024 * 1024);
  }

  @Bean
  PobXmlParser pobXmlParser() {
    return new PobXmlParser();
  }

  @Bean
  PobImportService pobImportService(PobDecoder decoder, PobXmlParser parser) {
    return new PobImportService(decoder, parser);
  }
}

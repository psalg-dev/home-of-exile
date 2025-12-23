package com.homeofexile.importing.pob.parse;

import com.homeofexile.importing.pob.model.ParsedCharacter;
import com.homeofexile.importing.pob.xml.DomSupport;
import com.homeofexile.importing.pob.xml.TextSupport;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

import java.util.Optional;

public class PobCharacterExtractor {
  private final PobClassNormalizer classNormalizer;

  public PobCharacterExtractor(PobClassNormalizer classNormalizer) {
    this.classNormalizer = classNormalizer;
  }

  public Optional<ParsedCharacter> extract(Document doc) {
    Element build = DomSupport.firstElementByTag(doc, "Build").orElse(null);
    if (build != null) {
      String level = TextSupport.firstNonBlank(build.getAttribute("level"), build.getAttribute("characterLevel"));
      String clazz = TextSupport.firstNonBlank(build.getAttribute("className"), build.getAttribute("class"));
      String ascendancy = TextSupport.firstNonBlank(build.getAttribute("ascendClassName"), build.getAttribute("ascendancy"));
      String name = TextSupport.firstNonBlank(build.getAttribute("name"), build.getAttribute("characterName"));

      Integer parsedLevel = tryParseInt(level).orElse(null);
      String normalizedClass = classNormalizer.normalize(clazz).orElse(clazz);

      if (parsedLevel != null || !TextSupport.isBlank(normalizedClass)) {
        return Optional.of(new ParsedCharacter(
            TextSupport.nullIfBlank(name),
            TextSupport.nullIfBlank(normalizedClass),
            TextSupport.nullIfBlank(ascendancy),
            parsedLevel
        ));
      }
    }

    for (Element el : DomSupport.allElements(doc)) {
      String clazz = el.getAttribute("className");
      String level = el.getAttribute("level");
      if (!TextSupport.isBlank(clazz) || !TextSupport.isBlank(level)) {
        Integer parsedLevel = tryParseInt(level).orElse(null);
        String normalizedClass = classNormalizer.normalize(clazz).orElse(clazz);
        if (parsedLevel != null || !TextSupport.isBlank(normalizedClass)) {
          return Optional.of(new ParsedCharacter(null, TextSupport.nullIfBlank(normalizedClass), null, parsedLevel));
        }
      }
    }

    return Optional.empty();
  }

  private Optional<Integer> tryParseInt(String s) {
    if (TextSupport.isBlank(s)) {
      return Optional.empty();
    }
    try {
      return Optional.of(Integer.parseInt(s.trim()));
    } catch (NumberFormatException e) {
      return Optional.empty();
    }
  }
}

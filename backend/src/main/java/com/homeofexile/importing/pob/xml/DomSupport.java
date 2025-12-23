package com.homeofexile.importing.pob.xml;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public final class DomSupport {
  private DomSupport() {}

  public static Optional<Element> firstElementByTag(Document doc, String tag) {
    NodeList list = doc.getElementsByTagName(tag);
    for (int i = 0; i < list.getLength(); i++) {
      Node n = list.item(i);
      if (n.getNodeType() == Node.ELEMENT_NODE) {
        return Optional.of((Element) n);
      }
    }
    return Optional.empty();
  }

  public static List<Element> elementsByTag(Document doc, String tag) {
    NodeList list = doc.getElementsByTagName(tag);
    List<Element> out = new ArrayList<>();
    for (int i = 0; i < list.getLength(); i++) {
      Node n = list.item(i);
      if (n.getNodeType() == Node.ELEMENT_NODE) {
        out.add((Element) n);
      }
    }
    return out;
  }

  public static List<Element> allElements(Document doc) {
    return elementsByTag(doc, "*");
  }

  public static String textContentOrEmpty(Element el) {
    String text = el.getTextContent();
    return text == null ? "" : text;
  }
}

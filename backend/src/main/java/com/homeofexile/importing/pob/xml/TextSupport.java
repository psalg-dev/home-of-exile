package com.homeofexile.importing.pob.xml;

public final class TextSupport {
  private TextSupport() {}

  public static boolean isBlank(String s) {
    return s == null || s.isBlank();
  }

  public static String firstNonBlank(String... values) {
    for (String v : values) {
      if (!isBlank(v)) {
        return v;
      }
    }
    return null;
  }

  public static String nullIfBlank(String s) {
    return isBlank(s) ? null : s;
  }
}

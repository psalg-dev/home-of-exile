package com.homeofexile.importing.pob.xml;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class TextSupportTest {

  @Test
  void helpersBehaveAsExpected() {
    assertTrue(TextSupport.isBlank(null));
    assertTrue(TextSupport.isBlank("  "));
    assertEquals("x", TextSupport.firstNonBlank(" ", null, "x"));
    assertNull(TextSupport.nullIfBlank("  "));
    assertEquals("ok", TextSupport.nullIfBlank("ok"));
  }
}

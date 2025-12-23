package com.homeofexile.importing.pob.testsupport;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.zip.Deflater;

public final class PobTestSupport {
  private PobTestSupport() {}

  public static String exportCodeFromXml(String xml) {
    byte[] input = xml.getBytes(StandardCharsets.UTF_8);

    Deflater deflater = new Deflater(Deflater.DEFAULT_COMPRESSION, false);
    deflater.setInput(input);
    deflater.finish();

    byte[] buffer = new byte[8192];
    try (ByteArrayOutputStream baos = new ByteArrayOutputStream()) {
      while (!deflater.finished()) {
        int count = deflater.deflate(buffer);
        baos.write(buffer, 0, count);
      }
      deflater.end();
      return Base64.getEncoder().encodeToString(baos.toByteArray());
    } catch (Exception e) {
      throw new RuntimeException(e);
    }
  }
}

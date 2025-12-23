package com.homeofexile.importing.pob;

import com.homeofexile.importing.pob.exception.InvalidPobExportCodeException;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.List;
import java.util.zip.Inflater;
import java.util.zip.InflaterInputStream;

public class PobDecoder {
  private final int maxDecodedBytes;

  public PobDecoder(int maxDecodedBytes) {
    this.maxDecodedBytes = maxDecodedBytes;
  }

  public String decodeToXml(String exportCode) {
    if (exportCode == null || exportCode.isBlank()) {
      throw new InvalidPobExportCodeException(
          "Could not decode or parse the Path of Building export code",
          List.of("exportCode is blank")
      );
    }

    String normalized = exportCode.trim().replaceAll("\\s+", "");

    byte[] compressed;
    try {
      compressed = Base64.getDecoder().decode(normalized);
    } catch (IllegalArgumentException standard) {
      try {
        compressed = Base64.getUrlDecoder().decode(normalized);
      } catch (IllegalArgumentException urlSafe) {
        throw new InvalidPobExportCodeException(
            "Could not decode or parse the Path of Building export code",
            List.of("base64 decode failed")
        );
      }
    }

    byte[] xmlBytes = tryInflate(compressed, false);
    if (xmlBytes == null) {
      xmlBytes = tryInflate(compressed, true);
    }
    if (xmlBytes == null) {
      throw new InvalidPobExportCodeException(
          "Could not decode or parse the Path of Building export code",
          List.of("decompression failed")
      );
    }

    return new String(xmlBytes, StandardCharsets.UTF_8);
  }

  private byte[] tryInflate(byte[] input, boolean nowrap) {
    try (ByteArrayInputStream bais = new ByteArrayInputStream(input);
         InflaterInputStream inflaterStream = new InflaterInputStream(bais, new Inflater(nowrap));
         ByteArrayOutputStream baos = new ByteArrayOutputStream()) {

      byte[] buffer = new byte[8192];
      int read;
      int total = 0;
      while ((read = inflaterStream.read(buffer)) != -1) {
        total += read;
        if (total > maxDecodedBytes) {
          throw new InvalidPobExportCodeException(
              "Could not decode or parse the Path of Building export code",
              List.of("decoded payload exceeds size limit")
          );
        }
        baos.write(buffer, 0, read);
      }
      return baos.toByteArray();
    } catch (InvalidPobExportCodeException e) {
      throw e;
    } catch (Exception ignored) {
      return null;
    }
  }
}

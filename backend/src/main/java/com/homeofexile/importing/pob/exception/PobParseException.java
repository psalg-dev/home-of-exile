package com.homeofexile.importing.pob.exception;

import java.util.List;

public class PobParseException extends RuntimeException {
  private final List<String> details;

  public PobParseException(String message, List<String> details) {
    super(message);
    this.details = details;
  }

  public List<String> details() {
    return details;
  }
}

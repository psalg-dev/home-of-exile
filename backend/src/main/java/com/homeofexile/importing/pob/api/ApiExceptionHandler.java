package com.homeofexile.importing.pob.api;

import com.homeofexile.importing.pob.dto.ApiErrorDto;
import com.homeofexile.importing.pob.dto.ErrorResponse;
import com.homeofexile.importing.pob.exception.InvalidPobExportCodeException;
import com.homeofexile.importing.pob.exception.PobParseException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;
import java.util.UUID;

@RestControllerAdvice
public class ApiExceptionHandler {

  @ExceptionHandler(MethodArgumentNotValidException.class)
  public ResponseEntity<ErrorResponse> onValidation(MethodArgumentNotValidException e) {
    List<String> details = e.getBindingResult().getFieldErrors().stream()
        .map(err -> err.getField() + ": " + err.getDefaultMessage())
        .toList();

    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(new ErrorResponse(
        new ApiErrorDto("INVALID_REQUEST", "Invalid request", details)
    ));
  }

  @ExceptionHandler(InvalidPobExportCodeException.class)
  public ResponseEntity<ErrorResponse> onInvalidExportCode(InvalidPobExportCodeException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(new ErrorResponse(
        new ApiErrorDto("INVALID_POB_EXPORT_CODE", e.getMessage(), e.details())
    ));
  }

  @ExceptionHandler(PobParseException.class)
  public ResponseEntity<ErrorResponse> onParse(PobParseException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(new ErrorResponse(
        new ApiErrorDto("INVALID_POB_EXPORT_CODE", e.getMessage(), e.details())
    ));
  }

  @ExceptionHandler(Exception.class)
  public ResponseEntity<ErrorResponse> onUnexpected(Exception e) {
    String id = UUID.randomUUID().toString();
    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(new ErrorResponse(
        new ApiErrorDto("INTERNAL_ERROR", "Unexpected error (ref " + id + ")", List.of())
    ));
  }
}

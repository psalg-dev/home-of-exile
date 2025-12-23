package com.homeofexile.importing.pob;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static com.homeofexile.importing.pob.testsupport.PobTestSupport.exportCodeFromXml;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class PobImportControllerIT {

  @Autowired
  MockMvc mvc;

  @Test
  void importEndpointReturnsParsedJson() throws Exception {
    String xml = "<PathOfBuilding><Build level=\"90\" className=\"Ranger\"/></PathOfBuilding>";
    String exportCode = exportCodeFromXml(xml);

    mvc.perform(post("/api/import/pob")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"exportCode\":\"" + exportCode + "\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.character.class").value("Ranger"))
        .andExpect(jsonPath("$.character.level").value(90))
        .andExpect(jsonPath("$.raw.source").value("POB_EXPORT_CODE"));
  }

  @Test
  void invalidInputReturns400() throws Exception {
    mvc.perform(post("/api/import/pob")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"exportCode\":\"not-base64\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_POB_EXPORT_CODE"));
  }
}

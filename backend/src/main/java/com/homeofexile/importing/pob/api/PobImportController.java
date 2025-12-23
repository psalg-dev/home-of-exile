package com.homeofexile.importing.pob.api;

import com.homeofexile.importing.pob.PobImportService;
import com.homeofexile.importing.pob.dto.CharacterDto;
import com.homeofexile.importing.pob.dto.EquipmentItemDto;
import com.homeofexile.importing.pob.dto.MainSkillDto;
import com.homeofexile.importing.pob.dto.PobImportRequest;
import com.homeofexile.importing.pob.dto.PobImportResponse;
import com.homeofexile.importing.pob.dto.RawMetaDto;
import com.homeofexile.importing.pob.model.ParsedCharacter;
import com.homeofexile.importing.pob.model.ParsedMainSkill;
import com.homeofexile.importing.pob.model.ParsedPob;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/import")
public class PobImportController {
  private final PobImportService service;

  public PobImportController(PobImportService service) {
    this.service = service;
  }

  @PostMapping("/pob")
  public PobImportResponse importPob(@Valid @RequestBody PobImportRequest request) {
    ParsedPob parsed = service.importExportCode(request.exportCode());

    ParsedCharacter character = parsed.character();
    ParsedMainSkill mainSkill = parsed.mainSkill();

    List<EquipmentItemDto> equipment = parsed.equipment().stream()
      .map(i -> new EquipmentItemDto(
        i.slot(),
        i.name(),
        i.rarity(),
        i.raw(),
        i.implicitMods(),
        i.prefixMods(),
        i.suffixMods(),
        i.explicitMods()
      ))
        .toList();

    return new PobImportResponse(
        new CharacterDto(character.name(), character.clazz(), character.ascendancy(), character.level()),
        new MainSkillDto(mainSkill.name(), mainSkill.group(), mainSkill.supportGems(), mainSkill.confidence().name()),
        equipment,
        new RawMetaDto(parsed.xmlVersion(), parsed.warnings(), "POB_EXPORT_CODE")
    );
  }
}

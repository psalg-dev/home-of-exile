# Copilot instructions (Home of Exile)

## Big picture
- This repo is a minimal MVP for importing a Path of Building (PoB) **export code** and displaying parsed results.
- **Frontend (Vue 3 + Vite)** posts to the backend at `POST /api/import/pob` via `fetch` and renders the parsed DTOs.
- **Backend (Spring Boot 3 / Java 17 / Maven)** decodes+decompresses the export code to XML, parses XML safely, and returns a stable JSON contract (including warnings).

## Key paths / boundaries
- Backend entrypoint: `backend/src/main/java/com/homeofexile/HomeOfExileApplication.java`
- REST API: `backend/src/main/java/com/homeofexile/importing/pob/api/PobImportController.java`
- Import pipeline:
  - decode/decompress: `.../importing/pob/PobDecoder.java` (Base64 + zlib/raw-deflate; size limited)
  - XML parse + orchestration: `.../importing/pob/PobXmlParser.java`
  - extractors/heuristics: `.../importing/pob/parse/*` (equipment, main skill selection, item text/mods)
  - secure XML config (XXE/DTD disabled): `.../importing/pob/xml/SecureXml.java`
- Frontend import flow:
  - API wrapper: `frontend/src/api/importPob.js`
  - main view: `frontend/src/views/PobImportView.vue`
  - UI components use `data-cy` hooks: `frontend/src/components/PobImportForm.vue`, `frontend/src/components/PobImportResult.vue`

## API contract (what FE expects)
- `POST /api/import/pob` body: `{ "exportCode": "..." }`
- Success response includes:
  - `character: { class, ascendancy, level, name? }`
  - `mainSkill: { name, group, supportGems: [], confidence: 'HIGH'|'MEDIUM'|'LOW' }`
  - `equipment[]: { slot, name, rarity, raw, implicitMods, prefixMods, suffixMods, explicitMods }`
  - `raw: { warnings: [], source: 'POB_EXPORT_CODE', xmlVersion? }`
- Errors are JSON: `{ error: { code, message, details: [] } }` via `.../api/ApiExceptionHandler.java`.

## Local dev workflows
- Backend (from `backend/`):
  - `mvn test` (runs unit+IT and enforces JaCoCo ≥80% on `com.homeofexile.importing.pob*` packages)
  - `mvn spring-boot:run` (localhost:8080)
- Frontend (from `frontend/`):
  - `npm install`
  - `npm run dev` (localhost:5173)
  - `npm run cy:open` / `npm run cy:run` (Cypress)
  - `npm run e2e` (runs `dev` then Cypress against it; backend must be running for the “real backend” test)
  - Vite proxies `/api` to `http://127.0.0.1:8080` in `frontend/vite.config.js`.

## Testing conventions
- For E2e Tests, Frontend and Backend MUST ALWAYS be started in a separate terminal.
- Backend tests are JUnit/Spring Boot:
  - integration: `backend/src/test/java/.../PobImportControllerIT.java` (MockMvc)
  - fixtures: `backend/src/test/resources/cws-witch.txt`
  - PoB export-code fixtures in tests are generated from XML via `.../testsupport/PobTestSupport.exportCodeFromXml()`.
- Cypress e2e:
  - spec: `frontend/cypress/e2e/pob_import.cy.js`
  - has both mocked API tests (`cy.intercept` with a stub body) and a “real backend” test that reads `../backend/src/test/resources/cws-witch.txt` and requires the backend running.

## Project-specific implementation patterns
- Keep parsing deterministic and return **warnings** rather than relying on logs (see `PobXmlParser` + `PobMainSkillSelector`).
- The backend keeps the response contract stable by returning objects with `null` fields + `LOW` confidence when data is missing (instead of omitting structures).
- Do not log full export codes; errors should return sanitized `details` lists (decoder/parser exceptions already follow this pattern).

---
agent: agent
---
# Implementation Plan — First MVP Version (PoB Export Code Import)

This document is a detailed implementation plan for the **First Version Scope** defined in `.github/prompts/mvp.prompt.md`.

## Context / Assumptions
- This repository currently contains only prompt documents (no backend/frontend source tree is present in `HEAD`).
- The plan assumes the target architecture described in `.github/prompts/home-of-exile.prompt.md`:
  - **Frontend:** Vue.js (SPA)
  - **Backend:** Spring Boot (REST)
- MVP v1 is **import + parse + display** only. No recommendations, persistence, accounts, or poe.ninja integration.

## Engineering Requirements (from `home-of-exile.prompt.md`)
- **Testing**
  - Backend unit/integration tests use **JUnit + Mockito**.
  - Frontend end-to-end tests use **Cypress**.
- **Code conventions**
  - Avoid source code files longer than **200 lines** (split into small, single-responsibility classes/components).
  - Follow standard naming conventions.
- **Quality gates**
  - Business logic covered by unit tests with at least **80%** coverage.
  - Features covered by **end-to-end tests**.
- **Constraints**
  - Use open-source technologies and respect Path of Exile / third-party **Terms of Service**.
  - Avoid duplicating large existing open-source codebases; prefer integration/interop where feasible.

## MVP v1 Success Criteria (Definition of Done)
- User can paste a **Path of Building (PoB) Export Code** into a text area.
- App parses the export code and extracts (at minimum):
  - character **class** (and ideally **ascendancy** when available)
  - character **level**
  - **equipment** list (basic item name + slot; plus raw item text for later)
  - **main skill** (best-effort from skills/gem links; if ambiguous, pick the highest linked/active group and state confidence)
- UI displays the parsed result clearly and handles errors (invalid code) gracefully.

---

## Phase 0 — Project Alignment (1–2 hours)
1. Confirm the exact projects/paths for backend and frontend (since they are not present in this repo):
   - Backend repo/path, Java version, build tool (Maven/Gradle), current REST base path.
   - Frontend repo/path, Vue version (2/3), router/state usage, API base URL.
2. Confirm where PoB parsing should live:
   - Preferred: backend does parsing (consistent results, avoids bundling decompression/XML libs into browser).
3. Confirm testing and quality-gate tooling:
  - Backend: how coverage is measured/enforced (e.g., JaCoCo) and where the 80% threshold is configured.
  - Frontend: where Cypress lives and how it runs in CI (baseUrl, ports, test command).
4. Confirm compliance constraints:
  - Ensure we do not log/store export codes beyond what is needed for parsing and tests.
5. Gather 3–5 representative PoB export codes for test fixtures:
   - one spell caster
   - one attack build
   - one minion/totem build
   - one intentionally malformed/partial

Deliverable:
- A small set of anonymized PoB export codes (or locally stored test fixtures) and a confirmed endpoint base URL.

---

## Phase 1 — Define the API Contract (Backend ↔ Frontend)

### Endpoint
- `POST /api/import/pob`

### Request JSON
```json
{
  "exportCode": "<pob export code string>"
}
```

### Response JSON (Success)
```json
{
  "character": {
    "name": "optional",
    "class": "Witch",
    "ascendancy": "Occultist",
    "level": 92
  },
  "mainSkill": {
    "name": "Freezing Pulse",
    "group": "Skill Group Name or Index",
    "supportGems": ["Spell Echo", "Controlled Destruction"],
    "confidence": "HIGH"
  },
  "equipment": [
    {
      "slot": "Weapon",
      "name": "Void Sceptre",
      "rarity": "RARE",
      "raw": "Item Class: One Hand Maces\nRarity: Rare\n..."
    }
  ],
  "raw": {
    "xmlVersion": "optional",
    "warnings": ["main skill ambiguous; chose group 2"],
    "source": "POB_EXPORT_CODE"
  }
}
```

### Error Responses
- `400 Bad Request` for invalid input
```json
{
  "error": {
    "code": "INVALID_POB_EXPORT_CODE",
    "message": "Could not decode or parse the Path of Building export code",
    "details": ["base64 decode failed"]
  }
}
```

### Non-goals for MVP v1
- No persistence/storage of builds.
- No authentication.
- No recommendation endpoints.

Deliverable:
- A written DTO schema (above) agreed by FE/BE.

---

## Phase 2 — Backend Implementation (Spring Boot)

### 2.1 Create a parsing module/service
Create a service with a single responsibility: accept `exportCode`, return a parsed domain model.

Implementation constraint:
- Keep classes small (target <200 lines) by splitting decoding, XML parsing, mapping, and heuristics into separate components.

Suggested package layout:
- `...importing.pob`
  - `PobImportController`
  - `PobImportService`
  - `PobDecoder` (decode + decompress)
  - `PobXmlParser` (XML → domain)
  - `dto/*` (request/response)
  - `model/*` (internal domain)

### 2.2 Decode & decompress PoB export code
PoB export codes are typically:
1. Base64 encoded
2. Compressed (commonly zlib/deflate)
3. Result is XML

Implementation steps:
- Validate input size (e.g., reject > 2–4 MB to prevent abuse).
- Normalize whitespace (trim).
- Base64 decode:
  - use `java.util.Base64` (be lenient about URL-safe variants if needed).
- Decompress:
  - try `InflaterInputStream` (zlib)
  - if that fails, try raw DEFLATE with `Inflater(true)`
- Convert bytes to UTF-8 string.

Output:
- `String pobXml`

### 2.3 Parse XML into a minimal domain model
Use a safe XML parser configuration:
- Disallow external entities / DTDs.
- Parse with standard JDK (`DocumentBuilderFactory`) or a safer wrapper.

Extraction targets (best effort):

#### Character: class and level
- Identify the XML nodes/attributes that contain character metadata.
- Map class strings to normalized values:
  - `Witch`, `Templar`, `Shadow`, `Duelist`, `Marauder`, `Ranger`, `Scion`
- Ascendancy is optional.

#### Equipment
- Parse item entries.
- For MVP v1, store:
  - slot (Weapon, Offhand, Helmet, Body Armour, Gloves, Boots, Belt, Ring 1/2, Amulet, Flask 1–5, etc.)
  - name (best-effort)
  - rarity (best-effort)
  - raw item text block

#### Main skill
This can be ambiguous; define a deterministic heuristic:
1. Extract all skill groups / gem links.
2. Identify active skill gems in each group.
3. Pick the group with the maximum number of linked gems (or maximum supports attached to a single active gem).
4. If ties:
   - prefer a group marked enabled/active (if metadata exists)
   - else prefer the highest gem level/quality if available
   - else first occurrence
5. Return:
   - main active skill gem name
   - list of support gem names linked to it
   - confidence: `HIGH | MEDIUM | LOW`
   - warnings describing ambiguity

### 2.4 Controller + DTO mapping
- `POST /api/import/pob`:
  - validate request body not null
  - call service
  - return response DTO

### 2.5 Error handling
- Add an exception hierarchy:
  - `InvalidPobExportCodeException`
  - `PobParseException`
- Add a `@ControllerAdvice` to map exceptions to the error JSON contract.

### 2.6 Logging & observability (minimal)
- Log parse failures with a correlation id.
- Do not log full export codes (they may contain character name/account-like info).

### 2.7 Testability-first structure
- Ensure parsing logic is exposed as pure functions/services that are easy to unit test (no controller coupling).
- Keep heuristics deterministic; return warnings instead of relying on logs.

Deliverables:
- Working endpoint producing deterministic JSON for known fixtures.

---

## Phase 3 — Frontend Implementation (Vue)

### 3.1 UI/UX requirements (MVP v1)
Single view is sufficient:
- A multiline text area for the export code.
- A primary action button: “Import”.
- A results area showing:
  - class, level
  - main skill name + support gems
  - equipment list by slot
- Error state:
  - show API error message
  - keep the text area contents
- Loading state:
  - disable button while request is pending

### 3.2 Component structure
- `PobImportView` (page)
  - `PobImportForm` (textarea + submit)
  - `PobImportResult` (renders parsed JSON nicely)

Implementation constraint:
- Keep each component/module small (<200 lines) by extracting API calls and formatting into helpers.

### 3.3 API client
- Create a small API wrapper:
  - `importPob(exportCode: string) → Promise<ImportResponse>`
- Handle:
  - base URL from environment config
  - `400` error mapping to user message

### 3.4 Data validation (frontend)
- If text area is empty, block submit and show a simple validation message.
- No client-side parsing required.

Deliverables:
- User can paste code → click import → see parsed output.

---

## Phase 4 — Testing Strategy

### Backend tests (JUnit + Mockito)
Goal: cover parsing business logic with **≥80% unit test coverage**.

1. Unit tests (fast)
  - `PobDecoder`:
    - base64 decode (standard + URL-safe if supported)
    - decompress zlib success path
    - decompress raw-deflate fallback path
    - invalid payloads raise `InvalidPobExportCodeException`
  - `PobXmlParser`:
    - extracts class and level for representative XML fixtures
    - extracts equipment slots + preserves raw item text
  - main-skill heuristic:
    - deterministic selection on tie cases
    - confidence + warnings emitted correctly

2. Integration tests
  - `POST /api/import/pob` with fixture export codes
  - validate response shape and key fields

3. Security/robustness tests
  - exportCode size limit enforced
  - XML parser hardened against XXE/DTD

### Frontend tests (Cypress end-to-end)
Goal: ensure the primary user flow is covered by **e2e tests**.

Minimum Cypress scenarios:
1. Happy path
  - paste a valid export code
  - click Import
  - verify class/level/main skill/equipment are rendered
2. Error path
  - paste invalid export code
  - click Import
  - verify friendly error message is shown
3. Loading behavior
  - intercept the API call with a delay
  - verify button disabled/loading state during request

---

## Phase 5 — Local Dev & Deployment Notes

### Local dev workflow
- Start backend (Spring Boot) and frontend (Vue dev server).
- Configure CORS (or proxy via dev server) for `POST /api/import/pob`.

### Docker (optional for MVP v1)
- If a `docker compose` setup exists elsewhere:
  - ensure backend port is exposed
  - ensure frontend can reach backend hostname

---

## Milestones & Estimated Effort
- M1: API contract agreed + fixtures collected (0.5 day)
- M2: Backend PoB decode/decompress + XML parsing (1–2 days)
- M3: Main skill heuristic + response DTO + errors (0.5–1 day)
- M4: Frontend import page + result rendering (0.5–1 day)
- M5: Tests + hardening (0.5–1 day)

Total: ~3–6 working days depending on existing scaffolding.

---

## Open Questions (Answer before coding)
1. Where are backend/frontend repositories located (since not present in this repo)?
2. What API base path conventions exist (e.g., `/api/v1`)?
3. Should the backend return raw XML for debugging (recommended: no) or only structured fields?
4. Is there an existing build identifier concept (`buildId`) that the import should integrate with?

---

## Acceptance Checklist
- [ ] Text area accepts PoB export code
- [ ] `POST /api/import/pob` returns parsed JSON for valid inputs
- [ ] UI shows class, level, equipment, main skill
- [ ] Invalid input yields friendly error
- [ ] Main skill selection is deterministic and includes confidence/warnings
- [ ] Backend unit tests meet ≥80% business-logic coverage
- [ ] Cypress e2e tests cover happy-path + error-path + loading behavior

# M1: Project Setup & PoB Parser

**Timeline:** Week 1
**Phase:** 1 (Engine-Only MVP)
**Priority:** P0 — MVP Blocker
**PRD Reference:** FR-1 (Path of Building Import)

---

## Objective

Bootstrap the project infrastructure and implement client-side PoB code parsing so users can paste a Path of Building export and see structured build data.

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | React + Vite + TypeScript | React 19, Vite 6, TS 5.7 |
| Styling | Tailwind CSS | v4 |
| Routing | React Router | v7 |
| PoB decode | pako + fast-xml-parser | pako ^2.1, fast-xml-parser ^4.5 |
| Backend | Python + FastAPI | Python 3.12, FastAPI ^0.115 |
| Package manager (backend) | uv | latest |
| HTTP client (backend) | httpx | ^0.28 |
| Database | PostgreSQL | 17 |
| Container | Docker + Docker Compose | Compose v2 |

---

## Directory Structure

```
home-of-exile/
├── frontend/                          # Vite + React app
│   ├── src/
│   │   ├── components/                # Shared UI components
│   │   ├── hooks/                     # Custom React hooks
│   │   ├── lib/
│   │   │   ├── pob/
│   │   │   │   ├── decode.ts          # decodePobCode()
│   │   │   │   ├── parse.ts           # parsePobXml()
│   │   │   │   └── types.ts           # PobXml, BuildData, Item, etc.
│   │   │   └── repoe/
│   │   │       ├── types.ts           # RePoE TypeScript types
│   │   │       └── loader.ts          # loadBaseItems(), loadGems(), loadMods()
│   │   ├── pages/
│   │   │   ├── HomePage.tsx
│   │   │   └── BuildPage.tsx
│   │   ├── types/                     # Global shared types
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tsconfig.app.json
│   ├── .eslintrc.cjs
│   └── package.json
│
├── backend/                           # FastAPI app
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       └── health.py          # GET /health
│   │   ├── core/
│   │   │   └── config.py              # Settings (pydantic-settings)
│   │   ├── models/
│   │   │   └── repoe.py               # Pydantic models for RePoE data
│   │   ├── services/
│   │   │   └── poe_ninja.py           # PoeNinjaClient
│   │   └── main.py                    # FastAPI app factory, CORS, router mount
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
│
├── data/
│   └── repoe/
│       ├── base_items.json
│       ├── gems.json
│       └── mods.json
│
├── scripts/
│   └── ingest_repoe.py                # Downloads RePoE data files
│
├── docker-compose.yml
├── .env.example
└── .github/
    └── workflows/
        └── ci.yml
```

---

## Deliverables

### D1.1: Project Scaffolding

**Frontend (React + Vite + TypeScript)**

- [ ] `npm create vite@latest frontend -- --template react-ts`
- [ ] Configure `tsconfig.app.json`: `strict: true`, `paths` alias `@/*` → `src/*`
- [ ] Configure ESLint (`@typescript-eslint`, `eslint-plugin-react-hooks`) and Prettier
- [ ] Install and configure Tailwind CSS v4 (`@tailwindcss/vite` plugin)
- [ ] Install React Router v7; add `<BrowserRouter>` in `main.tsx`
- [ ] Create placeholder `HomePage` and `BuildPage` with route definitions
- [ ] Add `vite.config.ts` proxy: `/api` → `http://localhost:8000`

**Backend (Python FastAPI)**

- [ ] `uv init backend && uv add fastapi uvicorn[standard] httpx pydantic-settings`
- [ ] Create `app/main.py` with `CORSMiddleware` allowing `http://localhost:5173`
- [ ] Implement `GET /health` returning `{ "status": "ok", "version": "0.1.0" }`
- [ ] Create `app/core/config.py` using `pydantic-settings` (`BaseSettings`), reads from `.env`
- [ ] Write `Dockerfile` (base: `python:3.12-slim`; use `uv` to install deps; expose 8000)

**Infrastructure**

- [ ] Write `docker-compose.yml` with three services:
  - `frontend`: `node:22-alpine`, mounts `./frontend`, runs `npm run dev`, port 5173
  - `backend`: built from `./backend/Dockerfile`, port 8000, depends on `db`
  - `db`: `postgres:17-alpine`, volume `pgdata`, env from `.env`
- [ ] Write `.env.example`:
  ```
  POSTGRES_USER=hoe
  POSTGRES_PASSWORD=hoe
  POSTGRES_DB=hoe
  DATABASE_URL=postgresql://hoe:hoe@db:5432/hoe
  POE_NINJA_LEAGUE=Settlers
  LUAJIT_POOL_SIZE=2
  ```
- [ ] Add `.github/workflows/ci.yml`:
  - Jobs: `frontend-lint` (`npm run lint`, `tsc --noEmit`), `backend-lint` (`ruff check`, `mypy`)
  - Triggers: push to `main`/`dev`, pull requests

### D1.2: PoB Code Parser (Client-Side)

**File:** `frontend/src/lib/pob/decode.ts`

- [ ] `uv add` / `npm install pako@^2.1 fast-xml-parser@^4.5 @types/pako`
- [ ] Implement `decodePobCode(code: string): string` (returns raw XML):
  1. Normalise URL-safe base64: replace `-`→`+`, `_`→`/`, add `=` padding
  2. `atob()` → `Uint8Array` → `pako.inflate()` → UTF-8 decode
  3. Throw `PobDecodeError` with message `"Invalid PoB code: <reason>"` on any failure
- [ ] Implement `parsePobXml(xml: string): BuildData`:
  - Parse with `XMLParser({ ignoreAttributes: false, attributeNamePrefix: '@_' })`
  - Map XML paths to `BuildData` fields (see schema table below)
  - All numeric fields default to `0` if missing; all string fields default to `''`
  - Throw `PobParseError` with message `"Unsupported PoB version — please export from v2.35+"` if `<PathOfBuilding>` root is absent

**PoB XML → `BuildData` Mapping**

| `BuildData` field | XML path | Attribute / content |
|---|---|---|
| `characterName` | `PathOfBuilding.Build` | `@_characterName` |
| `class` | `PathOfBuilding.Build` | `@_className` |
| `ascendancy` | `PathOfBuilding.Build` | `@_ascendClassName` |
| `level` | `PathOfBuilding.Build` | `@_level` (parse int) |
| `bandit` | `PathOfBuilding.Build` | `@_bandit` |
| `mainSkill` | `PathOfBuilding.Build` | `@_mainSocketGroup` → resolve to skill name via `Skills.Skill[n].Gem[0].nameSpec` |
| `stats.life` | `PathOfBuilding.Build.PlayerStat` where `@_stat="Life"` | `@_value` (parse float) |
| `stats.energyShield` | `PathOfBuilding.Build.PlayerStat` where `@_stat="EnergyShield"` | `@_value` |
| `stats.dps` | `PathOfBuilding.Build.PlayerStat` where `@_stat="CombinedDPS"` | `@_value` |
| `stats.fireRes` | `PathOfBuilding.Build.PlayerStat` where `@_stat="FireResist"` | `@_value` |
| `stats.coldRes` | `PathOfBuilding.Build.PlayerStat` where `@_stat="ColdResist"` | `@_value` |
| `stats.lightningRes` | `PathOfBuilding.Build.PlayerStat` where `@_stat="LightningResist"` | `@_value` |
| `stats.chaosRes` | `PathOfBuilding.Build.PlayerStat` where `@_stat="ChaosResist"` | `@_value` |
| `passiveTree` | `PathOfBuilding.Tree.Spec.nodes` | space-separated node IDs → `number[]` |
| `items` | `PathOfBuilding.Items.Item[*]` | see Item mapping below |
| `skillGroups` | `PathOfBuilding.Skills.Skill[*]` | see SkillGroup mapping below |

**Item XML → `Item` mapping** (each `<Item id="N">` element contains raw item text)

| `Item` field | Source |
|---|---|
| `name` | Line 1 of item text if unique/rare, else empty |
| `baseName` | Last non-mod line before mods block |
| `slot` | `PathOfBuilding.Items.Slot[@_name=X][@_itemId=N]` → X |
| `rarity` | `Rarity:` line in item text |
| `levelReq` | `LevelReq:` line in item text (parse int) |
| `attrReq` | `Requires` block: `Str X`, `Dex X`, `Int X` |
| `sockets` | `Sockets:` line (e.g., `R-R G-G B`) → normalise to `"R-R-G-G-B"` |
| `mods` | All lines after the `----` separator following `Sockets:` |

**SkillGroup XML → `SkillGroup` mapping**

- `slot`: `<Skill slot="X">` → `@_slot` (e.g., `"Weapon 1"`)
- `enabled`: `@_enabled === "true"`
- `gems`: each `<Gem>` child → `{ skillId, nameSpec, level, quality, enabled, isSupport }`

- [ ] Write unit tests in `frontend/src/lib/pob/__tests__/`:
  - `decode.test.ts`: round-trip with a known PoB code fixture
  - `parse.test.ts`: fixture XML → assert each `BuildData` field

### D1.3: RePoE Data Ingestion

**RePoE release URL:** `https://raw.githubusercontent.com/brather1ng/RePoE/master/RePoE/data/`

- [ ] Write `scripts/ingest_repoe.py` (plain Python, no dependencies beyond stdlib + `httpx`):
  - Downloads `base_items.json`, `gems.json`, `mods.json` to `data/repoe/`
  - Prints download size and SHA-256 of each file
  - Usage: `uv run scripts/ingest_repoe.py`
- [ ] Commit downloaded files to `data/repoe/` (they are static reference data, ~20 MB total)
- [ ] Create `frontend/src/lib/repoe/types.ts`:

```typescript
interface RePoEBaseItem {
  name: string;
  item_class: string;
  requirements: { level?: number; str?: number; dex?: number; int?: number };
  implicit_mods: string[];
  tags: string[];
}

interface RePoEGem {
  base_item: { display_name: string; release_state: string } | null;
  tags: string[];
  is_support: boolean;
}

interface RePoEMod {
  name: string;
  generation_type: 'prefix' | 'suffix' | 'corrupted' | string;
  groups: string[];
  stats: { id: string; min: number; max: number }[];
  spawn_weights: { tag: string; weight: number }[];
}
```

- [ ] Create `backend/app/models/repoe.py` (Pydantic v2 models mirroring the TypeScript types above)
- [ ] Create `backend/app/services/repoe_loader.py`:
  - `load_base_items() -> dict[str, RePoEBaseItem]` — key is item ID
  - `load_gems() -> dict[str, RePoEGem]` — key is gem ID
  - `load_mods() -> dict[str, RePoEMod]` — key is mod ID
  - Files read from path configured in `Settings.repoe_data_dir` (default: `../../data/repoe`)
  - Cache with `@functools.lru_cache`

### D1.4: poe.ninja Price Cache

**Base URL:** `https://poe.ninja/api/data/`

**Relevant endpoints:**

| Type | Endpoint | Notes |
|---|---|---|
| Currency | `CurrencyOverview?league=X&type=Currency` | Includes chaos orb, divine orb |
| Unique weapons | `ItemOverview?league=X&type=UniqueWeapon` | |
| Unique armour | `ItemOverview?league=X&type=UniqueArmour` | |
| Unique accessories | `ItemOverview?league=X&type=UniqueAccessory` | |
| Unique flasks | `ItemOverview?league=X&type=UniqueFlask` | |
| Unique jewels | `ItemOverview?league=X&type=UniqueJewel` | |
| Skill gems | `ItemOverview?league=X&type=SkillGem` | |

- [ ] Implement `backend/app/services/poe_ninja.py`:
  - `class PoeNinjaClient` with `httpx.AsyncClient` (timeout 10 s)
  - `async def get_item_prices(league: str) -> dict[str, PoeNinjaPrice]` — key is item name
  - `async def get_currency_prices(league: str) -> dict[str, float]` — key is currency name, value is chaos equivalent
  - In-memory cache: `dict[str, tuple[datetime, Any]]`; TTL = 1 hour; keyed by `(league, type)`
  - Return `None` for any item not found in cache/response
  - Catch `httpx.RequestError` and log warning; return empty dict (graceful fallback)
  - `X-Powered-By: home-of-exile` request header (API etiquette)
- [ ] Add `GET /api/v1/prices/{league}` endpoint that calls `PoeNinjaClient` and returns a summary (used for frontend league price context)
- [ ] League name defaults to `Settings.poe_ninja_league` if not specified

---

## TypeScript Types

**File:** `frontend/src/lib/pob/types.ts`

```typescript
// ---- Primitive types ----

type ItemRarity = 'normal' | 'magic' | 'rare' | 'unique';

type ItemSlot =
  | 'Helmet'
  | 'Body Armour'
  | 'Gloves'
  | 'Boots'
  | 'Weapon'
  | 'Weapon 2'
  | 'Shield'
  | 'Amulet'
  | 'Ring'
  | 'Ring 2'
  | 'Belt'
  | 'Flask'
  | 'Jewel';

type Bandit = 'None' | 'Oak' | 'Kraityn' | 'Alira';

// ---- Core domain types ----

interface BuildStats {
  life: number;
  energyShield: number;
  dps: number;              // CombinedDPS stat from PoB
  fireRes: number;
  coldRes: number;
  lightningRes: number;
  chaosRes: number;
}

interface AttrReq {
  str: number;
  dex: number;
  int: number;
}

interface Item {
  id: number;               // <Item id="N"> from XML
  name: string;             // unique/rare name; '' for normal/magic
  baseName: string;
  slot: ItemSlot;
  rarity: ItemRarity;
  levelReq: number;
  attrReq: AttrReq;
  sockets: string;          // e.g. "R-R-G G-B" (- = linked, space = unlinked)
  mods: string[];           // raw mod lines from item text
  corrupted: boolean;
}

interface Gem {
  skillId: string;          // e.g. "Metadata/Items/Gems/SkillGemFireball"
  nameSpec: string;         // display name, e.g. "Fireball"
  level: number;
  quality: number;
  enabled: boolean;
  isSupport: boolean;
}

interface SkillGroup {
  slot: string;             // e.g. "Weapon 1", "Body Armour"
  label: string;            // optional user label from PoB
  enabled: boolean;
  gems: Gem[];
  mainActiveGemIndex: number; // index into gems[] of the primary active skill
}

interface BuildData {
  characterName: string;
  class: string;
  ascendancy: string;
  level: number;
  bandit: Bandit;
  mainSkill: string;        // display name of the primary active skill
  stats: BuildStats;
  passiveTree: number[];    // allocated node IDs
  items: Map<ItemSlot, Item>;
  skillGroups: SkillGroup[];
}

// ---- Parser errors ----

class PobDecodeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PobDecodeError';
  }
}

class PobParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PobParseError';
  }
}
```

**File:** `frontend/src/lib/poe-ninja/types.ts`

```typescript
interface PoeNinjaPrice {
  name: string;
  chaosValue: number;
  divineValue: number;
  listingCount: number;
}
```

---

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| 1 | `docker compose up` starts all three services with no errors | Manual test |
| 2 | Frontend loads at `localhost:5173`; routes `/` and `/build` render without console errors | Manual test |
| 3 | Backend responds `200 { "status": "ok" }` to `GET localhost:8000/health` | `curl` test |
| 4 | `decodePobCode()` round-trips a known v2.40 PoB fixture without error | Unit test |
| 5 | `parsePobXml()` extracts `class`, `level`, and `ascendancy` from fixture | Unit test |
| 6 | `parsePobXml()` returns correct `stats.life` and `stats.dps` from fixture | Unit test |
| 7 | `parsePobXml()` returns all `items` with non-empty `mods[]` for rare/unique items | Unit test |
| 8 | `parsePobXml()` returns `skillGroups` with correct `gems` and `isSupport` flags | Unit test |
| 9 | `decodePobCode('')` throws `PobDecodeError` with a user-readable message | Unit test |
| 10 | `parsePobXml('<NotPoB/>')` throws `PobParseError` referencing minimum version | Unit test |
| 11 | `data/repoe/base_items.json`, `gems.json`, `mods.json` are present and valid JSON | `python -m json.tool` |
| 12 | `RePoELoader.load_base_items()` returns > 500 entries | Unit test |
| 13 | `PoeNinjaClient.get_item_prices('Settlers')` returns a non-empty dict | Integration test |
| 14 | `PoeNinjaClient` returns `{}` (not an exception) when poe.ninja is unreachable | Unit test (httpx mock) |
| 15 | CI workflow runs lint + type-check and passes on a clean branch | GitHub Actions |

---

## Dependencies

- **Upstream:** None (first milestone)
- **External:** poe.ninja API, RePoE data on GitHub
- **Frontend packages:** `pako ^2.1`, `@types/pako`, `fast-xml-parser ^4.5`
- **Backend packages:** `fastapi ^0.115`, `uvicorn[standard]`, `httpx ^0.28`, `pydantic-settings ^2.7`
- **Reference repos:** `brather1ng/RePoE` (data), `Davenads/poeninjaAPI-2025` (API docs)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| PoB XML schema varies between versions | Test with fixture exports from v2.35, v2.38, v2.40; all numeric/string fields default gracefully |
| `PlayerStat` key names may differ by build type | Log unknown stat keys in development; document known keys in `decode.ts` |
| poe.ninja API undocumented / rate-limited | Reference `Davenads/poeninjaAPI-2025`; 1-hour TTL; polite `User-Agent` header |
| RePoE data lags behind new league patch | Script is re-runnable; CI can alert if hash changes; data is committed so builds don't break offline |

---

## Definition of Done

- All acceptance criteria pass
- No TypeScript errors (`tsc --noEmit` clean)
- No Python type errors (`mypy app/` clean)
- Code reviewed and merged to `dev`
- `docker compose up --build` works from a clean clone (no pre-existing volumes)
- A real PoB export code (v2.40) can be pasted into the UI and `BuildData` logged to console with all fields populated

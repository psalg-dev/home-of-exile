# M6: Feedback System & MVP Launch

**Timeline:** Week 6
**Phase:** 1 (Engine-Only MVP)
**Priority:** P0 (Feedback: P1, Launch: P0)
**PRD Reference:** FR-3 (Recommendation Feedback Loop), NFR-3/4 (Scalability, Reliability)

---

## Objective

Implement the recommendation feedback system, wire up the full end-to-end pipeline, harden for production, and deploy the MVP.

---

## Deliverables

### D6.1: Feedback Database Schema

- [ ] PostgreSQL tables:

```sql
CREATE TABLE feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Build context
    archetype_damage TEXT NOT NULL,
    archetype_defense TEXT NOT NULL,
    archetype_playstyle TEXT NOT NULL,
    character_level INT NOT NULL,
    league TEXT NOT NULL,
    -- Recommendation context
    recommendation_rank INT NOT NULL,
    recommendation_category TEXT NOT NULL,
    slot TEXT NOT NULL,
    suggested_item TEXT NOT NULL,
    dps_delta FLOAT,
    ehp_delta FLOAT,
    price_divine FLOAT,
    -- Feedback
    vote TEXT NOT NULL CHECK (vote IN ('up', 'down')),
    -- Tracking
    session_id TEXT NOT NULL
);

CREATE TABLE trade_clicks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id TEXT NOT NULL,
    recommendation_rank INT NOT NULL,
    suggested_item TEXT NOT NULL,
    league TEXT NOT NULL
);

CREATE INDEX idx_feedback_league ON feedback(league);
CREATE INDEX idx_feedback_archetype ON feedback(archetype_damage, archetype_defense);
CREATE INDEX idx_trade_clicks_league ON trade_clicks(league);
```

### D6.2: Feedback API Endpoints

- [ ] `POST /api/v1/feedback`
  - Input: `{ session_id, recommendation_rank, vote: "up"|"down", context: {...} }`
  - Stores feedback with full build/recommendation context
  - Rate limit: max 10 feedback submissions per session
- [ ] `POST /api/v1/track/trade-click`
  - Input: `{ session_id, recommendation_rank, suggested_item, league }`
  - Lightweight implicit signal tracking
- [ ] `GET /api/v1/feedback/stats` (internal/admin)
  - Returns aggregate thumbs-up/down rates by archetype, slot, league

### D6.3: Frontend Feedback Integration

- [ ] Wire 👍 / 👎 buttons on recommendation cards
  - Click sends `POST /api/v1/feedback` with full context
  - Visual state: button highlights after click, disabled after voting
  - Only one vote per recommendation per session
- [ ] Track trade link clicks:
  - Intercept "Search on Trade" click → fire `POST /api/v1/track/trade-click` → open trade URL
- [ ] Generate session ID (UUID) on page load, persist in sessionStorage

### D6.4: Feedback Weight Adjustment (Batch)

- [ ] Implement `adjust_weights(league: str)` offline script
  - Query feedback table for current league
  - Group by `(archetype, slot, category)`
  - Calculate thumbs-up ratio per group
  - Adjust scoring weights: boost categories with high approval, dampen those with low approval
  - Output: updated weights JSON file
- [ ] Schedule: designed to run weekly (cron or manual trigger for MVP)
- [ ] League-tagged: weights are league-specific; expire when new league starts

### D6.5: End-to-End Integration

- [ ] Create unified `POST /api/v1/analyze` endpoint that orchestrates:
  1. Receive `BuildData` from frontend
  2. Detect archetype (M3)
  3. Generate candidates (M3)
  4. Run simulation loop (M4)
  5. Rank and build recommendations (M4)
  6. Return `AnalysisResponse` with build summary + 5 recommendations
- [ ] Add request validation and error handling at each step
- [ ] Add structured logging for debugging and analytics
- [ ] End-to-end integration tests with real PoB codes

### D6.6: Production Hardening

- [ ] **Rate limiting:** 10 analyses per IP per hour (configurable)
- [ ] **CORS:** Lock down to production frontend domain
- [ ] **Error handling:** Catch-all exception handler returning structured JSON errors
- [ ] **Health checks:**
  - `GET /health` — app alive
  - `GET /health/ready` — app + LuaJIT pool + PostgreSQL all healthy
- [ ] **Graceful degradation:**
  - If LuaJIT pool exhausted: return HTTP 503 with "Try again in a moment"
  - If poe.ninja unreachable: use cached prices (stale data warning)
  - If PostgreSQL down: skip feedback storage, analysis still works
- [ ] **Security:**
  - Input sanitization on PoB code (limit size: 500KB max)
  - No user-generated content reflected without escaping
  - HTTPS enforced in production

### D6.7: Deployment

- [ ] **Frontend:** Deploy to Vercel
  - Configure build: `npm run build`
  - Environment variables: `VITE_API_URL`
  - Custom domain setup (if available)
- [ ] **Backend:** Deploy to Render or Railway
  - Dockerfile with LuaJIT + FastAPI + PoB engine
  - Environment variables: `DATABASE_URL`, `LUAJIT_POOL_SIZE`, `POE_NINJA_CACHE_TTL`
  - PostgreSQL managed instance
- [ ] **CI/CD:**
  - GitHub Actions: lint → type-check → unit tests → build → deploy
  - Staging environment for pre-production validation
- [ ] **Monitoring:**
  - Application logs (structured JSON)
  - Basic uptime monitoring (e.g., UptimeRobot or similar free tier)

---

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| 1 | User can vote 👍/👎 on each recommendation | Manual test |
| 2 | Vote is persisted in PostgreSQL with full context | Database query |
| 3 | Trade link clicks are tracked | Database query |
| 4 | User cannot vote twice on same recommendation in same session | Manual test |
| 5 | `POST /api/v1/analyze` returns 5 recommendations end-to-end | Integration test |
| 6 | Analysis completes in < 8s (P50) and < 15s (P95) | Load test |
| 7 | Rate limiter blocks 11th request from same IP within 1 hour | Integration test |
| 8 | App returns 503 gracefully when LuaJIT pool is exhausted | Fault injection |
| 9 | App works (minus feedback) when PostgreSQL is down | Fault injection |
| 10 | Frontend is live on production URL | Manual verification |
| 11 | Backend health check passes on production | `curl` test |
| 12 | Full flow works on production: paste code → see recommendations → vote | Smoke test |

---

## Dependencies

- **Upstream:** M1-M5 (all prior milestones)
- **Infrastructure:** Vercel account, Render/Railway account, PostgreSQL instance, domain (optional)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Docker image too large for free-tier hosting | Multi-stage build; strip unnecessary PoB assets |
| Cold start latency on serverless/container restart | Pre-warm LuaJIT pool; use always-on instance if budget allows |
| Low feedback volume makes weight adjustment noisy | Require minimum 50 votes per group before adjusting; fall back to defaults |
| Database costs | Start with free-tier PostgreSQL (e.g., Neon, Supabase); feedback data is small |

---

## Definition of Done

- MVP is live and publicly accessible
- Full user flow works end-to-end on production
- Feedback system stores votes and trade clicks
- Rate limiting and error handling are active
- CI/CD pipeline deploys on merge to main
- At least 3 diverse PoB codes tested successfully on production

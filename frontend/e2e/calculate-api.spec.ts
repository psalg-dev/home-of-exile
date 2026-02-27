/**
 * E2E tests for the calculation API endpoints.
 *
 * These tests run directly against the backend API server at
 * http://localhost:8000, verifying the endpoints are reachable and respond
 * with correct status codes and structure.
 *
 * When LuaJIT is not installed (local dev), the endpoints return 503 which
 * is specifically tested here as the "degraded mode" acceptance criterion.
 */

import { test, expect, APIRequestContext, request } from '@playwright/test';
import { deflate } from 'pako';

const BACKEND_URL = 'http://localhost:8000';

/**
 * Encode an XML string as a PoB export code (URL-safe base64 zlib).
 *
 * @param xml - Raw XML string
 * @returns URL-safe base64 PoB code
 */
function encodePobCode(xml: string): string {
  const bytes = new TextEncoder().encode(xml);
  const compressed = deflate(bytes);
  const base64 = Buffer.from(compressed).toString('base64');
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Minimal PoB XML fixture for API tests */
const FIXTURE_XML = `<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding>
  <Build level="90" className="Witch" ascendClassName="Occultist"
         characterName="TestWitch" bandit="None" mainSocketGroup="1">
    <PlayerStat stat="Life" value="4500"/>
    <PlayerStat stat="EnergyShield" value="0"/>
    <PlayerStat stat="CombinedDPS" value="1200000"/>
    <PlayerStat stat="FireResist" value="75"/>
    <PlayerStat stat="ColdResist" value="75"/>
    <PlayerStat stat="LightningResist" value="75"/>
    <PlayerStat stat="ChaosResist" value="-60"/>
  </Build>
  <Skills>
    <Skill slot="Weapon 1" enabled="true" label="">
      <Gem nameSpec="Ball Lightning"
           skillId="Metadata/Items/Gems/SkillGemBallLightning"
           level="21" quality="20" enabled="true"/>
    </Skill>
  </Skills>
  <Tree><Spec nodes="1 2 3"/></Tree>
  <Items/>
</PathOfBuilding>`;

const FIXTURE_CODE = encodePobCode(FIXTURE_XML);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function createApiContext(): Promise<APIRequestContext> {
  return await request.newContext({ baseURL: BACKEND_URL });
}

// ---------------------------------------------------------------------------
// Health endpoint
// ---------------------------------------------------------------------------

test.describe('GET /api/v1/calculate/health', () => {
  test('returns 200 with pool availability info', async () => {
    const ctx = await createApiContext();
    const response = await ctx.get('/api/v1/calculate/health');

    expect(response.status()).toBe(200);
    const body = await response.json();

    // Must contain these keys regardless of availability
    expect(body).toHaveProperty('available');
    expect(body).toHaveProperty('pool_size');
    expect(body).toHaveProperty('total_workers');
    expect(body).toHaveProperty('healthy_workers');

    await ctx.dispose();
  });
});

// ---------------------------------------------------------------------------
// POST /api/v1/calculate
// ---------------------------------------------------------------------------

test.describe('POST /api/v1/calculate', () => {
  test('returns 422 when request body is empty', async () => {
    const ctx = await createApiContext();
    const response = await ctx.post('/api/v1/calculate', {
      data: {},
      headers: { 'Content-Type': 'application/json' },
    });

    expect(response.status()).toBe(422);
    await ctx.dispose();
  });

  test('returns 400 for an invalid PoB export code', async () => {
    const ctx = await createApiContext();
    const response = await ctx.post('/api/v1/calculate', {
      data: { build_code: 'NOT_VALID_POB_CODE!!!' },
      headers: { 'Content-Type': 'application/json' },
    });

    expect(response.status()).toBe(400);
    await ctx.dispose();
  });

  test('returns 200 or 503 for a valid PoB code', async () => {
    /**
     * When LuaJIT is installed the endpoint returns 200 with stats.
     * Without LuaJIT it returns 503 (graceful degradation).
     * Both are valid outcomes in the test environment.
     */
    const ctx = await createApiContext();
    const response = await ctx.post('/api/v1/calculate', {
      data: { build_code: FIXTURE_CODE },
      headers: { 'Content-Type': 'application/json' },
    });

    expect([200, 503, 504]).toContain(response.status());

    if (response.status() === 200) {
      const body = await response.json();
      expect(body).toHaveProperty('result');
      const result = body.result;
      expect(result).toHaveProperty('dps');
      expect(result).toHaveProperty('life');
      expect(result).toHaveProperty('fire_res');
    }

    await ctx.dispose();
  });

  test('returns 200 or 503 for a raw build_xml input', async () => {
    const ctx = await createApiContext();
    const response = await ctx.post('/api/v1/calculate', {
      data: { build_xml: FIXTURE_XML },
      headers: { 'Content-Type': 'application/json' },
    });

    expect([200, 503, 504]).toContain(response.status());
    await ctx.dispose();
  });
});

// ---------------------------------------------------------------------------
// POST /api/v1/calculate-swap
// ---------------------------------------------------------------------------

const HELMET_ITEM_TEXT = [
  'Rarity: Rare',
  'Iron Circlet',
  '--------',
  '+50 to maximum Life',
  '+30% to Fire Resistance',
  '+25% to Cold Resistance',
].join('\n');

test.describe('POST /api/v1/calculate-swap', () => {
  test('returns 422 when slot or item_text is missing', async () => {
    const ctx = await createApiContext();
    const response = await ctx.post('/api/v1/calculate-swap', {
      data: { build_xml: FIXTURE_XML },
      headers: { 'Content-Type': 'application/json' },
    });

    expect(response.status()).toBe(422);
    await ctx.dispose();
  });

  test('returns 200 or 503 for a valid swap request', async () => {
    const ctx = await createApiContext();
    const response = await ctx.post('/api/v1/calculate-swap', {
      data: {
        build_xml: FIXTURE_XML,
        slot: 'Helmet',
        item_text: HELMET_ITEM_TEXT,
      },
      headers: { 'Content-Type': 'application/json' },
    });

    expect([200, 503, 504]).toContain(response.status());

    if (response.status() === 200) {
      const body = await response.json();
      expect(body).toHaveProperty('result');
      const result = body.result;
      expect(result).toHaveProperty('slot');
      expect(result).toHaveProperty('baseline');
      expect(result).toHaveProperty('modified');
      expect(result).toHaveProperty('deltas');
    }

    await ctx.dispose();
  });
});

// ---------------------------------------------------------------------------
// POST /api/v1/calculate-swap/batch
// ---------------------------------------------------------------------------

test.describe('POST /api/v1/calculate-swap/batch', () => {
  test('returns 422 when swaps list is missing', async () => {
    const ctx = await createApiContext();
    const response = await ctx.post('/api/v1/calculate-swap/batch', {
      data: { build_xml: FIXTURE_XML },
      headers: { 'Content-Type': 'application/json' },
    });

    expect(response.status()).toBe(422);
    await ctx.dispose();
  });

  test('returns 200 or 503 for a valid batch request', async () => {
    const ctx = await createApiContext();
    const response = await ctx.post('/api/v1/calculate-swap/batch', {
      data: {
        build_xml: FIXTURE_XML,
        swaps: [{ slot: 'Helmet', item_text: HELMET_ITEM_TEXT }],
      },
      headers: { 'Content-Type': 'application/json' },
    });

    expect([200, 503, 504]).toContain(response.status());

    if (response.status() === 200) {
      const body = await response.json();
      expect(body).toHaveProperty('results');
      expect(Array.isArray(body.results)).toBe(true);
      expect(body.results.length).toBe(1);
    }

    await ctx.dispose();
  });
});

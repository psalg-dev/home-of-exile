/**
 * E2E tests for the candidate pool pipeline API endpoint.
 *
 * Tests run directly against the backend API at http://localhost:8000.
 * They verify the /api/v1/candidates endpoint is reachable, returns the
 * correct structure, and respects slot filtering.
 *
 * Note: poe.ninja pricing may return empty results in tests (network
 * unavailable or rate-limited) — the endpoint must still succeed and
 * return archetype + item/gem candidates from RePoE.
 */

import { test, expect, APIRequestContext, request } from '@playwright/test';

const BACKEND_URL = 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Shared fixture — a minimal, fully-described build
// ---------------------------------------------------------------------------

/** A Level-80 Occultist cold caster build used across tests. */
const COLD_CASTER_BUILD = {
  class: 'Witch',
  ascendancy: 'Occultist',
  level: 80,
  main_skill: 'Ice Nova',
  stats: {
    life: 4000,
    energy_shield: 2000,
    dps: 800000,
    fire_res: 75,
    cold_res: 75,
    lightning_res: 75,
    chaos_res: -60,
  },
  attrs: { str: 80, dex: 90, int: 250 },
  passive_tree: [],
  items: {},
  skill_groups: [
    {
      slot: 'Body Armour',
      label: '',
      enabled: true,
      main_active_gem_index: 0,
      gems: [
        {
          name_spec: 'Ice Nova',
          skill_id: 'Metadata/Items/Gems/SkillGemIceNova',
          level: 20,
          quality: 20,
          enabled: true,
          is_support: false,
        },
        {
          name_spec: 'Spell Echo Support',
          skill_id: 'Metadata/Items/Gems/SupportSpellEcho',
          level: 20,
          quality: 20,
          enabled: true,
          is_support: true,
        },
        {
          name_spec: 'Added Cold Damage Support',
          skill_id: 'Metadata/Items/Gems/SupportAddedColdDamage',
          level: 20,
          quality: 20,
          enabled: true,
          is_support: true,
        },
      ],
    },
  ],
};

/** A Level-90 Juggernaut physical melee build. */
const PHYSICAL_MELEE_BUILD = {
  class: 'Marauder',
  ascendancy: 'Juggernaut',
  level: 90,
  main_skill: 'Cyclone',
  stats: {
    life: 6500,
    energy_shield: 100,
    dps: 2000000,
    fire_res: 75,
    cold_res: 75,
    lightning_res: 75,
    chaos_res: -20,
  },
  attrs: { str: 240, dex: 110, int: 60 },
  passive_tree: [],
  items: {},
  skill_groups: [
    {
      slot: 'Weapon',
      label: '',
      enabled: true,
      main_active_gem_index: 0,
      gems: [
        {
          name_spec: 'Cyclone',
          skill_id: 'Metadata/Items/Gems/SkillGemCyclone',
          level: 21,
          quality: 20,
          enabled: true,
          is_support: false,
        },
        {
          name_spec: 'Melee Physical Damage Support',
          skill_id: 'Metadata/Items/Gems/SupportMeleePhysicalDamage',
          level: 20,
          quality: 20,
          enabled: true,
          is_support: true,
        },
      ],
    },
  ],
};

async function createApiContext(): Promise<APIRequestContext> {
  return await request.newContext({ baseURL: BACKEND_URL });
}

// ---------------------------------------------------------------------------
// POST /api/v1/candidates — structural checks
// ---------------------------------------------------------------------------

test.describe('POST /api/v1/candidates', () => {
  test('returns 200 with cold caster build', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: COLD_CASTER_BUILD,
        slot: 'Helmet',
        league: 'TestLeague',
      },
    });

    expect(response.status()).toBe(200);
    await ctx.dispose();
  });

  test('response contains archetype with required fields', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: COLD_CASTER_BUILD,
        slot: 'Helmet',
        league: 'TestLeague',
      },
    });

    expect(response.status()).toBe(200);
    const body = await response.json();

    expect(body).toHaveProperty('archetype');
    expect(body.archetype).toHaveProperty('damage_type');
    expect(body.archetype).toHaveProperty('defense_style');
    expect(body.archetype).toHaveProperty('playstyle');

    await ctx.dispose();
  });

  test('archetype for cold caster is cold/caster', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: COLD_CASTER_BUILD,
        slot: 'Helmet',
        league: 'TestLeague',
      },
    });

    const body = await response.json();
    expect(body.archetype.damage_type).toBe('cold');
    expect(body.archetype.playstyle).toBe('caster');

    await ctx.dispose();
  });

  test('archetype for physical melee build is physical/melee', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: PHYSICAL_MELEE_BUILD,
        slot: 'Helmet',
        league: 'TestLeague',
      },
    });

    const body = await response.json();
    expect(body.archetype.damage_type).toBe('physical');
    expect(body.archetype.playstyle).toBe('melee');

    await ctx.dispose();
  });

  test('response contains item_candidates array', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: COLD_CASTER_BUILD,
        slot: 'Helmet',
        league: 'TestLeague',
      },
    });

    const body = await response.json();
    expect(body).toHaveProperty('item_candidates');
    expect(Array.isArray(body.item_candidates)).toBe(true);

    await ctx.dispose();
  });

  test('response contains gem_candidates array', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: COLD_CASTER_BUILD,
        slot: 'Helmet',
        league: 'TestLeague',
      },
    });

    const body = await response.json();
    expect(body).toHaveProperty('gem_candidates');
    expect(Array.isArray(body.gem_candidates)).toBe(true);

    await ctx.dispose();
  });

  test('slot filter limits item_candidates to requested slot', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: COLD_CASTER_BUILD,
        slot: 'Gloves',
        league: 'TestLeague',
      },
    });

    const body = await response.json();
    for (const slotResult of body.item_candidates) {
      expect(slotResult.slot).toBe('Gloves');
    }

    await ctx.dispose();
  });

  test('all item candidates have at most 20 entries per slot', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: COLD_CASTER_BUILD,
        league: 'TestLeague',
        // no slot filter — run all slots
      },
    });

    const body = await response.json();
    for (const slotResult of body.item_candidates) {
      expect(slotResult.candidates.length).toBeLessThanOrEqual(20);
    }

    await ctx.dispose();
  });

  test('each item candidate has required fields', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: COLD_CASTER_BUILD,
        slot: 'Helmet',
        league: 'TestLeague',
      },
    });

    const body = await response.json();
    const helmetSlot = body.item_candidates.find(
      (s: { slot: string }) => s.slot === 'Helmet'
    );

    if (helmetSlot && helmetSlot.candidates.length > 0) {
      const first = helmetSlot.candidates[0];
      expect(first).toHaveProperty('slot');
      expect(first).toHaveProperty('base_name');
      expect(first).toHaveProperty('level_req');
      expect(first).toHaveProperty('rarity');
      expect(first).toHaveProperty('relevance_score');
      expect(first).toHaveProperty('source');
    }

    await ctx.dispose();
  });

  test('returns 422 for missing build field', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: { league: 'TestLeague' },
    });

    expect(response.status()).toBe(422);
    await ctx.dispose();
  });

  test('returns 422 for build with level 0', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: { level: 0, class: 'Witch' },
        league: 'TestLeague',
      },
    });

    expect(response.status()).toBe(422);
    await ctx.dispose();
  });

  test('all slots processed when no slot filter given', async () => {
    const ctx = await createApiContext();

    const response = await ctx.post('/api/v1/candidates', {
      data: {
        build: COLD_CASTER_BUILD,
        league: 'TestLeague',
      },
    });

    const body = await response.json();
    // Should have 10+ slot results (one per equipment slot)
    expect(body.item_candidates.length).toBeGreaterThanOrEqual(10);

    await ctx.dispose();
  });
});

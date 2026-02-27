/**
 * API client for the M4 recommendation engine.
 *
 * Converts the camelCase frontend BuildData to the snake_case format
 * expected by the backend ``POST /api/v1/recommendations`` endpoint.
 */

import type { BuildData, Item, SkillGroup, Gem } from '@/lib/pob/types';
import type { RecommendResponse } from './types';

/** Base URL for the backend API (configurable via env). */
const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// BuildData → backend wire format converters
// ---------------------------------------------------------------------------

function serializeGem(gem: Gem): Record<string, unknown> {
  return {
    skill_id: gem.skillId,
    name_spec: gem.nameSpec,
    level: gem.level,
    quality: gem.quality,
    enabled: gem.enabled,
    is_support: gem.isSupport,
  };
}

function serializeSkillGroup(group: SkillGroup): Record<string, unknown> {
  return {
    slot: group.slot,
    label: group.label,
    enabled: group.enabled,
    gems: group.gems.map(serializeGem),
    main_active_gem_index: group.mainActiveGemIndex,
  };
}

function serializeItem(item: Item): Record<string, unknown> {
  return {
    name: item.name,
    base_name: item.baseName,
    slot: item.slot,
    rarity: item.rarity,
    level_req: item.levelReq,
    attr_req: {
      str: item.attrReq.str,
      dex: item.attrReq.dex,
      int: item.attrReq.int,
    },
    sockets: item.sockets,
    mods: item.mods,
    corrupted: item.corrupted,
  };
}

/**
 * Serialize a frontend BuildData to the snake_case format expected by the
 * backend Pydantic models.
 *
 * @param build - Frontend BuildData (camelCase, items as Map).
 * @param itemsObj - Items as a plain object (from sessionStorage, pre-JSON).
 * @returns Plain object ready for JSON serialisation.
 */
function serializeBuild(
  build: BuildData,
  itemsObj?: Record<string, Item>,
): Record<string, unknown> {
  // Items may come from the Map or from the pre-serialised sessionStorage obj.
  const serializedItems: Record<string, Record<string, unknown>> = {};
  if (itemsObj) {
    for (const [slot, item] of Object.entries(itemsObj)) {
      serializedItems[slot] = serializeItem(item);
    }
  } else if (build.items instanceof Map) {
    for (const [slot, item] of build.items.entries()) {
      serializedItems[slot] = serializeItem(item);
    }
  }

  return {
    character_name: build.characterName,
    class: build.class,
    ascendancy: build.ascendancy,
    level: build.level,
    bandit: build.bandit,
    main_skill: build.mainSkill,
    stats: {
      life: build.stats.life,
      energy_shield: build.stats.energyShield,
      dps: build.stats.dps,
      fire_res: build.stats.fireRes,
      cold_res: build.stats.coldRes,
      lightning_res: build.stats.lightningRes,
      chaos_res: build.stats.chaosRes,
    },
    items: serializedItems,
    skill_groups: build.skillGroups.map(serializeSkillGroup),
    passive_tree: build.passiveTree ?? [],
  };
}

// ---------------------------------------------------------------------------
// API call
// ---------------------------------------------------------------------------

/**
 * Fetch upgrade recommendations for a build.
 *
 * @param build - Parsed build data.
 * @param buildCode - Raw PoB export code for the LuaJIT simulation engine.
 * @param itemsObj - Items as a plain object (from sessionStorage).
 * @param league - League name (default: ``'Settlers'``).
 * @param sessionId - Frontend session UUID for A/B LLM assignment.
 * @returns Parsed {@link RecommendResponse} from the backend.
 * @throws Error on non-2xx HTTP response.
 */
export async function fetchRecommendations(
  build: BuildData,
  buildCode: string,
  itemsObj: Record<string, Item> | undefined,
  league = 'Settlers',
  sessionId?: string,
): Promise<RecommendResponse> {
  const body: Record<string, unknown> = {
    build: serializeBuild(build, itemsObj),
    build_code: buildCode,
    league,
    max_candidates_per_slot: 5,
  };
  if (sessionId) {
    body['session_id'] = sessionId;
  }

  const resp = await fetch(`${API_BASE}/api/v1/recommendations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`Recommendations API error ${resp.status}: ${detail}`);
  }

  // Map backend snake_case fields to camelCase for the frontend
  const raw = await resp.json() as {
    recommendations: Array<{
      rank: number;
      category: string;
      slot: string;
      current_item: string;
      suggested_item: string;
      deltas: Record<string, number>;
      price_divine: number | null;
      efficiency_score: number | null;
      explanation: string;
      explanation_source: string;
      trade_url: string;
      wiki_url: string | null;
      ninja_url: string | null;
      score: number;
    }>;
    critical_issues: Array<{
      category: string;
      severity: string;
      description: string;
      affected_stat: string;
      current_value: number;
      target_value: number;
    }>;
    simulation_count: number;
    elapsed_seconds: number;
  };

  return {
    recommendations: raw.recommendations.map(r => ({
      rank: r.rank,
      category: r.category as RecommendResponse['recommendations'][0]['category'],
      slot: r.slot,
      currentItem: r.current_item,
      suggestedItem: r.suggested_item,
      deltas: r.deltas,
      priceDivine: r.price_divine,
      efficiencyScore: r.efficiency_score,
      explanation: r.explanation,
      explanationSource: (r.explanation_source ?? 'template') as 'llm' | 'template',
      tradeUrl: r.trade_url,
      wikiUrl: r.wiki_url,
      ninjaUrl: r.ninja_url,
      score: r.score,
    })),
    critical_issues: raw.critical_issues.map(i => ({
      category: i.category as RecommendResponse['critical_issues'][0]['category'],
      severity: i.severity as 'critical' | 'warning',
      description: i.description,
      affectedStat: i.affected_stat,
      currentValue: i.current_value,
      targetValue: i.target_value,
    })),
    simulation_count: raw.simulation_count,
    elapsed_seconds: raw.elapsed_seconds,
  };
}

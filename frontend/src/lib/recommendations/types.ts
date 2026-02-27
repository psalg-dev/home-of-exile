/**
 * TypeScript types for the M4 recommendation engine API.
 *
 * These mirror the Pydantic models defined in
 * ``backend/app/models/recommendation.py``.
 */

// ---- Recommendation category ------------------------------------------------

export type RecommendationCategory =
  | 'critical_fix'
  | 'power_upgrade'
  | 'defense_upgrade'
  | 'qol'
  | 'efficiency';

// ---- Critical issue ---------------------------------------------------------

export type CriticalIssueCategory =
  | 'uncapped_res'
  | 'low_life'
  | 'no_movement'
  | 'dead_link'
  | 'wasted_points';

export interface CriticalIssue {
  category: CriticalIssueCategory;
  severity: 'critical' | 'warning';
  description: string;
  affectedStat: string;
  currentValue: number;
  targetValue: number;
}

// ---- Recommendation ---------------------------------------------------------

export interface Recommendation {
  rank: number;
  category: RecommendationCategory;
  slot: string;
  currentItem: string;
  suggestedItem: string;
  deltas: Record<string, number>;
  priceDivine: number | null;
  efficiencyScore: number | null;
  explanation: string;
  /** Whether explanation came from LLM or template. */
  explanationSource: 'llm' | 'template';
  tradeUrl: string;
  wikiUrl: string | null;
  ninjaUrl: string | null;
  score: number;
}

// ---- API request / response -------------------------------------------------

export interface RecommendRequest {
  /** Parsed build data from the PoB parser. */
  build: Record<string, unknown>;
  /** URL-safe base64 PoB export code (required for LuaJIT). */
  build_code?: string;
  /** Raw PoB XML (alternative to build_code). */
  build_xml?: string;
  /** League name for live price data. */
  league?: string;
  /** How many top candidates to simulate per slot (1–20). */
  max_candidates_per_slot?: number;
  /** Frontend session UUID for A/B group assignment. */
  session_id?: string;
}

export interface RecommendResponse {
  recommendations: Recommendation[];
  critical_issues: CriticalIssue[];
  simulation_count: number;
  elapsed_seconds: number;
}

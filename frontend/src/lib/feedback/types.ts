/**
 * TypeScript types for the M6 feedback system API.
 *
 * These mirror the Pydantic models defined in
 * ``backend/app/models/feedback.py``.
 */

// ---- Feedback context -------------------------------------------------------

export interface FeedbackContext {
  archetype_damage: string;
  archetype_defense: string;
  archetype_playstyle: string;
  character_level: number;
  league: string;
  recommendation_category: string;
  slot: string;
  suggested_item: string;
  dps_delta: number | null;
  ehp_delta: number | null;
  price_divine: number | null;
  /** Whether explanation came from LLM or template — used for A/B analysis. */
  explanation_source: string;
}

// ---- Feedback request / response -------------------------------------------

export interface FeedbackRequest {
  session_id: string;
  recommendation_rank: number;
  vote: 'up' | 'down' | 'wrong_explanation';
  context: FeedbackContext;
}

export interface FeedbackResponse {
  stored: boolean;
  message: string;
}

// ---- Trade click -----------------------------------------------------------

export interface TradeClickRequest {
  session_id: string;
  recommendation_rank: number;
  suggested_item: string;
  league: string;
}

export interface TradeClickResponse {
  stored: boolean;
}

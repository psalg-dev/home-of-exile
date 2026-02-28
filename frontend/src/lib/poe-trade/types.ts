/**
 * TypeScript types for the PoE Trade API proxy.
 *
 * These mirror the Pydantic models defined in
 * ``backend/app/models/trade.py``.
 */

// ---- Request ----------------------------------------------------------------

export interface TradeListingsRequest {
  /** Unique item name (e.g. "Headhunter"). Leave empty for rares/gems. */
  item_name?: string;
  /** Item base type (e.g. "Leather Belt" or gem name like "Fireball"). */
  base_type?: string;
  /** True for unique items. */
  is_unique?: boolean;
  /** True when the candidate is a skill or support gem. */
  is_gem?: boolean;
  /** Minimum gem level filter (gems only). */
  gem_level?: number;
  /** Minimum gem quality filter (gems only). */
  gem_quality?: number;
  /** League name for the trade search. */
  league: string;
  /** Max number of listings to return (1–10). */
  count?: number;
  /**
   * When true (default), restrict to items with an explicit buyout price
   * so players can trade instantly without negotiation.
   */
  buyout_only?: boolean;
  /**
   * Archetype-relevant mod lines from the candidate item.  When provided,
   * the backend adds stat filters to the trade query so only items that
   * actually carry these mods are returned (e.g. attack speed + life on a
   * rare shield).
   */
  key_mods?: string[];
  /**
   * Player's POESESSID cookie value. Required to fetch actual listing
   * details from the trade API.
   */
  poesessid?: string;
}

// ---- Response ---------------------------------------------------------------

export interface TradePrice {
  type: string;
  amount: number;
  currency: string;
  /** Human-friendly currency label (e.g. "Divine Orb"). */
  currency_display: string;
}

export interface TradeListing {
  id: string;
  /** ISO-8601 timestamp when the item was indexed. */
  indexed: string;
  price: TradePrice;
  /** Pre-filled whisper message to copy and send to the seller in-game. */
  whisper: string;
  account_name: string;
  character_name: string;
  item_name: string;
  item_type: string;
  ilvl: number;
  corrupted: boolean;
}

export interface TradeListingsResponse {
  league: string;
  item_name: string;
  base_type: string;
  /** URL to view the search on the PoE trade site. */
  trade_url: string;
  total_listings: number;
  listings: TradeListing[];
  /** True when the result was served from the server-side cache. */
  cached: boolean;
  /** Non-empty when the upstream query failed. */
  error: string;
}

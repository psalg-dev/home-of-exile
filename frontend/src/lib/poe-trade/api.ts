/**
 * API client for the PoE Trade listings proxy endpoint.
 *
 * Calls ``POST /api/v1/trade/listings`` which proxies search and fetch
 * requests to pathofexile.com/trade on behalf of the frontend, handling
 * CORS, caching, and rate-limit enforcement server-side.
 */

import type { TradeListingsRequest, TradeListingsResponse } from './types';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/**
 * Fetch live PoE Trade listings for a single recommendation item.
 *
 * @param params - Item descriptor and search parameters.
 * @returns Structured listing response with prices and whisper text.
 * @throws Error if the network request itself fails (non-4xx/5xx).
 */
export async function fetchTradeListings(
  params: TradeListingsRequest,
): Promise<TradeListingsResponse> {
  const response = await fetch(`${API_BASE}/api/v1/trade/listings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`Trade API error ${response.status}: ${text || response.statusText}`);
  }

  return (await response.json()) as TradeListingsResponse;
}

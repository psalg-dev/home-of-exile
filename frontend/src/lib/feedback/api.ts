/**
 * API client for the M6 feedback and trade-click tracking endpoints.
 *
 * Both calls are fire-and-forget from the UI perspective — errors are
 * logged but never surfaced to the user.
 */

import type { FeedbackRequest, FeedbackResponse, TradeClickRequest, TradeClickResponse } from './types';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// POST /api/v1/feedback
// ---------------------------------------------------------------------------

/**
 * Submit a thumbs-up or thumbs-down vote for a recommendation.
 *
 * @param payload - Feedback payload including session ID, rank, vote, context.
 * @returns Resolved `FeedbackResponse` from the backend, or `null` on error.
 */
export async function submitFeedback(
  payload: FeedbackRequest,
): Promise<FeedbackResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.status === 409) {
      // Already voted — silently ignore
      return null;
    }

    if (!res.ok) {
      console.warn('[feedback] unexpected status', res.status);
      return null;
    }

    return (await res.json()) as FeedbackResponse;
  } catch (err) {
    console.warn('[feedback] network error', err);
    return null;
  }
}

// ---------------------------------------------------------------------------
// POST /api/v1/track/trade-click
// ---------------------------------------------------------------------------

/**
 * Record that the user clicked the "Search on Trade" link.
 *
 * This is a fire-and-forget call; errors are silently ignored.
 *
 * @param payload - Trade-click payload.
 * @returns `true` if the server confirmed persistence, `false` otherwise.
 */
export async function trackTradeClick(
  payload: TradeClickRequest,
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/track/trade-click`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      console.warn('[trade-click] unexpected status', res.status);
      return false;
    }

    const data = (await res.json()) as TradeClickResponse;
    return data.stored;
  } catch (err) {
    console.warn('[trade-click] network error', err);
    return false;
  }
}

"""Feedback and trade-click tracking endpoints — M6.

Routes
------
POST /api/v1/feedback           — submit a thumbs-up/down vote
POST /api/v1/track/trade-click  — record a trade-link click
GET  /api/v1/feedback/stats     — aggregate approval stats (admin)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.models.feedback import (
    FeedbackRequest,
    FeedbackResponse,
    FeedbackStatRow,
    FeedbackStatsResponse,
    TradeClickRequest,
    TradeClickResponse,
)
from app.services.database import (
    count_session_feedback,
    get_feedback_stats,
    insert_feedback,
    insert_trade_click,
    is_db_healthy,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["feedback"])

# Maximum feedback submissions per session (across all recommendations)
_MAX_FEEDBACK_PER_SESSION = 10

# ---------------------------------------------------------------------------
# POST /api/v1/feedback
# ---------------------------------------------------------------------------


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    request: Request,
) -> FeedbackResponse:
    """Submit a thumbs-up, thumbs-down, or wrong-explanation report.

    For ``up``/``down`` votes, a session may only vote once per
    recommendation rank.  ``wrong_explanation`` reports are always accepted
    (they are a separate signal and do not block a thumbs vote).

    Args:
        body: Feedback payload including session ID, rank, vote, context.
        request: FastAPI request object (for logging).

    Returns:
        :class:`~app.models.feedback.FeedbackResponse` indicating
        whether the vote was stored.

    Raises:
        HTTPException 409: If the session already cast a thumbs vote on
            this rank (only for ``up``/``down`` votes).
    """
    # Duplicate-vote guard only applies to thumbs votes, not wrong_explanation.
    if body.vote in ("up", "down"):
        existing = await count_session_feedback(
            body.session_id, body.recommendation_rank
        )
        if existing > 0:
            raise HTTPException(
                status_code=409,
                detail="You have already voted on this recommendation.",
            )

    ctx = body.context
    record = {
        "archetype_damage": ctx.archetype_damage,
        "archetype_defense": ctx.archetype_defense,
        "archetype_playstyle": ctx.archetype_playstyle,
        "character_level": ctx.character_level,
        "league": ctx.league,
        "recommendation_rank": body.recommendation_rank,
        "recommendation_category": ctx.recommendation_category,
        "slot": ctx.slot,
        "suggested_item": ctx.suggested_item,
        "dps_delta": ctx.dps_delta,
        "ehp_delta": ctx.ehp_delta,
        "price_divine": ctx.price_divine,
        "vote": body.vote,
        "session_id": body.session_id,
        "explanation_source": ctx.explanation_source,
    }

    stored = await insert_feedback(record)

    logger.info(
        "Feedback received: session=%s rank=%d vote=%s stored=%s",
        body.session_id[:8],
        body.recommendation_rank,
        body.vote,
        stored,
    )

    return FeedbackResponse(
        stored=stored,
        message=(
            "Vote recorded successfully."
            if stored
            else "Vote received (database unavailable — not persisted)."
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/track/trade-click
# ---------------------------------------------------------------------------


@router.post("/track/trade-click", response_model=TradeClickResponse)
async def track_trade_click(
    body: TradeClickRequest,
) -> TradeClickResponse:
    """Record that a user clicked the «Search on Trade» link.

    This is a lightweight implicit signal; failure is ignored silently.

    Args:
        body: Trade-click payload.

    Returns:
        :class:`~app.models.feedback.TradeClickResponse` with ``stored``
        indicating persistence success.
    """
    record = {
        "session_id": body.session_id,
        "recommendation_rank": body.recommendation_rank,
        "suggested_item": body.suggested_item,
        "league": body.league,
    }

    stored = await insert_trade_click(record)

    logger.info(
        "Trade click: session=%s rank=%d item=%s",
        body.session_id[:8],
        body.recommendation_rank,
        body.suggested_item,
    )

    return TradeClickResponse(stored=stored)


# ---------------------------------------------------------------------------
# GET /api/v1/feedback/stats (admin / internal)
# ---------------------------------------------------------------------------


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats_endpoint(
    league: str | None = None,
) -> FeedbackStatsResponse:
    """Return aggregate thumbs-up/down rates by archetype, slot, and league.

    This endpoint is intended for internal/admin use.  It does *not* require
    authentication in the MVP — that can be added in a follow-up.

    Args:
        league: Optional league filter.

    Returns:
        :class:`~app.models.feedback.FeedbackStatsResponse` with all rows
        and a DB availability flag.
    """
    db_up = await is_db_healthy()
    raw_rows = await get_feedback_stats(league=league)

    rows = [
        FeedbackStatRow(
            archetype_damage=r.get("archetype_damage", ""),
            archetype_defense=r.get("archetype_defense", ""),
            slot=r.get("slot", ""),
            recommendation_category=r.get("recommendation_category", ""),
            league=r.get("league", ""),
            total=int(r.get("total", 0)),
            up_votes=int(r.get("up_votes", 0)),
            down_votes=int(r.get("down_votes", 0)),
            up_ratio=(
                float(r["up_ratio"]) if r.get("up_ratio") is not None else None
            ),
        )
        for r in raw_rows
    ]

    return FeedbackStatsResponse(rows=rows, db_available=db_up)

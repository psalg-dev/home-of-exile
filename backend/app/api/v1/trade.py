"""PoE Trade API proxy endpoint.

Routes
------
POST /api/v1/trade/listings
    Proxy a PoE Trade search for a single item and return the top N live
    listings with price, whisper text, and seller details.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.core.limiter import limiter
from app.models.trade import TradeListingsRequest, TradeListingsResponse
from app.services.poe_trade import fetch_trade_listings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/trade", tags=["trade"])


@router.post(
    "/listings",
    summary="Fetch live PoE Trade listings for a recommendation item",
    response_description=(
        "Top N live listings ordered by price, including whisper text."
    ),
)
@limiter.limit("30/minute")
async def get_trade_listings(
    request: Request,  # noqa: ARG001 — required by slowapi
    body: TradeListingsRequest,
) -> TradeListingsResponse:
    """Proxy a PoE Trade search and return the cheapest live listings.

    The endpoint accepts an item descriptor extracted from a recommendation
    card (name, base type, rarity, gem flag) and returns structured listing
    data — price, whisper message, indexed time, and seller — so the frontend
    can display actionable follow-up information inline.

    Rate-limited to 30 requests per minute per IP to avoid DDoS-ing the
    upstream PoE trade site.

    Args:
        request: FastAPI request (used by the rate-limiter).
        body: Item descriptor and search parameters.

    Returns:
        :class:`~app.models.trade.TradeListingsResponse` with live or
        cached listings, or an ``error`` field on failure.
    """
    logger.info(
        "Trade listings request: item=%r base=%r league=%r",
        body.item_name,
        body.base_type,
        body.league,
    )
    return await fetch_trade_listings(body)

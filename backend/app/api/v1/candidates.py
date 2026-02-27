"""Candidate pool pipeline API endpoint.

Routes
------
POST /api/v1/candidates  — generate candidate upgrades for a build
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.models.candidate import (
    CandidatesRequest,
    CandidatesResponse,
)
from app.services.archetype import detect_archetype
from app.services.candidate_generator import run_pipeline
from app.services.poe_ninja import PoeNinjaClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["candidates"])

# Shared PoeNinjaClient (created once per process)
_poe_ninja_client: PoeNinjaClient | None = None


def _get_poe_ninja_client() -> PoeNinjaClient:
    """Return the module-level shared PoeNinjaClient, creating it lazily.

    Returns:
        Shared :class:`~app.services.poe_ninja.PoeNinjaClient` instance.
    """
    global _poe_ninja_client
    if _poe_ninja_client is None:
        _poe_ninja_client = PoeNinjaClient()
    return _poe_ninja_client


@router.post("/candidates", response_model=CandidatesResponse)
async def get_candidates(body: CandidatesRequest) -> CandidatesResponse:
    """Generate a pool of candidate item and gem upgrades for a build.

    Detects the build archetype, fetches current poe.ninja prices for the
    given league, then runs the candidate pipeline for the requested slot(s)
    and all enabled skill groups.

    Args:
        body: Request containing a parsed :class:`~app.models.candidate.BuildData`,
            an optional slot filter, and a league name.

    Returns:
        :class:`~app.models.candidate.CandidatesResponse` with archetype
        information, per-slot item candidates, and per-group gem candidates.

    Raises:
        HTTPException 422: Raised by Pydantic validation if the request body
            is malformed.
        HTTPException 500: If an unexpected error occurs during pipeline
            execution.
    """
    build = body.build
    league = body.league
    slot_filter = body.slot

    # 1. Detect archetype
    try:
        archetype = detect_archetype(build)
    except Exception as exc:
        logger.exception("Archetype detection failed")
        raise HTTPException(
            status_code=500,
            detail=f"Archetype detection error: {exc}",
        ) from exc

    logger.info(
        "Archetype detected: damage=%s defense=%s playstyle=%s",
        archetype.damage_type,
        archetype.defense_style,
        archetype.playstyle,
    )

    # 2. Fetch live prices
    client = _get_poe_ninja_client()
    try:
        prices = await client.get_item_prices(league)
    except Exception as exc:
        logger.warning("poe.ninja price fetch failed (%s); continuing", exc)
        prices = {}

    # 3. Run pipeline
    try:
        item_candidates, gem_candidates = run_pipeline(
            build=build,
            archetype=archetype,
            prices=prices,
            slot_filter=slot_filter,
        )
    except Exception as exc:
        logger.exception("Candidate pipeline failed")
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline error: {exc}",
        ) from exc

    return CandidatesResponse(
        archetype=archetype,
        item_candidates=item_candidates,
        gem_candidates=gem_candidates,
    )

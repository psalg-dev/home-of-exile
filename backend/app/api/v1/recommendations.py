"""Recommendation engine API endpoint — M4.

Routes
------
POST /api/v1/recommendations  — full simulation + ranked recommendations
"""

from __future__ import annotations

import base64
import logging
import time
import zlib

from fastapi import APIRouter, HTTPException

from app.models.recommendation import (
    RecommendRequest,
    RecommendResponse,
)
from app.services.archetype import detect_archetype
from app.services.candidate_generator import run_pipeline
from app.services.llm_explainer import get_llm_service
from app.services.luajit_pool import get_pool
from app.services.poe_ninja import PoeNinjaClient
from app.services.simulation import (
    build_recommendations_async,
    detect_critical_issues,
    simulate_upgrades,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["recommendations"])

# Shared PoeNinjaClient (lazily created)
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


def _decode_build_code(code: str) -> str:
    """Decode a URL-safe base64 PoB export code to an XML string.

    Args:
        code: URL-safe base64-encoded, zlib-compressed PoB export code.

    Returns:
        Decompressed XML string.

    Raises:
        HTTPException 400: If decoding or decompression fails.
    """
    standard = code.replace("-", "+").replace("_", "/")
    standard += "=" * ((4 - len(standard) % 4) % 4)

    try:
        compressed = base64.b64decode(standard)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PoB code: base64 decode failed — {exc}",
        ) from exc

    try:
        xml_bytes = zlib.decompress(compressed)
    except zlib.error as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PoB code: zlib decompression failed — {exc}",
        ) from exc

    return xml_bytes.decode("utf-8")


def _resolve_xml(
    build_code: str | None,
    build_xml: str | None,
) -> str:
    """Resolve PoB XML from a code or raw XML input.

    Args:
        build_code: URL-safe base64 PoB export code.
        build_xml: Raw PoB XML string.

    Returns:
        PoB XML string.

    Raises:
        HTTPException 400: If neither source is provided.
    """
    if build_xml:
        return build_xml
    if build_code:
        return _decode_build_code(build_code)
    raise HTTPException(
        status_code=400,
        detail="Either 'build_code' or 'build_xml' must be provided.",
    )


@router.post("/recommendations", response_model=RecommendResponse)
async def get_recommendations(
    body: RecommendRequest,
) -> RecommendResponse:
    """Run the full simulation loop and return the top 5 recommendations.

    Pipeline:
    1. Detect build archetype from parsed build data.
    2. Fetch live poe.ninja prices.
    3. Run M3 candidate pipeline for all slots.
    4. Detect critical issues from build stats.
    5. Simulate all candidate swaps via the LuaJIT engine pool.
    6. Score, rank, and select the top 5 recommendations.

    Args:
        body: Request containing a parsed build, a PoB code or raw XML,
            and optional parameters.

    Returns:
        :class:`~app.models.recommendation.RecommendResponse` with ranked
        recommendations, detected issues, and timing data.

    Raises:
        HTTPException 400: If the PoB code is invalid.
        HTTPException 503: If the LuaJIT engine pool is unavailable.
        HTTPException 504: If the engine times out during simulation.
        HTTPException 500: On internal pipeline errors.
    """
    start_time = time.monotonic()
    build = body.build
    league = body.league
    max_per_slot = body.max_candidates_per_slot

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
        "Recommendations: archetype damage=%s defense=%s playstyle=%s",
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

    # 3. Run M3 candidate pipeline
    try:
        item_candidates, gem_candidates = run_pipeline(
            build=build,
            archetype=archetype,
            prices=prices,
        )
    except Exception as exc:
        logger.exception("Candidate pipeline failed")
        raise HTTPException(
            status_code=500,
            detail=f"Candidate pipeline error: {exc}",
        ) from exc

    total_candidates = sum(
        len(sc.candidates) for sc in item_candidates
    ) + sum(
        len(gc.support_candidates) for gc in gem_candidates
    )
    logger.info("Candidate pipeline produced %d candidates", total_candidates)

    # 4. Detect critical issues (from parsed build stats)
    critical_issues = detect_critical_issues(build)
    logger.info("Detected %d critical issues", len(critical_issues))

    # 5. Simulate upgrades (requires LuaJIT pool + raw XML)
    # Decode the raw XML for the engine.
    build_xml = _resolve_xml(body.build_code, body.build_xml)

    # Try to get the pool; fall back gracefully if unavailable.
    pool = None
    try:
        pool = get_pool()
        if not pool.is_available:
            pool = None
    except RuntimeError:
        pool = None

    sim_results = []
    if pool is not None:
        try:
            sim_results = await simulate_upgrades(
                build_xml=build_xml,
                build=build,
                item_candidates=item_candidates,
                gem_candidates=gem_candidates,
                archetype=archetype,
                pool=pool,
                max_per_slot=max_per_slot,
            )
        except Exception as exc:
            logger.warning(
                "Simulation failed (%s); returning issue-only recommendations",
                exc,
            )
    else:
        logger.warning(
            "LuaJIT pool unavailable; "
            "recommendations will be based on archetype only."
        )

    # 6. Build ranked recommendations
    recommendations = await build_recommendations_async(
        simulations=sim_results,
        issues=critical_issues,
        build=build,
        archetype=archetype,
        league=league,
        session_id=body.session_id,
        llm_service=get_llm_service(),
    )

    elapsed = round(time.monotonic() - start_time, 3)
    logger.info(
        "Recommendations complete: %d recs, %d simulations, %.2fs",
        len(recommendations),
        len(sim_results),
        elapsed,
    )

    return RecommendResponse(
        recommendations=recommendations,
        critical_issues=critical_issues,
        simulation_count=len(sim_results),
        elapsed_seconds=elapsed,
    )

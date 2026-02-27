"""Unified analysis endpoint — M6 D6.5.

Routes
------
POST /api/v1/analyze  — full end-to-end pipeline (archetype → candidates →
                        simulation → ranked recommendations)

This endpoint is the primary entry-point for the frontend.  It wraps the
same pipeline as ``/api/v1/recommendations`` and additionally:

* Echoes the detected archetype back to the caller.
* Accepts an optional ``session_id`` for future per-session analytics.
* Enforces a 500 KB input size limit on the PoB code / XML.
"""

from __future__ import annotations

import base64
import logging
import time
import zlib

from fastapi import APIRouter, HTTPException, Request

from app.core.limiter import limiter
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

router = APIRouter(prefix="/api/v1", tags=["analyze"])

# Maximum allowed PoB export code size (bytes, before decoding)
_MAX_CODE_BYTES = 500 * 1024  # 500 KB

# Shared PoeNinjaClient (lazily created)
_poe_ninja_client: PoeNinjaClient | None = None


def _get_poe_ninja_client() -> PoeNinjaClient:
    """Return shared PoeNinjaClient, creating it lazily.

    Returns:
        Shared :class:`~app.services.poe_ninja.PoeNinjaClient` instance.
    """
    global _poe_ninja_client
    if _poe_ninja_client is None:
        _poe_ninja_client = PoeNinjaClient()
    return _poe_ninja_client


def _decode_build_code(code: str) -> str:
    """Decode a URL-safe base64 PoB export code to XML.

    Args:
        code: URL-safe base64-encoded, zlib-compressed PoB export code.

    Returns:
        Decompressed XML string.

    Raises:
        HTTPException 400: If the code exceeds the size limit or is invalid.
    """
    if len(code) > _MAX_CODE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"PoB code too large ({len(code)} bytes). "
                f"Maximum allowed: {_MAX_CODE_BYTES} bytes."
            ),
        )

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
    """Resolve PoB XML from code or raw XML.

    Args:
        build_code: URL-safe base64 PoB export code.
        build_xml: Raw PoB XML string.

    Returns:
        PoB XML string.

    Raises:
        HTTPException 400: If neither source is provided.
    """
    if build_xml:
        if len(build_xml) > _MAX_CODE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"PoB XML too large ({len(build_xml)} bytes). "
                    f"Maximum allowed: {_MAX_CODE_BYTES} bytes."
                ),
            )
        return build_xml
    if build_code:
        return _decode_build_code(build_code)
    raise HTTPException(
        status_code=400,
        detail="Either 'build_code' or 'build_xml' must be provided.",
    )


@router.post("/analyze", response_model=RecommendResponse)
@limiter.limit("10/hour")
async def analyze(
    body: RecommendRequest,
    request: Request,
) -> RecommendResponse:
    """Run the full build analysis pipeline and return ranked recommendations.

    Orchestrates:
    1. Archetype detection (M3)
    2. Live price fetch from poe.ninja
    3. Candidate generation (M3)
    4. Critical issue detection
    5. Simulation loop (M4) via the LuaJIT engine pool
    6. Scoring and ranking — returns up to 5 recommendations

    Args:
        body: Request body mirroring ``RecommendRequest``.
        request: Injected FastAPI request (used for logging/rate-limiting).

    Returns:
        :class:`~app.models.recommendation.RecommendResponse` with
        recommendations, critical issues, simulation count, and timing.

    Raises:
        HTTPException 400: If the PoB code is invalid or too large.
        HTTPException 503: If the LuaJIT pool is exhausted.
        HTTPException 500: On unexpected pipeline errors.
    """
    start_time = time.monotonic()
    build = body.build
    league = body.league
    max_per_slot = body.max_candidates_per_slot
    client_ip = request.client.host if request.client else "unknown"

    logger.info(
        "analyze: ip=%s league=%s class=%s level=%d",
        client_ip,
        league,
        build.char_class,
        build.level,
    )

    # 1. Validate and decode PoB source
    build_xml = _resolve_xml(body.build_code, body.build_xml)

    # 2. Detect archetype
    try:
        archetype = detect_archetype(build)
    except Exception as exc:
        logger.exception("Archetype detection failed")
        raise HTTPException(
            status_code=500,
            detail=f"Archetype detection error: {exc}",
        ) from exc

    logger.info(
        "analyze: archetype damage=%s defense=%s playstyle=%s",
        archetype.damage_type,
        archetype.defense_style,
        archetype.playstyle,
    )

    # 3. Fetch live prices (graceful degradation on failure)
    client = _get_poe_ninja_client()
    prices: dict[str, dict[str, object]] = {}
    try:
        prices = await client.get_item_prices(league)
    except Exception as exc:
        logger.warning("poe.ninja price fetch failed (%s); continuing", exc)

    # 4. Run M3 candidate pipeline
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
    ) + sum(len(gc.support_candidates) for gc in gem_candidates)
    logger.info("analyze: %d total candidates generated", total_candidates)

    # 5. Detect critical issues
    critical_issues = detect_critical_issues(build)
    logger.info("analyze: %d critical issues detected", len(critical_issues))

    # 6. Simulate upgrades (requires LuaJIT pool)
    pool = None
    try:
        pool = get_pool()
        if not pool.is_available:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Build engine is temporarily unavailable. "
                    "Please try again in a moment."
                ),
            )
    except HTTPException:
        raise
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
            "recommendations based on archetype metadata only."
        )

    # 7. Build ranked recommendations (with optional LLM enrichment via M7)
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
        "analyze: done — %d recs, %d simulations, %.2fs",
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

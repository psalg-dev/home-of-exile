"""Calculation endpoints backed by the LuaJIT / PathOfBuilding engine.

Routes
------
POST /api/v1/calculate          — calculate stats for a PoB build
POST /api/v1/calculate-swap     — calculate stats with one item swapped
POST /api/v1/calculate-swap/batch — parallel batch of item swaps
GET  /api/v1/calculate/health   — pool health check
"""

from __future__ import annotations

import base64
import logging
import zlib
from typing import Any

from fastapi import APIRouter, HTTPException

from app.models.calculation import (
    CalculateRequest,
    CalculateSwapBatchRequest,
    CalculateSwapRequest,
    CalculationResult,
    SwapResult,
)
from app.services.luajit_pool import LuaJITWorkerError, get_pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["calculate"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_build_code(code: str) -> str:
    """Decode a PoB export code to an XML string.

    PoB codes are URL-safe base64-encoded, zlib-compressed XML.

    Args:
        code: URL-safe base64 PoB export code.

    Returns:
        Decompressed XML string.

    Raises:
        HTTPException 400: If decoding or decompression fails.
    """
    # Normalise URL-safe base64 → standard base64
    standard = code.replace("-", "+").replace("_", "/")
    # Pad to multiple of 4
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
    """Resolve the XML string from either a code or a raw XML body.

    Args:
        build_code: Optional PoB export code.
        build_xml: Optional raw XML string.

    Returns:
        Decoded XML string.

    Raises:
        HTTPException 400: If neither is provided or decoding fails.
    """
    if build_xml:
        return build_xml
    if build_code:
        return _decode_build_code(build_code)
    raise HTTPException(
        status_code=400,
        detail="Either 'build_code' or 'build_xml' must be provided.",
    )


def _pool_or_503() -> Any:
    """Return the pool or raise 503 if unavailable.

    Returns:
        Active :class:`~app.services.luajit_pool.LuaJITPoolManager`.

    Raises:
        HTTPException 503: If the LuaJIT pool is not available.
    """
    try:
        pool = get_pool()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Calculation engine not initialised.",
        ) from exc

    if not pool.is_available:
        raise HTTPException(
            status_code=503,
            detail=(
                "Calculation engine unavailable — LuaJIT or PoB not found."
            ),
        )
    return pool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/calculate")
async def calculate(body: CalculateRequest) -> dict[str, object]:
    """Calculate DPS and defensive stats for a PoB build.

    Accepts either a raw PoB export code (``build_code``) or a decoded XML
    string (``build_xml``).  Returns a :class:`CalculationResult` with
    all available stats.

    Args:
        body: Request object with build source.

    Returns:
        JSON containing the ``result`` :class:`CalculationResult`.
    """
    xml = _resolve_xml(body.build_code, body.build_xml)
    pool = _pool_or_503()

    try:
        data = await pool.calculate(xml)
    except LuaJITWorkerError as exc:
        logger.error("calculate: LuaJIT error: %s", exc)
        raise HTTPException(
            status_code=504,
            detail=f"Calculation engine error: {exc}",
        ) from exc

    result = CalculationResult.from_pob_stats(data.get("stats", {}))
    return {"result": result.model_dump()}


@router.post("/calculate-swap")
async def calculate_swap(body: CalculateSwapRequest) -> dict[str, object]:
    """Calculate stats with one item replaced in a build.

    Loads the build, records baseline stats, swaps the specified item, then
    returns both baseline and modified stats along with numeric deltas.

    Args:
        body: Request object with build source plus ``slot`` and
            ``item_text``.

    Returns:
        JSON containing the ``result`` :class:`SwapResult`.
    """
    xml = _resolve_xml(body.build_code, body.build_xml)
    pool = _pool_or_503()

    try:
        data = await pool.calculate_swap(xml, body.item_text, body.slot)
    except LuaJITWorkerError as exc:
        logger.error("calculate-swap: LuaJIT error: %s", exc)
        raise HTTPException(
            status_code=504,
            detail=f"Calculation engine error: {exc}",
        ) from exc

    item_info = data.get("item") or {}
    item_name = str(item_info.get("name", ""))

    result = SwapResult.from_swap_data(
        slot=body.slot,
        item_name=item_name,
        baseline_stats=data.get("baseline", {}),
        modified_stats=data.get("modified", {}),
    )
    return {"result": result.model_dump()}


@router.post("/calculate-swap/batch")
async def calculate_swap_batch(
    body: CalculateSwapBatchRequest,
) -> dict[str, object]:
    """Run multiple item swap calculations in parallel.

    Each swap is dispatched to an available worker concurrently.  Results
    are returned in the same order as the input swaps.  Individual failures
    include an ``error`` key instead of results and do not abort the batch.

    Args:
        body: Request with build source and list of swaps.

    Returns:
        JSON containing ``results`` list of :class:`SwapResult` or error
        dicts.
    """
    xml = _resolve_xml(body.build_code, body.build_xml)
    pool = _pool_or_503()

    swaps = [
        {"item_text": s.item_text, "slot_name": s.slot} for s in body.swaps
    ]

    raw_results = await pool.calculate_swap_batch(xml, swaps)

    output: list[dict[str, object]] = []
    for _i, (raw, swap_spec) in enumerate(zip(raw_results, body.swaps, strict=True)):
        if isinstance(raw, dict) and "error" in raw and len(raw) == 1:
            output.append({"slot": swap_spec.slot, "error": raw["error"]})
        else:
            raw_dict: dict[str, Any] = raw
            item_info = raw_dict.get("item") or {}
            item_name = str(item_info.get("name", ""))
            swap_result = SwapResult.from_swap_data(
                slot=swap_spec.slot,
                item_name=item_name,
                baseline_stats=raw_dict.get("baseline", {}),
                modified_stats=raw_dict.get("modified", {}),
            )
            output.append(swap_result.model_dump())

    return {"results": output}


@router.get("/calculate/health")
async def calculate_health() -> dict[str, object]:
    """Return LuaJIT pool health information.

    Does not require the pool to be available — a degraded pool returns a
    health dict with ``available: false``.

    Returns:
        Health dict from :meth:`LuaJITPoolManager.health_check`.
    """
    try:
        pool = get_pool()
    except RuntimeError:
        return {
            "available": False,
            "pool_size": 0,
            "total_workers": 0,
            "healthy_workers": 0,
        }

    return await pool.health_check()

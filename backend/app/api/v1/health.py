"""Health check endpoints — M6.

Routes
------
GET /health        — liveness probe (app is alive)
GET /health/ready  — readiness probe (app + LuaJIT pool + PostgreSQL)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response

from app.services.database import is_db_healthy
from app.services.luajit_pool import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()

_VERSION = "0.6.0"


@router.get("/health")
async def health() -> dict[str, str]:
    """Return the service liveness status.

    This endpoint returns 200 OK as long as the application process is
    running.  It does *not* check downstream dependencies.

    Returns:
        A dict with ``status`` and ``version`` fields.
    """
    return {"status": "ok", "version": _VERSION}


@router.get("/health/ready")
async def health_ready(response: Response) -> dict[str, object]:
    """Return the service readiness status.

    Checks the LuaJIT engine pool and PostgreSQL availability.  Returns
    HTTP 503 if any critical dependency is unavailable.

    Returns:
        A dict with ``status``, ``version``, ``luajit_pool``, and
        ``database`` fields.
    """
    # --- LuaJIT pool ---
    luajit_ok = False
    try:
        pool = get_pool()
        luajit_ok = pool.is_available
    except Exception:
        luajit_ok = False

    # --- PostgreSQL ---
    db_ok = await is_db_healthy()

    overall = "ok" if luajit_ok else "degraded"

    payload: dict[str, object] = {
        "status": overall,
        "version": _VERSION,
        "luajit_pool": "ok" if luajit_ok else "unavailable",
        "database": "ok" if db_ok else "unavailable",
    }

    if not luajit_ok:
        response.status_code = 503
        logger.warning("Readiness check: LuaJIT pool unavailable")

    return payload

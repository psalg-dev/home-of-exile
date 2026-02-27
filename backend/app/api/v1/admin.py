"""Admin endpoints for LLM usage monitoring — M7.

Routes
------
GET  /api/v1/admin/llm-usage  — token usage dashboard
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.services.llm_explainer import get_llm_service, get_usage_tracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# GET /api/v1/admin/llm-usage
# ---------------------------------------------------------------------------


@router.get("/llm-usage")
async def get_llm_usage() -> dict[str, Any]:
    """Return today's LLM token usage and cost dashboard.

    Returns a snapshot of:
    - Total input and output tokens consumed today.
    - Estimated USD cost for today.
    - Number of LLM-served requests.
    - Number of template fallbacks (with breakdown by cause).
    - A/B test configuration (enabled model, spend cap).

    Returns:
        JSON dict with usage metrics for today.
    """
    tracker = get_usage_tracker()
    service = get_llm_service()
    snapshot = tracker.snapshot()

    # Annotate with service configuration for the dashboard.
    snapshot["llm_enabled"] = service.llm_enabled
    snapshot["model"] = service.model
    snapshot["daily_spend_cap_usd"] = service.daily_spend_cap_usd
    snapshot["cap_reached"] = tracker.cap_reached(service.daily_spend_cap_usd)
    snapshot["timeout_seconds"] = service.timeout_seconds

    logger.debug("LLM usage dashboard queried: %s", snapshot)
    return snapshot

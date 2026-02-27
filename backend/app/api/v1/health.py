"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """
    Return the service health status.

    Returns:
        A dict with ``status`` and ``version`` fields.
    """
    return {"status": "ok", "version": "0.1.0"}

"""poe.ninja price overview endpoint."""

from fastapi import APIRouter

from app.core.config import settings
from app.services.poe_ninja import PoeNinjaClient

router = APIRouter()

# Shared client instance (created once per process)
_client: PoeNinjaClient | None = None


def get_client() -> PoeNinjaClient:
    """Return the shared PoeNinjaClient, creating it if necessary."""
    global _client
    if _client is None:
        _client = PoeNinjaClient()
    return _client


@router.get("/prices/{league}")
async def get_prices(league: str | None = None) -> dict[str, object]:
    """
    Return a summary of current poe.ninja prices for the given league.

    Falls back to the configured default league if not specified.

    Args:
        league: Optional league name (defaults to settings.poe_ninja_league).

    Returns:
        A dict containing ``items`` and ``currency`` price dicts.
    """
    effective_league = league or settings.poe_ninja_league
    client = get_client()
    items = await client.get_item_prices(effective_league)
    currency = await client.get_currency_prices(effective_league)
    return {"league": effective_league, "items": items, "currency": currency}

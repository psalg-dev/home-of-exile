"""Pydantic models for the PoE Trade API proxy.

These models describe the request / response shapes for the
``/api/v1/trade/listings`` endpoint that proxies pathofexile.com/trade.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class TradeListingsRequest(BaseModel):
    """Request body for ``POST /api/v1/trade/listings``.

    Callers supply the item identity fields extracted from a recommendation.
    The backend builds the appropriate PoE Trade query and returns live
    listings.

    Attributes:
        item_name: Unique item name (e.g. ``'Headhunter'``).
            Leave empty for rares / gems.
        base_type: Item base type (e.g. ``'Leather Belt'`` or ``'Fireball'``
            for gems).
        is_unique: ``True`` for unique items.
        is_gem: ``True`` when the candidate is a skill or support gem.
        gem_level: Minimum gem level filter (gems only).
        gem_quality: Minimum gem quality filter (gems only).
        league: League name for the trade search.
        count: Max number of listings to return (1–10).
    """

    item_name: str = Field(default="")
    base_type: str = Field(default="")
    is_unique: bool = Field(default=False)
    is_gem: bool = Field(default=False)
    gem_level: int | None = Field(default=None, ge=1, le=30)
    gem_quality: int | None = Field(default=None, ge=0, le=23)
    league: str = Field(default="Keepers")
    count: int = Field(default=5, ge=1, le=10)
    buyout_only: bool = Field(
        default=True,
        description=(
            "When True (default), restrict results to items that have an "
            "explicit buyout price set (\"~b/o\") so players can trade "
            "instantly without negotiation."
        ),
    )
    poesessid: str = Field(
        default="",
        description=(
            "Player's POESESSID cookie value. When provided it is forwarded "
            "as a cookie to the upstream trade API so the player's account "
            "session is used for the request (required for most trade fetch "
            "calls)."
        ),
    )


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class TradePrice(BaseModel):
    """Price information for a single trade listing.

    Attributes:
        type: Pricing type (``'~b/o'`` = buyout, ``'~price'`` = fixed).
        amount: Numerical price.
        currency: Currency shorthand (e.g. ``'divine'``, ``'chaos'``).
        currency_display: Human-friendly currency label.
    """

    type: str = Field(default="~b/o")
    amount: float
    currency: str
    currency_display: str = Field(default="")


class TradeListing(BaseModel):
    """A single item listing from the PoE trade site.

    Attributes:
        id: Internal listing identifier.
        indexed: ISO-8601 timestamp when the item was indexed.
        price: Listing price.
        whisper: Pre-filled whisper message for the seller.
        account_name: Seller's account name.
        character_name: Seller's last character name.
        item_name: Name line of the item (may be empty for rares).
        item_type: Type line / base type.
        ilvl: Item level.
        corrupted: Whether the item is corrupted.
    """

    id: str
    indexed: str
    price: TradePrice
    whisper: str = Field(default="")
    account_name: str = Field(default="")
    character_name: str = Field(default="")
    item_name: str = Field(default="")
    item_type: str = Field(default="")
    ilvl: int = Field(default=0)
    corrupted: bool = Field(default=False)


class TradeListingsResponse(BaseModel):
    """Response body for ``POST /api/v1/trade/listings``.

    Attributes:
        league: The league the search was run against.
        item_name: Effective item name used in the query.
        base_type: Effective base type used in the query.
        trade_url: Shareable URL to view the search on the trade site.
        total_listings: Total number of listings found (before slicing).
        listings: Top *N* listings ordered by price ascending.
        cached: ``True`` when the result was served from cache.
        error: Non-empty string if the query failed (listings will be empty).
    """

    league: str
    item_name: str
    base_type: str
    trade_url: str
    total_listings: int = Field(default=0)
    listings: list[TradeListing] = Field(default_factory=list)
    cached: bool = Field(default=False)
    error: str = Field(default="")

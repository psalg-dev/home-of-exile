"""PoE Trade API proxy service.

Provides a thin, async wrapper around ``pathofexile.com/api/trade``
that:

* Builds query payloads from item/gem descriptors.
* Proxies search (POST) and fetch (GET) calls with proper headers.
* Respects the trade-site rate limits via a per-service token bucket.
* Caches results for 60 s to avoid duplicate upstream requests.

The public entry point is :func:`fetch_trade_listings`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.parse
from typing import Any

import httpx

from app.models.trade import (
    TradeListing,
    TradeListingsRequest,
    TradeListingsResponse,
    TradePrice,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TRADE_BASE = "https://www.pathofexile.com/api/trade"

# PoE Trade requires an informative User-Agent.
_USER_AGENT = (
    "home-of-exile/1.0 (https://github.com/home-of-exile; "
    "trade-proxy contact@homeofexile.example)"
)

# Cache TTL in seconds — trade listings expire quickly.
_CACHE_TTL = 60

# Rate-limit: GGG allows ~12 search calls per 10 s (conservative).
# We enforce a minimum inter-call gap to stay well within the limit.
_MIN_CALL_INTERVAL = 1.0  # seconds between upstream trade-API calls

# Upstream request timeout (seconds).
_REQUEST_TIMEOUT = 8.0

# Human-friendly labels for common currency identifiers.
_CURRENCY_LABELS: dict[str, str] = {
    "divine": "Divine Orb",
    "exalted": "Exalted Orb",
    "chaos": "Chaos Orb",
    "vaal": "Vaal Orb",
    "annul": "Orb of Annulment",
    "fusing": "Orb of Fusing",
    "alchemy": "Orb of Alchemy",
    "gcp": "Gemcutter's Prism",
    "alteration": "Orb of Alteration",
    "chromatic": "Chromatic Orb",
    "scour": "Orb of Scouring",
    "regret": "Orb of Regret",
    "regal": "Regal Orb",
    "blessed": "Blessed Orb",
    "offer": "Orb of Offering",
    "mirror": "Mirror of Kalandra",
    "coin": "Perandus Coin",
}


# ---------------------------------------------------------------------------
# Simple in-memory cache
# ---------------------------------------------------------------------------


class _Cache:
    """Thread-safe TTL cache keyed by arbitrary strings.

    Entries are lazily expired on read.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Return cached value or ``None`` if missing / expired."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: float = _CACHE_TTL) -> None:
        """Store *value* under *key* for *ttl* seconds."""
        async with self._lock:
            self._store[key] = (value, time.monotonic() + ttl)


_cache = _Cache()


# ---------------------------------------------------------------------------
# Rate-limiter (token bucket, single token)
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Enforces a minimum interval between upstream trade-API calls.

    Uses a simple last-call timestamp rather than a full token bucket
    because GGG's limits are lenient for single-user proxies.
    """

    def __init__(self, min_interval: float = _MIN_CALL_INTERVAL) -> None:
        self._min_interval = min_interval
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait if necessary to respect the minimum inter-call interval."""
        async with self._lock:
            now = time.monotonic()
            gap = now - self._last_call
            if gap < self._min_interval:
                await asyncio.sleep(self._min_interval - gap)
            self._last_call = time.monotonic()


_rate_limiter = _RateLimiter()


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------


def _build_query(req: TradeListingsRequest) -> dict[str, Any]:
    """Construct a PoE Trade JSON query payload from a listings request.

    Args:
        req: Deserialized trade listings request.

    Returns:
        Dict suitable for JSON-encoding as the POST body.
    """
    # Trade filters common to all queries — collapse duplicate accounts.
    trade_filters: dict[str, Any] = {
        "trade_filters": {
            "filters": {
                "collapse": {"option": "true"},
            }
        }
    }

    if req.is_gem:
        misc: dict[str, Any] = {}
        if req.gem_level is not None:
            misc["gem_level"] = {"min": req.gem_level}
        if req.gem_quality is not None:
            misc["quality"] = {"min": req.gem_quality}
        filters: dict[str, Any] = dict(trade_filters)
        if misc:
            filters["misc_filters"] = {"filters": misc}
        return {
            "query": {
                "status": {"option": "online"},
                "type": req.base_type or req.item_name,
                "filters": filters,
            },
            "sort": {"price": "asc"},
        }

    if req.is_unique and req.item_name:
        return {
            "query": {
                "status": {"option": "online"},
                "name": req.item_name,
                "type": req.base_type if req.base_type else None,
                "filters": trade_filters,
            },
            "sort": {"price": "asc"},
        }

    # Rare / normal — search by base type.
    return {
        "query": {
            "status": {"option": "online"},
            "type": req.base_type or req.item_name,
            "filters": trade_filters,
        },
        "sort": {"price": "asc"},
    }


def _build_trade_url(req: TradeListingsRequest, query_id: str = "") -> str:
    """Return the shareable trade site URL for the given request.

    When *query_id* is provided the URL points to the exact search
    result page; otherwise a fresh query link is returned.

    Args:
        req: Listings request.
        query_id: Optional upstream query identifier.

    Returns:
        Absolute https URL to ``pathofexile.com/trade``.
    """
    safe_league = urllib.parse.quote(req.league)
    if query_id:
        return f"https://www.pathofexile.com/trade/search/{safe_league}/{query_id}"

    base = f"https://www.pathofexile.com/trade/search/{safe_league}"
    q = _build_query(req)
    return f"{base}?q={urllib.parse.quote(json.dumps(q, separators=(',', ':')))}"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _make_headers() -> dict[str, str]:
    """Return HTTP headers for upstream PoE Trade API calls.

    Returns:
        Dict with ``User-Agent``, ``Accept``, and ``Content-Type`` headers.
    """
    return {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _parse_listing(raw: dict[str, Any]) -> TradeListing | None:
    """Parse a raw trade fetch result entry into a :class:`TradeListing`.

    Args:
        raw: Single entry from the ``result`` array in a trade fetch response.

    Returns:
        Parsed :class:`TradeListing`, or ``None`` if the entry is malformed.
    """
    try:
        listing = raw.get("listing", {})
        item = raw.get("item", {})
        price_raw = listing.get("price", {})

        currency = price_raw.get("currency", "chaos")
        price = TradePrice(
            type=price_raw.get("type", "~b/o"),
            amount=float(price_raw.get("amount", 0)),
            currency=currency,
            currency_display=_CURRENCY_LABELS.get(currency, currency),
        )

        account = listing.get("account", {})

        return TradeListing(
            id=str(raw.get("id", "")),
            indexed=listing.get("indexed", ""),
            price=price,
            whisper=listing.get("whisper", ""),
            account_name=account.get("name", ""),
            character_name=account.get("lastCharacterName", ""),
            item_name=item.get("name", ""),
            item_type=item.get("typeLine", item.get("baseType", "")),
            ilvl=int(item.get("ilvl", 0)),
            corrupted=bool(item.get("corrupted", False)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("Failed to parse listing entry: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Core async fetching logic
# ---------------------------------------------------------------------------


async def _search(
    client: httpx.AsyncClient,
    query: dict[str, Any],
    league: str,
) -> tuple[str, list[str], int]:
    """POST a trade search and return (query_id, result_ids, total).

    Args:
        client: Shared httpx async client.
        query: Trade query payload.
        league: League name.

    Returns:
        Tuple of (query_id, result_ids, total_count).

    Raises:
        httpx.HTTPStatusError: On non-2xx responses.
        httpx.TimeoutException: On request timeout.
    """
    await _rate_limiter.acquire()
    url = f"{_TRADE_BASE}/search/{urllib.parse.quote(league)}"
    response = await client.post(
        url,
        json=query,
        headers=_make_headers(),
        timeout=_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    query_id: str = data.get("id", "")
    result_ids: list[str] = data.get("result", [])
    total: int = data.get("total", len(result_ids))
    return query_id, result_ids, total


async def _fetch(
    client: httpx.AsyncClient,
    result_ids: list[str],
    query_id: str,
) -> list[dict[str, Any]]:
    """GET up to 20 trade listings by their IDs.

    Args:
        client: Shared httpx async client.
        result_ids: Listing IDs from a prior search.
        query_id: The query identifier from the search response.

    Returns:
        Raw result entries from the fetch response.

    Raises:
        httpx.HTTPStatusError: On non-2xx responses.
        httpx.TimeoutException: On request timeout.
    """
    if not result_ids:
        return []
    await _rate_limiter.acquire()
    ids_param = ",".join(result_ids[:20])
    url = f"{_TRADE_BASE}/fetch/{ids_param}?query={query_id}"
    response = await client.get(
        url,
        headers=_make_headers(),
        timeout=_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("result", [])  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def fetch_trade_listings(
    req: TradeListingsRequest,
) -> TradeListingsResponse:
    """Fetch live PoE Trade listings for an item described by *req*.

    The function:

    1. Builds a PoE Trade API query from the request.
    2. Checks the in-memory cache; returns the cached result when fresh.
    3. POSTs the query to the upstream search endpoint.
    4. GETs the first *req.count* listing details.
    5. Returns a structured :class:`TradeListingsResponse`.

    Args:
        req: Item descriptor and search parameters.

    Returns:
        :class:`TradeListingsResponse` with live or cached listings.
    """
    cache_key = (
        f"{req.league}|{req.item_name}|{req.base_type}"
        f"|{req.is_unique}|{req.is_gem}"
        f"|{req.gem_level}|{req.gem_quality}|{req.count}"
    )

    cached = await _cache.get(cache_key)
    if cached is not None:
        logger.debug("Trade listings cache hit: %s", cache_key)
        result: TradeListingsResponse = cached
        result.cached = True
        return result

    query = _build_query(req)
    trade_url = _build_trade_url(req)
    effective_name = req.item_name
    effective_base = req.base_type

    try:
        async with httpx.AsyncClient() as client:
            query_id, result_ids, total = await _search(client, query, req.league)

            if query_id:
                trade_url = _build_trade_url(req, query_id)

            fetch_ids = result_ids[: req.count]
            raw_entries = await _fetch(client, fetch_ids, query_id)

    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 429:
            msg = "Trade API rate limit reached. Please try again in a moment."
        elif status == 400:
            msg = "Trade API rejected the query (invalid item name or league)."
        else:
            msg = f"Trade API returned HTTP {status}."
        logger.warning("PoE Trade API error for %r: %s", cache_key, msg)
        return TradeListingsResponse(
            league=req.league,
            item_name=effective_name,
            base_type=effective_base,
            trade_url=trade_url,
            error=msg,
        )
    except httpx.TimeoutException:
        msg = "Trade API request timed out."
        logger.warning("PoE Trade API timeout for %r", cache_key)
        return TradeListingsResponse(
            league=req.league,
            item_name=effective_name,
            base_type=effective_base,
            trade_url=trade_url,
            error=msg,
        )
    except Exception as exc:
        msg = f"Unexpected error fetching trade listings: {exc}"
        logger.exception("PoE Trade API unexpected error for %r", cache_key)
        return TradeListingsResponse(
            league=req.league,
            item_name=effective_name,
            base_type=effective_base,
            trade_url=trade_url,
            error=msg,
        )

    listings: list[TradeListing] = []
    for entry in raw_entries:
        parsed = _parse_listing(entry)
        if parsed is not None:
            listings.append(parsed)

    response = TradeListingsResponse(
        league=req.league,
        item_name=effective_name,
        base_type=effective_base,
        trade_url=trade_url,
        total_listings=total,
        listings=listings,
        cached=False,
    )

    await _cache.set(cache_key, response)
    logger.info(
        "Trade listings fetched: item=%r league=%r total=%d returned=%d",
        effective_name or effective_base,
        req.league,
        total,
        len(listings),
    )
    return response

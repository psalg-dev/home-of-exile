"""
poe.ninja price client.

Fetches live item and currency prices from poe.ninja with an in-memory
TTL cache and graceful fallback on network errors.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Cache TTL — poe.ninja asks for polite access; 1 h is reasonable.
_CACHE_TTL = timedelta(hours=1)

# Base URL for poe.ninja economy API
_BASE_URL = "https://poe.ninja/poe1/api/economy/stash/current"

# Item categories to fetch for item prices
_ITEM_TYPES = [
    "UniqueWeapon",
    "UniqueArmour",
    "UniqueAccessory",
    "UniqueFlask",
    "UniqueJewel",
    "SkillGem",
]


class PoeNinjaPrice:
    """A single item price entry from poe.ninja."""

    __slots__ = ("chaos_value", "divine_value", "listing_count", "name")

    def __init__(
        self,
        name: str,
        chaos_value: float,
        divine_value: float,
        listing_count: int,
    ) -> None:
        """
        Initialise a price entry.

        Args:
            name: Item or currency name.
            chaos_value: Price in chaos orbs.
            divine_value: Price in divine orbs.
            listing_count: Number of trade listings.
        """
        self.name = name
        self.chaos_value = chaos_value
        self.divine_value = divine_value
        self.listing_count = listing_count

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-compatible dict."""
        return {
            "name": self.name,
            "chaosValue": self.chaos_value,
            "divineValue": self.divine_value,
            "listingCount": self.listing_count,
        }


class PoeNinjaClient:
    """
    Async client for the poe.ninja price API.

    Uses an in-memory cache keyed by (league, type) with a 1-hour TTL.
    Raises no exceptions on network failure; returns empty dicts instead.
    """

    def __init__(self) -> None:
        """Initialise the HTTP client and empty cache."""
        self._http = httpx.AsyncClient(
            timeout=10.0,
            headers={"X-Powered-By": "home-of-exile"},
            follow_redirects=True,
        )
        # Cache: key = (league, type_str) → (fetched_at, payload)
        self._cache: dict[tuple[str, str], tuple[datetime, Any]] = {}

    async def _fetch(self, url: str, params: dict[str, str]) -> Any:
        """
        Fetch JSON from a URL, returning None on network error.

        Args:
            url: Endpoint URL.
            params: Query parameters.

        Returns:
            Parsed JSON object, or None if the request failed.
        """
        try:
            response = await self._http.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as exc:
            logger.warning("poe.ninja request failed: %s", exc)
            return None
        except httpx.HTTPStatusError as exc:
            logger.warning("poe.ninja HTTP error %s: %s", exc.response.status_code, exc)
            return None

    def _is_cached(self, key: tuple[str, str]) -> bool:
        """Return True if the cache entry exists and has not expired."""
        if key not in self._cache:
            return False
        fetched_at, _ = self._cache[key]
        return datetime.now(UTC) - fetched_at < _CACHE_TTL

    async def get_item_prices(self, league: str) -> dict[str, dict[str, Any]]:
        """
        Return item prices for the given league, keyed by item name.

        Fetches all item type categories and merges them. The result is
        cached for 1 hour per league.

        Args:
            league: PoE league name (e.g. 'Settlers').

        Returns:
            Dict mapping item name → price dict with chaosValue, divineValue,
            listingCount. Returns {} on network failure.
        """
        merged: dict[str, dict[str, Any]] = {}

        for item_type in _ITEM_TYPES:
            cache_key = (league, item_type)
            if self._is_cached(cache_key):
                _, data = self._cache[cache_key]
            else:
                data = await self._fetch(
                    f"{_BASE_URL}/item/overview",
                    {"league": league, "type": item_type},
                )
                self._cache[cache_key] = (datetime.now(UTC), data)

            if data and "lines" in data:
                for entry in data["lines"]:
                    name: str = entry.get("name", "")
                    if name:
                        merged[name] = PoeNinjaPrice(
                            name=name,
                            chaos_value=float(entry.get("chaosValue", 0)),
                            divine_value=float(entry.get("divineValue", 0)),
                            listing_count=int(entry.get("listingCount", 0)),
                        ).to_dict()

        return merged

    async def get_currency_prices(self, league: str) -> dict[str, float]:
        """
        Return currency chaos-equivalent prices for the given league.

        Args:
            league: PoE league name (e.g. 'Settlers').

        Returns:
            Dict mapping currency name → chaos equivalent value.
            Returns {} on network failure.
        """
        cache_key = (league, "Currency")
        if self._is_cached(cache_key):
            _, data = self._cache[cache_key]
        else:
            data = await self._fetch(
                f"{_BASE_URL}/currency/overview",
                {"league": league, "type": "Currency"},
            )
            self._cache[cache_key] = (datetime.now(UTC), data)

        if not data or "lines" not in data:
            return {}

        result: dict[str, float] = {}
        for entry in data["lines"]:
            name: str = entry.get("currencyTypeName", "")
            # chaosEquivalent is the standard field in the currency overview
            value = entry.get("chaosEquivalent", entry.get("chaosValue", 0))
            if name:
                result[name] = float(value)

        return result

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

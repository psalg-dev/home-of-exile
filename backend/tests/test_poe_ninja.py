"""
Unit tests for the poe.ninja price client.

Uses httpx mock transport to avoid real network calls.
"""

from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.services.poe_ninja import PoeNinjaClient


def _make_item_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a fake poe.ninja ItemOverview response."""
    return {"lines": items}


def _make_currency_response(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a fake poe.ninja CurrencyOverview response."""
    return {"lines": lines}


@pytest.fixture
def client() -> PoeNinjaClient:
    """Return a fresh PoeNinjaClient for each test."""
    return PoeNinjaClient()


class TestGetItemPrices:
    """Tests for PoeNinjaClient.get_item_prices()."""

    @pytest.mark.asyncio
    async def test_returns_dict_from_response(self, client: PoeNinjaClient) -> None:
        """Should return a non-empty dict when the API responds successfully."""
        sample = {"name": "Shavronne's Wrappings", "chaosValue": 500.0, "divineValue": 1.5, "listingCount": 120}

        async def mock_fetch(url: str, params: dict[str, str]) -> Any:
            return _make_item_response([sample])

        with patch.object(client, "_fetch", side_effect=mock_fetch):
            result = await client.get_item_prices("Settlers")

        assert "Shavronne's Wrappings" in result
        assert result["Shavronne's Wrappings"]["chaosValue"] == 500.0

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_network_error(self, client: PoeNinjaClient) -> None:
        """Should return {} (not raise) when poe.ninja is unreachable."""
        async def mock_fetch(url: str, params: dict[str, str]) -> Any:
            return None  # simulate network failure returning None

        with patch.object(client, "_fetch", side_effect=mock_fetch):
            result = await client.get_item_prices("Settlers")

        assert result == {}

    @pytest.mark.asyncio
    async def test_uses_cache_after_first_fetch(self, client: PoeNinjaClient) -> None:
        """Should not call _fetch again if cache is still valid."""
        call_count = 0

        async def mock_fetch(url: str, params: dict[str, str]) -> Any:
            nonlocal call_count
            call_count += 1
            return _make_item_response([])

        with patch.object(client, "_fetch", side_effect=mock_fetch):
            await client.get_item_prices("Settlers")
            first_count = call_count
            await client.get_item_prices("Settlers")
            # Second call should reuse cache; _fetch count should not grow for cached items
            # (we have 6 item types so first_count = 6, second should still be 6)
            assert call_count == first_count


class TestGetCurrencyPrices:
    """Tests for PoeNinjaClient.get_currency_prices()."""

    @pytest.mark.asyncio
    async def test_returns_float_values(self, client: PoeNinjaClient) -> None:
        """Should return dict mapping currency name → chaos equivalent."""
        sample = {"currencyTypeName": "Divine Orb", "chaosEquivalent": 200.0}

        async def mock_fetch(url: str, params: dict[str, str]) -> Any:
            return _make_currency_response([sample])

        with patch.object(client, "_fetch", side_effect=mock_fetch):
            result = await client.get_currency_prices("Settlers")

        assert "Divine Orb" in result
        assert result["Divine Orb"] == 200.0

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_network_error(self, client: PoeNinjaClient) -> None:
        """Should return {} (not raise) when poe.ninja is unreachable."""
        async def mock_fetch(url: str, params: dict[str, str]) -> Any:
            return None

        with patch.object(client, "_fetch", side_effect=mock_fetch):
            result = await client.get_currency_prices("Settlers")

        assert result == {}


class TestRequestError:
    """Tests that RequestError is caught gracefully."""

    @pytest.mark.asyncio
    async def test_request_error_returns_empty_dict(self, client: PoeNinjaClient) -> None:
        """PoeNinjaClient should return {} when httpx raises RequestError."""
        mock_transport = httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(
                httpx.ConnectError("Connection refused", request=request)
            )  # type: ignore[arg-type]
        )
        client._http = httpx.AsyncClient(transport=mock_transport, headers={"X-Powered-By": "home-of-exile"})

        result = await client.get_item_prices("Settlers")
        assert result == {}

        result2 = await client.get_currency_prices("Settlers")
        assert result2 == {}

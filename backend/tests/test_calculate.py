"""Tests for the /api/v1/calculate* endpoints.

These tests use mocking to avoid requiring a real LuaJIT binary.
"""

from __future__ import annotations

import base64
import json
import zlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.calculation import CalculationResult, SwapResult
from app.services.luajit_pool import LuaJITPoolManager, LuaJITWorkerError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_build_code(xml: str) -> str:
    """Encode an XML string as a PoB export code (for test input).

    Args:
        xml: Raw XML string.

    Returns:
        URL-safe base64-encoded zlib-compressed code.
    """
    compressed = zlib.compress(xml.encode("utf-8"))
    encoded = base64.b64encode(compressed).decode("ascii")
    return encoded.replace("+", "-").replace("/", "_").rstrip("=")


_MINIMAL_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<PathOfBuilding>"
    "<Build level='90' className='Witch' ascendClassName='Occultist'>"
    "<PlayerStat stat='Life' value='4500'/>"
    "<PlayerStat stat='EnergyShield' value='0'/>"
    "<PlayerStat stat='CombinedDPS' value='1200000'/>"
    "</Build>"
    "</PathOfBuilding>"
)

_POB_STATS: dict[str, Any] = {
    "Life": 4500,
    "EnergyShield": 250,
    "Armour": 8000,
    "Evasion": 0,
    "FireResist": 75,
    "ColdResist": 75,
    "LightningResist": 75,
    "ChaosResist": -60,
    "BlockChance": 0,
    "SpellBlockChance": 0,
    "TotalDPS": 0,
    "FullDPS": 0,
    "CombinedDPS": 1200000,
    "AverageDamage": 0,
}

_SWAP_STATS_MODIFIED: dict[str, Any] = dict(_POB_STATS)
_SWAP_STATS_MODIFIED["Life"] = 5000
_SWAP_STATS_MODIFIED["CombinedDPS"] = 1400000


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_client() -> TestClient:
    """Return a synchronous TestClient for the app (bypasses lifespan)."""
    # Use raise_server_exceptions=True so test assertions see real errors
    return TestClient(app, raise_server_exceptions=True)


def _make_mock_pool(
    available: bool = True,
    calc_result: dict[str, Any] | None = None,
    swap_result: dict[str, Any] | None = None,
    raise_on_calc: Exception | None = None,
    raise_on_swap: Exception | None = None,
) -> MagicMock:
    """Build a mock LuaJITPoolManager.

    Args:
        available: Whether pool.is_available returns True.
        calc_result: Return value for pool.calculate().
        swap_result: Return value for pool.calculate_swap().
        raise_on_calc: If set, pool.calculate() raises this exception.
        raise_on_swap: If set, pool.calculate_swap() raises this exception.

    Returns:
        Configured MagicMock.
    """
    pool = MagicMock(spec=LuaJITPoolManager)
    pool.is_available = available

    if raise_on_calc is not None:
        pool.calculate = AsyncMock(side_effect=raise_on_calc)
    else:
        pool.calculate = AsyncMock(
            return_value=calc_result or {"stats": _POB_STATS}
        )

    if raise_on_swap is not None:
        pool.calculate_swap = AsyncMock(side_effect=raise_on_swap)
    else:
        pool.calculate_swap = AsyncMock(
            return_value=swap_result
            or {
                "baseline": _POB_STATS,
                "modified": _SWAP_STATS_MODIFIED,
                "item": {"name": "Test Item", "slot": "Helmet"},
            }
        )

    pool.calculate_swap_batch = AsyncMock(
        return_value=[
            {
                "baseline": _POB_STATS,
                "modified": _SWAP_STATS_MODIFIED,
                "item": {"name": "Test Item", "slot": "Helmet"},
            }
        ]
    )

    pool.health_check = AsyncMock(
        return_value={
            "available": available,
            "pool_size": 2,
            "total_workers": 2,
            "healthy_workers": 2 if available else 0,
        }
    )

    return pool


# ---------------------------------------------------------------------------
# /api/v1/calculate/health
# ---------------------------------------------------------------------------


class TestCalculateHealth:
    """Tests for GET /api/v1/calculate/health."""

    def test_health_pool_available(self, test_client: TestClient) -> None:
        """Health endpoint returns healthy info when pool is available."""
        pool = _make_mock_pool(available=True)
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.get("/api/v1/calculate/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["healthy_workers"] == 2

    def test_health_pool_unavailable(self, test_client: TestClient) -> None:
        """Health endpoint returns degraded info when pool is not running."""
        with patch(
            "app.api.v1.calculate.get_pool",
            side_effect=RuntimeError("not init"),
        ):
            resp = test_client.get("/api/v1/calculate/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False


# ---------------------------------------------------------------------------
# /api/v1/calculate
# ---------------------------------------------------------------------------


class TestCalculate:
    """Tests for POST /api/v1/calculate."""

    def test_calculate_with_build_xml(
        self, test_client: TestClient
    ) -> None:
        """Endpoint accepts raw build_xml and returns calculation result."""
        pool = _make_mock_pool()
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate",
                json={"build_xml": _MINIMAL_XML},
            )

        assert resp.status_code == 200
        data = resp.json()
        result = data["result"]
        assert result["life"] == 4500
        assert result["energy_shield"] == 250
        assert result["fire_res"] == 75
        assert result["dps"] == 1200000

    def test_calculate_with_build_code(
        self, test_client: TestClient
    ) -> None:
        """Endpoint decodes a PoB export code correctly."""
        code = _make_build_code(_MINIMAL_XML)
        pool = _make_mock_pool()
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate",
                json={"build_code": code},
            )

        assert resp.status_code == 200
        pool.calculate.assert_awaited_once()

    def test_calculate_returns_503_when_pool_unavailable(
        self, test_client: TestClient
    ) -> None:
        """Endpoint returns 503 when LuaJIT pool is not available."""
        pool = _make_mock_pool(available=False)
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate",
                json={"build_xml": _MINIMAL_XML},
            )
        assert resp.status_code == 503

    def test_calculate_returns_504_on_engine_error(
        self, test_client: TestClient
    ) -> None:
        """Endpoint returns 504 when the LuaJIT engine throws an error."""
        pool = _make_mock_pool(
            raise_on_calc=LuaJITWorkerError("engine crashed")
        )
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate",
                json={"build_xml": _MINIMAL_XML},
            )
        assert resp.status_code == 504

    def test_calculate_returns_400_for_invalid_build_code(
        self, test_client: TestClient
    ) -> None:
        """Endpoint returns 400 for a garbled PoB code."""
        pool = _make_mock_pool()
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate",
                json={"build_code": "NOT_VALID_CODE!!"},
            )
        assert resp.status_code == 400

    def test_calculate_returns_422_for_missing_body(
        self, test_client: TestClient
    ) -> None:
        """Endpoint returns 422 when neither build_code nor build_xml given."""
        pool = _make_mock_pool()
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate",
                json={},
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/v1/calculate-swap
# ---------------------------------------------------------------------------


_ITEM_TEXT = (
    "Rarity: Rare\n"
    "Hubris Circlet\n"
    "--------\n"
    "+50 to Maximum Life\n"
    "+30% to Fire Resistance\n"
)


class TestCalculateSwap:
    """Tests for POST /api/v1/calculate-swap."""

    def test_swap_returns_baseline_and_modified(
        self, test_client: TestClient
    ) -> None:
        """Swap endpoint returns baseline, modified, and deltas."""
        pool = _make_mock_pool()
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate-swap",
                json={
                    "build_xml": _MINIMAL_XML,
                    "slot": "Helmet",
                    "item_text": _ITEM_TEXT,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        result = data["result"]
        assert result["slot"] == "Helmet"
        assert "baseline" in result
        assert "modified" in result
        assert "deltas" in result
        # Life increased by 500
        assert result["deltas"].get("life") == pytest.approx(500.0)

    def test_swap_503_when_pool_unavailable(
        self, test_client: TestClient
    ) -> None:
        """Swap endpoint returns 503 when pool is down."""
        pool = _make_mock_pool(available=False)
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate-swap",
                json={
                    "build_xml": _MINIMAL_XML,
                    "slot": "Helmet",
                    "item_text": _ITEM_TEXT,
                },
            )
        assert resp.status_code == 503

    def test_swap_504_on_engine_error(
        self, test_client: TestClient
    ) -> None:
        """Swap endpoint returns 504 on engine failure."""
        pool = _make_mock_pool(
            raise_on_swap=LuaJITWorkerError("timeout")
        )
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate-swap",
                json={
                    "build_xml": _MINIMAL_XML,
                    "slot": "Helmet",
                    "item_text": _ITEM_TEXT,
                },
            )
        assert resp.status_code == 504


# ---------------------------------------------------------------------------
# /api/v1/calculate-swap/batch
# ---------------------------------------------------------------------------


class TestCalculateSwapBatch:
    """Tests for POST /api/v1/calculate-swap/batch."""

    def test_batch_returns_list(self, test_client: TestClient) -> None:
        """Batch endpoint returns one result per swap."""
        pool = _make_mock_pool()
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate-swap/batch",
                json={
                    "build_xml": _MINIMAL_XML,
                    "swaps": [
                        {"slot": "Helmet", "item_text": _ITEM_TEXT},
                    ],
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1

    def test_batch_503_when_pool_unavailable(
        self, test_client: TestClient
    ) -> None:
        """Batch endpoint returns 503 when pool is down."""
        pool = _make_mock_pool(available=False)
        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate-swap/batch",
                json={
                    "build_xml": _MINIMAL_XML,
                    "swaps": [
                        {"slot": "Helmet", "item_text": _ITEM_TEXT},
                    ],
                },
            )
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Unit: CalculationResult.from_pob_stats
# ---------------------------------------------------------------------------


class TestCalculationResult:
    """Unit tests for CalculationResult model helpers."""

    def test_from_pob_stats_full(self) -> None:
        """All fields are mapped correctly from a complete stats dict."""
        result = CalculationResult.from_pob_stats(_POB_STATS)
        assert result.life == 4500
        assert result.energy_shield == 250
        assert result.armour == 8000
        assert result.fire_res == 75
        assert result.chaos_res == -60
        assert result.dps == 1200000

    def test_from_pob_stats_empty(self) -> None:
        """Missing stats default to 0."""
        result = CalculationResult.from_pob_stats({})
        assert result.life == 0
        assert result.dps == 0.0

    def test_from_pob_stats_dps_fallback(self) -> None:
        """DPS fallback chain: CombinedDPS → TotalDPS → FullDPS → Avg."""
        # Only AverageDamage
        stats: dict[str, Any] = {"AverageDamage": 500.0}
        result = CalculationResult.from_pob_stats(stats)
        assert result.dps == 500.0

        # TotalDPS beats AverageDamage
        stats["TotalDPS"] = 600.0
        result = CalculationResult.from_pob_stats(stats)
        assert result.dps == 600.0

        # CombinedDPS wins over all
        stats["CombinedDPS"] = 700.0
        result = CalculationResult.from_pob_stats(stats)
        assert result.dps == 700.0


class TestSwapResult:
    """Unit tests for SwapResult model helpers."""

    def test_deltas_computed_correctly(self) -> None:
        """Deltas reflect the difference between modified and baseline."""
        result = SwapResult.from_swap_data(
            slot="Helmet",
            item_name="Test Hat",
            baseline_stats=_POB_STATS,
            modified_stats=_SWAP_STATS_MODIFIED,
        )
        assert result.deltas["life"] == pytest.approx(500.0)
        assert result.deltas["dps"] == pytest.approx(200000.0)

    def test_zero_deltas_not_in_dict(self) -> None:
        """Unchanged stats are excluded from the delta dict."""
        result = SwapResult.from_swap_data(
            slot="Ring",
            item_name="Same Ring",
            baseline_stats=_POB_STATS,
            modified_stats=_POB_STATS,
        )
        assert result.deltas == {}


# ---------------------------------------------------------------------------
# Unit: _decode_build_code helper
# ---------------------------------------------------------------------------


class TestDecodeBuildCode:
    """Unit tests for the _decode_build_code helper."""

    def test_round_trip(self, test_client: TestClient) -> None:
        """A code produced from XML should decode back correctly."""
        code = _make_build_code(_MINIMAL_XML)
        pool = _make_mock_pool()

        with patch(
            "app.api.v1.calculate.get_pool", return_value=pool
        ):
            resp = test_client.post(
                "/api/v1/calculate",
                json={"build_code": code},
            )

        assert resp.status_code == 200
        # The pool was called with the decoded XML
        call_args = pool.calculate.call_args
        passed_xml: str = call_args.args[0]
        assert "<PathOfBuilding>" in passed_xml

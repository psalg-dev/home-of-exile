"""Tests for the M6 feedback, trade-click, and analyze endpoints.

Uses mocking to avoid requiring a real PostgreSQL database or LuaJIT binary.
"""

from __future__ import annotations

import base64
import zlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Return a synchronous TestClient for the app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Feedback endpoint helpers
# ---------------------------------------------------------------------------

_FEEDBACK_BODY = {
    "session_id": "test-session-abc123",
    "recommendation_rank": 1,
    "vote": "up",
    "context": {
        "archetype_damage": "phys",
        "archetype_defense": "life",
        "archetype_playstyle": "caster",
        "character_level": 90,
        "league": "Settlers",
        "recommendation_category": "power_upgrade",
        "slot": "Helmet",
        "suggested_item": "Starkonja's Head",
        "dps_delta": 50000.0,
        "ehp_delta": None,
        "price_divine": 2.5,
    },
}

_TRADE_CLICK_BODY = {
    "session_id": "test-session-abc123",
    "recommendation_rank": 2,
    "suggested_item": "Starkonja's Head",
    "league": "Settlers",
}


# ---------------------------------------------------------------------------
# POST /api/v1/feedback
# ---------------------------------------------------------------------------


class TestFeedbackEndpoint:
    """Tests for POST /api/v1/feedback."""

    def test_feedback_stored_when_db_available(self, client: TestClient) -> None:
        """Feedback POST should return 200 with stored=True when DB is up."""
        with (
            patch(
                "app.api.v1.feedback.count_session_feedback",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "app.api.v1.feedback.insert_feedback",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            response = client.post("/api/v1/feedback", json=_FEEDBACK_BODY)

        assert response.status_code == 200
        data = response.json()
        assert data["stored"] is True
        assert "message" in data

    def test_feedback_graceful_when_db_unavailable(
        self, client: TestClient
    ) -> None:
        """Feedback POST should return 200 with stored=False when DB is down."""
        with (
            patch(
                "app.api.v1.feedback.count_session_feedback",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "app.api.v1.feedback.insert_feedback",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            response = client.post("/api/v1/feedback", json=_FEEDBACK_BODY)

        assert response.status_code == 200
        data = response.json()
        assert data["stored"] is False

    def test_duplicate_vote_returns_409(self, client: TestClient) -> None:
        """Voting twice on the same recommendation returns HTTP 409."""
        with patch(
            "app.api.v1.feedback.count_session_feedback",
            new_callable=AsyncMock,
            return_value=1,  # already voted
        ):
            response = client.post("/api/v1/feedback", json=_FEEDBACK_BODY)

        assert response.status_code == 409

    def test_invalid_vote_value_returns_422(self, client: TestClient) -> None:
        """A vote value other than 'up'/'down' should return HTTP 422."""
        body = {**_FEEDBACK_BODY, "vote": "maybe"}
        response = client.post("/api/v1/feedback", json=body)
        assert response.status_code == 422

    def test_rank_out_of_range_returns_422(self, client: TestClient) -> None:
        """recommendation_rank outside [1, 5] should return HTTP 422."""
        body = {**_FEEDBACK_BODY, "recommendation_rank": 6}
        response = client.post("/api/v1/feedback", json=body)
        assert response.status_code == 422

    def test_empty_session_id_returns_422(self, client: TestClient) -> None:
        """An empty session_id should fail validation (min_length=1)."""
        body = {**_FEEDBACK_BODY, "session_id": ""}
        response = client.post("/api/v1/feedback", json=body)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/track/trade-click
# ---------------------------------------------------------------------------


class TestTradeClickEndpoint:
    """Tests for POST /api/v1/track/trade-click."""

    def test_trade_click_stored(self, client: TestClient) -> None:
        """Trade-click POST should return 200 with stored=True when DB is up."""
        with patch(
            "app.api.v1.feedback.insert_trade_click",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = client.post(
                "/api/v1/track/trade-click", json=_TRADE_CLICK_BODY
            )

        assert response.status_code == 200
        assert response.json()["stored"] is True

    def test_trade_click_graceful_no_db(self, client: TestClient) -> None:
        """Trade-click returns 200 with stored=False when DB is unavailable."""
        with patch(
            "app.api.v1.feedback.insert_trade_click",
            new_callable=AsyncMock,
            return_value=False,
        ):
            response = client.post(
                "/api/v1/track/trade-click", json=_TRADE_CLICK_BODY
            )

        assert response.status_code == 200
        assert response.json()["stored"] is False


# ---------------------------------------------------------------------------
# GET /api/v1/feedback/stats
# ---------------------------------------------------------------------------


class TestFeedbackStatsEndpoint:
    """Tests for GET /api/v1/feedback/stats."""

    def test_stats_empty_when_db_up(self, client: TestClient) -> None:
        """Stats endpoint returns 200 with empty rows and db_available=True."""
        with (
            patch(
                "app.api.v1.feedback.is_db_healthy",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.v1.feedback.get_feedback_stats",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            response = client.get("/api/v1/feedback/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["db_available"] is True
        assert data["rows"] == []

    def test_stats_db_unavailable(self, client: TestClient) -> None:
        """Stats endpoint returns db_available=False when DB is down."""
        with (
            patch(
                "app.api.v1.feedback.is_db_healthy",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.api.v1.feedback.get_feedback_stats",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            response = client.get("/api/v1/feedback/stats")

        assert response.status_code == 200
        assert response.json()["db_available"] is False

    def test_stats_with_rows(self, client: TestClient) -> None:
        """Stats endpoint correctly serialises aggregate rows."""
        mock_rows = [
            {
                "archetype_damage": "phys",
                "archetype_defense": "life",
                "slot": "Helmet",
                "recommendation_category": "power_upgrade",
                "league": "Settlers",
                "total": 10,
                "up_votes": 7,
                "down_votes": 3,
                "up_ratio": 0.7,
            }
        ]
        with (
            patch(
                "app.api.v1.feedback.is_db_healthy",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.v1.feedback.get_feedback_stats",
                new_callable=AsyncMock,
                return_value=mock_rows,
            ),
        ):
            response = client.get("/api/v1/feedback/stats?league=Settlers")

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        row = data["rows"][0]
        assert row["up_ratio"] == pytest.approx(0.7)
        assert row["total"] == 10


# ---------------------------------------------------------------------------
# GET /health and GET /health/ready
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    """Tests for the health and readiness endpoints."""

    def test_health_returns_ok(self, client: TestClient) -> None:
        """GET /health always returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.6.0"

    def test_health_ready_degraded_when_pool_unavailable(
        self, client: TestClient
    ) -> None:
        """GET /health/ready returns 503 when LuaJIT pool is unavailable."""
        with (
            patch(
                "app.api.v1.health.get_pool",
                side_effect=RuntimeError("pool not initialised"),
            ),
            patch(
                "app.api.v1.health.is_db_healthy",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            response = client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["luajit_pool"] == "unavailable"

    def test_health_ready_ok(self, client: TestClient) -> None:
        """GET /health/ready returns 200 when all dependencies are up."""
        mock_pool = AsyncMock()
        mock_pool.is_available = True

        with (
            patch("app.api.v1.health.get_pool", return_value=mock_pool),
            patch(
                "app.api.v1.health.is_db_healthy",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["luajit_pool"] == "ok"
        assert data["database"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/v1/analyze
# ---------------------------------------------------------------------------


def _make_pob_code(xml: str) -> str:
    """Encode XML as a PoB export code for test input.

    Args:
        xml: Raw XML string.

    Returns:
        URL-safe base64-encoded zlib-compressed code.
    """
    compressed = zlib.compress(xml.encode("utf-8"))
    encoded = base64.b64encode(compressed).decode("ascii")
    return encoded.replace("+", "-").replace("/", "_").rstrip("=")


_MINIMAL_XML = (
    '<?xml version="1.0" encoding="UTF-8"?><PathOfBuilding>'
    "<Build level='80' className='Witch' ascendClassName='Occultist'>"
    "<PlayerStat stat='Life' value='4500'/>"
    "</Build></PathOfBuilding>"
)

_MINIMAL_BUILD = {
    "character_name": "Test",
    "class": "Witch",
    "ascendancy": "Occultist",
    "level": 80,
    "main_skill": "Fireball",
    "bandit": "None",
    "stats": {
        "life": 4500, "energy_shield": 0, "dps": 1200000.0,
        "fire_res": 75, "cold_res": 75, "lightning_res": 75, "chaos_res": -60,
        "armour": 0, "evasion": 0,
    },
    "attrs": {"str": 100, "dex": 100, "int": 200},
    "skill_groups": [
        {
            "slot": "Body Armour",
            "label": "",
            "enabled": True,
            "gems": [
                {
                    "skill_id": "Fireball",
                    "name_spec": "Fireball",
                    "level": 20,
                    "quality": 20,
                    "enabled": True,
                    "is_support": False,
                }
            ],
            "main_active_gem_index": 0,
        }
    ],
    "items": {},
}


class TestAnalyzeEndpoint:
    """Tests for POST /api/v1/analyze."""

    def test_analyze_returns_200_no_pool(self, client: TestClient) -> None:
        """POST /api/v1/analyze returns 200 when pool is unavailable.

        Without a LuaJIT pool the endpoint still returns recommendations
        generated from critical issue detection only.
        """
        code = _make_pob_code(_MINIMAL_XML)

        with (
            patch(
                "app.api.v1.analyze.run_pipeline",
                return_value=([], []),
            ),
            patch(
                "app.api.v1.analyze.detect_critical_issues",
                return_value=[],
            ),
            patch(
                "app.api.v1.analyze.get_pool",
                side_effect=RuntimeError("no pool"),
            ),
            patch(
                "app.services.poe_ninja.PoeNinjaClient.get_item_prices",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            resp = client.post(
                "/api/v1/analyze",
                json={
                    "build": _MINIMAL_BUILD,
                    "build_code": code,
                    "league": "Settlers",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data
        assert "critical_issues" in data
        assert "elapsed_seconds" in data

    def test_analyze_rejects_oversized_code(self, client: TestClient) -> None:
        """POST /api/v1/analyze returns 400 for a PoB code that is too large."""
        oversized_code = "A" * (500 * 1024 + 1)
        resp = client.post(
            "/api/v1/analyze",
            json={
                "build": _MINIMAL_BUILD,
                "build_code": oversized_code,
                "league": "Settlers",
            },
        )
        assert resp.status_code == 400

    def test_analyze_missing_build_code_returns_422(
        self, client: TestClient
    ) -> None:
        """POST /api/v1/analyze returns 422 when no build source is provided."""
        resp = client.post(
            "/api/v1/analyze",
            json={"build": _MINIMAL_BUILD, "league": "Settlers"},
        )
        assert resp.status_code == 422

    def test_analyze_503_when_pool_exhausted(
        self, client: TestClient
    ) -> None:
        """POST /api/v1/analyze returns 503 when pool is initialised but busy."""
        code = _make_pob_code(_MINIMAL_XML)
        mock_pool = MagicMock()
        mock_pool.is_available = False

        with (
            patch(
                "app.api.v1.analyze.run_pipeline",
                return_value=([], []),
            ),
            patch(
                "app.api.v1.analyze.detect_critical_issues",
                return_value=[],
            ),
            patch("app.api.v1.analyze.get_pool", return_value=mock_pool),
            patch(
                "app.services.poe_ninja.PoeNinjaClient.get_item_prices",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            resp = client.post(
                "/api/v1/analyze",
                json={
                    "build": _MINIMAL_BUILD,
                    "build_code": code,
                    "league": "Settlers",
                },
            )

        assert resp.status_code == 503

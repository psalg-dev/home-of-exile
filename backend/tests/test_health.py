"""Tests for the /health endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def test_client() -> TestClient:
    """Return a synchronous TestClient for the app."""
    return TestClient(app)


def test_health_returns_ok(test_client: TestClient) -> None:
    """GET /health should return 200 with status=ok."""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data

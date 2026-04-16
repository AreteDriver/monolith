"""Tests for health endpoint."""

import pytest
from fastapi.testclient import TestClient

from backend.db.database import init_db
from backend.main import app


@pytest.fixture
def client():
    """Test client with in-memory database."""
    app.state.db = init_db(":memory:")
    with TestClient(app) as c:
        yield c
    app.state.db.close()


def test_health_returns_ok(client):
    """Health endpoint returns status ok."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.5.0"
    assert "uptime_seconds" in data
    assert "row_counts" in data


def test_health_row_counts_structure(client):
    """Health endpoint includes all table counts."""
    resp = client.get("/api/health")
    counts = resp.json()["row_counts"]
    assert "chain_events" in counts
    assert "anomalies" in counts
    assert "bug_reports" in counts
    assert "filed_issues" in counts

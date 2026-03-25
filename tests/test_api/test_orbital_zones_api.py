"""Tests for orbital zones API endpoints."""

import time

import pytest
from fastapi.testclient import TestClient

from backend.db.database import init_db
from backend.main import app


@pytest.fixture
def client():
    """Create test client with fresh DB."""
    conn = init_db(":memory:")
    app.state.db = conn
    yield TestClient(app)
    conn.close()


def _seed_zone(conn, zone_id, **kwargs):
    """Insert an orbital zone for testing."""
    now = int(time.time())
    conn.execute(
        "INSERT INTO orbital_zones "
        "(zone_id, zone_name, system_id, feral_ai_tier, threat_level, last_polled, discovered_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            zone_id,
            kwargs.get("zone_name", f"Zone {zone_id}"),
            kwargs.get("system_id", "sys-1"),
            kwargs.get("tier", 0),
            kwargs.get("threat", "LOW"),
            kwargs.get("last_polled", now),
            now,
        ),
    )
    conn.commit()


def test_list_zones_empty(client):
    """Empty table returns empty list."""
    resp = client.get("/api/orbital-zones")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_list_zones_with_data(client):
    """Seeded zones appear in response."""
    conn = app.state.db
    _seed_zone(conn, "z-1")
    _seed_zone(conn, "z-2", system_id="sys-2")

    resp = client.get("/api/orbital-zones")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


def test_list_zones_filter_system(client):
    """system_id filter works."""
    conn = app.state.db
    _seed_zone(conn, "z-a", system_id="sys-10")
    _seed_zone(conn, "z-b", system_id="sys-20")

    resp = client.get("/api/orbital-zones?system_id=sys-10")
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["zone_id"] == "z-a"


def test_list_zones_filter_threat(client):
    """threat_level filter works."""
    conn = app.state.db
    _seed_zone(conn, "z-safe", threat="LOW")
    _seed_zone(conn, "z-hot", threat="HIGH")

    resp = client.get("/api/orbital-zones?threat_level=HIGH")
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["zone_id"] == "z-hot"


def test_threat_overview(client):
    """Threat overview aggregates correctly."""
    conn = app.state.db
    _seed_zone(conn, "z-1", threat="LOW", tier=0)
    _seed_zone(conn, "z-2", threat="LOW", tier=1)
    _seed_zone(conn, "z-3", threat="HIGH", tier=3)

    resp = client.get("/api/orbital-zones/threats")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2  # LOW and HIGH groups


def test_feral_ai_events_empty(client):
    """Empty feral AI events returns empty list."""
    resp = client.get("/api/orbital-zones/feral-ai/events")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_cycle_info(client):
    """Cycle endpoint returns current cycle metadata."""
    resp = client.get("/api/orbital-zones/cycle")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cycle"] == 5
    assert data["name"] == "Shroud of Fear"
    assert data["days_elapsed"] >= 0

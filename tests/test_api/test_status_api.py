"""Tests for status API endpoints."""

import time

import pytest

from backend.alerts.service_health import CheckResult, record_check
from backend.api.status import get_status, get_status_history
from backend.db.database import init_db


class FakeRequest:
    """Minimal request stub for route handlers."""

    def __init__(self, conn, heartbeats=None, intervals=None):
        self.app = type("App", (), {"state": type("State", (), {
            "db": conn,
            "loop_heartbeats": heartbeats or {},
            "loop_intervals": intervals or {},
        })()})()


@pytest.fixture
def setup():
    """In-memory DB with seeded service state."""
    conn = init_db(":memory:")
    now = int(time.time())
    record_check(conn, CheckResult("world_api", "up", 150, None, now))
    record_check(conn, CheckResult("sui_rpc", "up", 200, None, now))
    heartbeats = {"chain_poll": time.time(), "detection": time.time()}
    intervals = {"chain_poll": 30, "detection": 300}
    request = FakeRequest(conn, heartbeats, intervals)
    yield conn, request
    conn.close()


def test_get_status(setup):
    """GET /api/status returns service list and overall status."""
    conn, request = setup
    data = get_status(request)
    assert "services" in data
    assert "monolith" in data
    assert "overall" in data
    assert data["overall"] in ("up", "degraded", "down", "unknown")
    assert len(data["services"]) >= 2


def test_get_status_loops(setup):
    """GET /api/status includes loop health."""
    _, request = setup
    data = get_status(request)
    loops = data["monolith"]["loops"]
    assert "chain_poll" in loops
    assert "detection" in loops


def test_get_status_history(setup):
    """GET /api/status/history returns check records."""
    _, request = setup
    data = get_status_history(request, service="world_api", limit=10)
    assert data["service_name"] == "world_api"
    assert len(data["checks"]) >= 1
    assert data["checks"][0]["status"] == "up"


def test_get_status_history_empty(setup):
    """GET /api/status/history returns empty for unknown service."""
    _, request = setup
    data = get_status_history(request, service="nonexistent", limit=10)
    assert data["checks"] == []


def test_overall_status_degraded(setup):
    """Overall status reflects worst service."""
    conn, request = setup
    now = int(time.time())
    record_check(conn, CheckResult("watchtower", "degraded", 6000, "Slow", now))
    data = get_status(request)
    assert data["overall"] == "degraded"


def test_overall_status_down(setup):
    """Overall status is down when any service is down."""
    conn, request = setup
    now = int(time.time())
    record_check(conn, CheckResult("watchtower", "down", 0, "timeout", now))
    data = get_status(request)
    assert data["overall"] == "down"

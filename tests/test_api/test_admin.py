"""Tests for admin endpoints — auth gating + universe reset flush."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.db.database import init_db
from backend.main import app


@pytest.fixture
def client():
    conn = init_db(":memory:")
    app.state.db = conn
    yield TestClient(app, raise_server_exceptions=False)
    conn.close()


def _configure_admin(key: str = "") -> None:
    settings = MagicMock()
    settings.admin_key = key
    app.state.settings = settings


def _set_poller(flushed: dict[str, int]) -> MagicMock:
    poller = MagicMock()
    poller.flush_polled_data.return_value = flushed
    app.state.world_poller = poller
    return poller


def test_universe_reset_no_admin_key_configured(client):
    """Server with no admin_key set rejects every caller."""
    _configure_admin("")
    _set_poller({})
    resp = client.post("/api/admin/universe-reset")
    assert resp.status_code == 403


def test_universe_reset_wrong_key(client):
    _configure_admin("real-key")
    _set_poller({})
    resp = client.post(
        "/api/admin/universe-reset",
        headers={"X-Admin-Key": "wrong"},
    )
    assert resp.status_code == 403


def test_universe_reset_missing_header(client):
    _configure_admin("real-key")
    _set_poller({})
    resp = client.post("/api/admin/universe-reset")
    assert resp.status_code == 403


def test_universe_reset_valid_key_flushes_poller(client):
    _configure_admin("real-key")
    poller = _set_poller(
        {
            "orbital_zones": 12,
            "feral_ai_events": 45,
            "reference_data": 3,
            "tribe_cache": 7,
        }
    )
    resp = client.post(
        "/api/admin/universe-reset",
        headers={"X-Admin-Key": "real-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["flushed"]["orbital_zones"] == 12
    assert body["flushed"]["feral_ai_events"] == 45
    assert body["total_rows"] == 67
    assert "repopulate" in body["message"]
    poller.flush_polled_data.assert_called_once()



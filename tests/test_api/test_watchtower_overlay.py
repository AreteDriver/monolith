"""Tests for WatchTower map overlay proxy endpoint."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api import stats as stats_module
from backend.db.database import init_db
from backend.main import app


@pytest.fixture(autouse=True)
def _clear_caches():
    """Reset module-level caches between tests."""
    stats_module._wt_cache = None
    stats_module._wt_cache_time = 0
    stats_module._bg_systems_cache = None
    stats_module._bg_systems_etag = None
    stats_module._bg_bounds = None
    yield
    stats_module._wt_cache = None
    stats_module._wt_cache_time = 0
    stats_module._bg_systems_cache = None
    stats_module._bg_systems_etag = None
    stats_module._bg_bounds = None


@pytest.fixture
def client():
    conn = init_db(":memory:")
    app.state.db = conn
    yield TestClient(app, raise_server_exceptions=False)
    conn.close()


def _seed_reference_system(conn, system_id="30012602", name="Auga", x=100, z=200):
    """Insert a reference system for coordinate resolution."""
    data = json.dumps({"name": name, "location": {"x": x, "z": z}})
    conn.execute(
        "INSERT INTO reference_data (data_id, data_type, name, data_json) VALUES (?, ?, ?, ?)",
        (system_id, "solarsystems", name, data),
    )
    conn.commit()


def _mock_wt_responses(hotzones=None, predictions=None, assemblies=None):
    """Create a mock httpx.AsyncClient that returns specified WatchTower data."""

    async def mock_get(url, **kwargs):
        resp = AsyncMock(spec=httpx.Response)
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        if "/hotzones" in url:
            resp.json.return_value = hotzones or {"hotzones": []}
        elif "/predictions/map" in url:
            resp.json.return_value = predictions or {"systems": []}
        elif "/assemblies" in url:
            resp.json.return_value = assemblies or {
                "total": 0,
                "online": 0,
                "offline": 0,
                "systems_covered": 0,
                "by_type": {},
                "assemblies": [],
            }
        return resp

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestWatchTowerOverlay:
    """Tests for GET /api/stats/map/watchtower."""

    def test_empty_when_no_reference_data(self, client):
        """Returns empty arrays when no reference_data exists."""
        with patch("httpx.AsyncClient", return_value=_mock_wt_responses()):
            resp = client.get("/api/stats/map/watchtower")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hotzones"] == []
        assert data["threat_systems"] == []
        assert data["assemblies"] == []

    def test_hotzones_joined_with_coords(self, client):
        """Hotzone systems get normalized coordinates from reference_data."""
        conn = app.state.db
        _seed_reference_system(conn, "30012602", "Auga", x=100, z=200)
        _seed_reference_system(conn, "30012603", "Amamake", x=300, z=400)

        hotzones = {
            "hotzones": [
                {
                    "solar_system_id": "30012602",
                    "solar_system_name": "Auga",
                    "kills": 15,
                    "danger_level": "extreme",
                    "unique_attackers": 8,
                    "unique_victims": 5,
                    "latest_kill": 1000,
                },
            ]
        }

        with patch("httpx.AsyncClient", return_value=_mock_wt_responses(hotzones=hotzones)):
            resp = client.get("/api/stats/map/watchtower")

        data = resp.json()
        assert len(data["hotzones"]) == 1
        hz = data["hotzones"][0]
        assert hz["system_id"] == "30012602"
        assert hz["name"] == "Auga"
        assert hz["kills"] == 15
        assert hz["danger_level"] == "extreme"
        assert "nx" in hz
        assert "nz" in hz

    def test_threat_systems_joined(self, client):
        """Threat forecast systems get coords and are included."""
        conn = app.state.db
        _seed_reference_system(conn, "30012602", "Auga", x=100, z=200)

        predictions = {
            "systems": [
                {
                    "solar_system_id": "30012602",
                    "solar_system_name": "Auga",
                    "threat_score": 75,
                    "threat_level": "high",
                    "kill_trend": "surging",
                    "kills_7d": 10,
                },
            ]
        }

        with patch("httpx.AsyncClient", return_value=_mock_wt_responses(predictions=predictions)):
            resp = client.get("/api/stats/map/watchtower")

        data = resp.json()
        assert len(data["threat_systems"]) == 1
        ts = data["threat_systems"][0]
        assert ts["threat_score"] == 75
        assert ts["kill_trend"] == "surging"

    def test_assemblies_joined(self, client):
        """Assembly markers get coords from reference_data, not WT positions."""
        conn = app.state.db
        _seed_reference_system(conn, "30012602", "Auga", x=100, z=200)

        assemblies = {
            "total": 1,
            "online": 1,
            "offline": 0,
            "systems_covered": 1,
            "by_type": {"Refinery": 1},
            "assemblies": [
                {
                    "assembly_id": "0xabc",
                    "type": "Refinery",
                    "solar_system_id": "30012602",
                    "solar_system_name": "Auga",
                    "state": "online",
                    "position": {"x": 999, "y": 999, "z": 999},
                    "deployed_at": 1000,
                },
            ],
        }

        with patch("httpx.AsyncClient", return_value=_mock_wt_responses(assemblies=assemblies)):
            resp = client.get("/api/stats/map/watchtower")

        data = resp.json()
        assert len(data["assemblies"]) == 1
        asm = data["assemblies"][0]
        assert asm["type"] == "Refinery"
        assert asm["state"] == "online"
        # Uses reference_data coords, not WT's position
        assert "nx" in asm

    def test_unknown_system_ids_skipped(self, client):
        """Systems not in reference_data are silently skipped."""
        conn = app.state.db
        _seed_reference_system(conn, "30012602", "Auga", x=100, z=200)

        hotzones = {
            "hotzones": [
                {
                    "solar_system_id": "30012602",
                    "solar_system_name": "Auga",
                    "kills": 5,
                    "danger_level": "moderate",
                    "unique_attackers": 2,
                    "unique_victims": 3,
                    "latest_kill": 1000,
                },
                {
                    "solar_system_id": "99999999",
                    "solar_system_name": "Unknown",
                    "kills": 1,
                    "danger_level": "low",
                    "unique_attackers": 1,
                    "unique_victims": 1,
                    "latest_kill": 1000,
                },
            ]
        }

        with patch("httpx.AsyncClient", return_value=_mock_wt_responses(hotzones=hotzones)):
            resp = client.get("/api/stats/map/watchtower")

        data = resp.json()
        assert len(data["hotzones"]) == 1
        assert data["hotzones"][0]["system_id"] == "30012602"

    def test_all_fetches_fail_returns_empty(self, client):
        """When all WatchTower fetches fail, returns empty result."""
        conn = app.state.db
        _seed_reference_system(conn, "30012602", "Auga", x=100, z=200)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.get("/api/stats/map/watchtower")

        assert resp.status_code == 200
        data = resp.json()
        assert data["hotzones"] == []
        assert data["threat_systems"] == []
        assert data["assemblies"] == []

    def test_cache_serves_stale_on_failure(self, client):
        """After a successful fetch, stale cache is served on subsequent failure."""
        conn = app.state.db
        _seed_reference_system(conn, "30012602", "Auga", x=100, z=200)

        hotzones = {
            "hotzones": [
                {
                    "solar_system_id": "30012602",
                    "solar_system_name": "Auga",
                    "kills": 5,
                    "danger_level": "high",
                    "unique_attackers": 3,
                    "unique_victims": 2,
                    "latest_kill": 1000,
                },
            ]
        }

        # First call succeeds
        with patch("httpx.AsyncClient", return_value=_mock_wt_responses(hotzones=hotzones)):
            resp1 = client.get("/api/stats/map/watchtower")
        assert len(resp1.json()["hotzones"]) == 1

        # Expire cache
        stats_module._wt_cache_time = 0

        # Second call fails — should serve stale
        mock_fail = AsyncMock(spec=httpx.AsyncClient)
        mock_fail.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_fail.__aenter__ = AsyncMock(return_value=mock_fail)
        mock_fail.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_fail):
            resp2 = client.get("/api/stats/map/watchtower")

        assert resp2.status_code == 200
        assert len(resp2.json()["hotzones"]) == 1

"""Tests for public API v1 endpoints."""

import time

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.db.database import init_db
from backend.main import app


@pytest.fixture
def client():
    conn = init_db(":memory:")
    app.state.db = conn
    app.state.settings = Settings(chain="stillness")
    yield TestClient(app, raise_server_exceptions=False)
    conn.close()


def _insert_anomaly(conn, anomaly_id, severity="MEDIUM", anomaly_type="ORPHAN_OBJECT"):
    now = int(time.time())
    conn.execute(
        "INSERT INTO anomalies (anomaly_id, anomaly_type, severity, category, "
        "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            anomaly_id,
            anomaly_type,
            severity,
            "CONTINUITY",
            "continuity_checker",
            "C1",
            "obj-1",
            "30012602",
            now,
            "{}",
            "UNVERIFIED",
        ),
    )
    conn.commit()


def test_public_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.4.0"
    assert body["chain"] == "stillness"


def test_public_anomalies_empty(client):
    resp = client.get("/api/v1/anomalies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["limit"] == 50
    assert body["offset"] == 0


def test_public_anomalies_with_data(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1", "CRITICAL", "RESURRECTION")
    resp = client.get("/api/v1/anomalies")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["anomaly_id"] == "A1"
    assert data[0]["severity"] == "CRITICAL"


def test_public_stats(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1", "CRITICAL", "RESURRECTION")
    _insert_anomaly(conn, "A2", "HIGH", "STATE_GAP")
    resp = client.get("/api/v1/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["by_severity"]["CRITICAL"] == 1
    assert body["by_severity"]["HIGH"] == 1
    assert body["by_type"]["RESURRECTION"] == 1
    assert body["by_type"]["STATE_GAP"] == 1

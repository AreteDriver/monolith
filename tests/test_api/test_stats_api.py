"""Tests for stats API endpoint."""

import time

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


def test_stats_empty(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["anomaly_rate_24h"] == 0
    assert data["false_positive_rate"] == 0.0
    assert len(data["anomaly_rate_by_hour"]) == 24


def test_stats_with_anomalies(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1", "CRITICAL", "RESURRECTION")
    _insert_anomaly(conn, "A2", "HIGH", "STATE_GAP")
    _insert_anomaly(conn, "A3", "MEDIUM", "ORPHAN_OBJECT")

    resp = client.get("/api/stats")
    data = resp.json()
    assert data["anomaly_rate_24h"] == 3
    assert data["by_severity"]["CRITICAL"] == 1
    assert data["by_severity"]["HIGH"] == 1
    assert data["by_type"]["RESURRECTION"] == 1

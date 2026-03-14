"""Tests for anomalies API — enrichment and status update endpoints."""

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


def _insert_anomaly(conn, anomaly_id, system_id="30012602"):
    now = int(time.time())
    conn.execute(
        "INSERT INTO anomalies (anomaly_id, anomaly_type, severity, category, "
        "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            anomaly_id,
            "ORPHAN_OBJECT",
            "MEDIUM",
            "CONTINUITY",
            "continuity_checker",
            "C1",
            "obj-1",
            system_id,
            now,
            "{}",
            "UNVERIFIED",
        ),
    )
    conn.commit()


def _insert_reference(conn, data_id, name):
    now = int(time.time())
    conn.execute(
        "INSERT INTO reference_data (data_type, data_id, name, data_json, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("solarsystems", data_id, name, "{}", now),
    )
    conn.commit()


def test_anomaly_enrichment(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1", system_id="30012602")
    _insert_reference(conn, "30012602", "Jita")
    resp = client.get("/api/anomalies/A1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["system_name"] == "Jita"


def test_anomaly_status_update(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1")
    resp = client.patch(
        "/api/anomalies/A1/status",
        json={"status": "CONFIRMED"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CONFIRMED"
    # Verify persisted
    verify = client.get("/api/anomalies/A1")
    assert verify.json()["status"] == "CONFIRMED"


def test_anomaly_status_invalid(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1")
    resp = client.patch(
        "/api/anomalies/A1/status",
        json={"status": "BOGUS_STATUS"},
    )
    assert resp.status_code == 422

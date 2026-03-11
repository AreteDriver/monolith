"""Tests for submit API endpoint."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.db.database import init_db
from backend.main import app


@pytest.fixture
def client():
    conn = init_db(":memory:")
    app.state.db = conn

    class FakeSettings:
        anthropic_api_key = ""

    app.state.settings = FakeSettings()
    yield TestClient(app, raise_server_exceptions=False)
    conn.close()


def test_submit_no_anomaly(client):
    """Submit for unknown object returns no_anomaly_detected."""
    resp = client.post(
        "/api/submit",
        json={"object_id": "0xnonexistent", "description": "My gate broke"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "no_anomaly_detected"
    assert data["object_id"] == "0xnonexistent"


def test_submit_with_existing_anomaly(client):
    """Submit for object with existing anomaly returns anomaly_found."""
    conn = app.state.db
    now = int(time.time())

    # Insert anomaly for this object
    conn.execute(
        "INSERT INTO anomalies (anomaly_id, anomaly_type, severity, category, "
        "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "ANM-SUBMIT",
            "PHANTOM_ITEM_CHANGE",
            "HIGH",
            "STATE_INCONSISTENCY",
            "assembly_checker",
            "A4",
            "0xmygate",
            "30012602",
            now,
            json.dumps({"description": "Items changed"}),
            "UNVERIFIED",
        ),
    )
    conn.commit()

    resp = client.post(
        "/api/submit",
        json={
            "object_id": "0xmygate",
            "description": "Items disappeared from my storage unit",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "anomaly_found"
    assert data["anomaly_type"] == "PHANTOM_ITEM_CHANGE"
    assert data["severity"] == "HIGH"


def test_submit_object_status(client):
    """Status endpoint returns object health."""
    resp = client.get("/api/submit/0xtest/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object_id"] == "0xtest"
    assert data["found"] is False
    assert data["anomaly_count"] == 0

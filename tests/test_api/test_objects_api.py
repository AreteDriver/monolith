"""Tests for objects API endpoints."""

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


def _insert_object(conn, object_id="obj-001", obj_type="SmartGate"):
    now = int(time.time())
    conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, "
        "current_owner, system_id, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (object_id, obj_type, "{}", "0xowner", "30012602", now, now),
    )
    conn.commit()


def test_get_object_not_found(client):
    resp = client.get("/api/objects/NONEXISTENT")
    assert resp.json()["error"] == "not_found"


def test_get_object_found(client):
    conn = app.state.db
    _insert_object(conn)

    resp = client.get("/api/objects/obj-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"]["object_id"] == "obj-001"
    assert data["object"]["object_type"] == "SmartGate"
    assert "transitions" in data
    assert "anomalies" in data
    assert "events" in data


def test_search_objects_empty(client):
    resp = client.get("/api/objects")
    assert resp.json()["data"] == []


def test_search_objects_with_filter(client):
    conn = app.state.db
    _insert_object(conn, "obj-gate", "SmartGate")
    _insert_object(conn, "obj-turret", "SmartTurret")

    resp = client.get("/api/objects?object_type=SmartGate")
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["object_id"] == "obj-gate"

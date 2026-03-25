"""Extended tests for objects API — additional filters and edge cases."""

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
    yield TestClient(app, raise_server_exceptions=False)
    conn.close()


def _insert_object(conn, object_id, obj_type="SmartGate", system_id="30012602"):
    now = int(time.time())
    conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, "
        "current_owner, system_id, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (object_id, obj_type, '{"state": "online"}', "0xowner", system_id, now, now),
    )
    conn.commit()


def _insert_anomaly(conn, anomaly_id, object_id):
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
            "test",
            "C1",
            object_id,
            "",
            now,
            json.dumps({"description": "test"}),
            "UNVERIFIED",
        ),
    )
    conn.commit()


def test_search_by_system_id(client):
    conn = app.state.db
    _insert_object(conn, "obj-1", system_id="30012602")
    _insert_object(conn, "obj-2", system_id="30004759")
    resp = client.get("/api/objects?system_id=30012602")
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["object_id"] == "obj-1"


def test_search_by_query(client):
    conn = app.state.db
    _insert_object(conn, "0xabcdef1234")
    _insert_object(conn, "0x999888777")
    resp = client.get("/api/objects?q=abcdef")
    data = resp.json()["data"]
    assert len(data) == 1
    assert "abcdef" in data[0]["object_id"]


def test_get_object_with_anomalies(client):
    conn = app.state.db
    _insert_object(conn, "obj-1")
    _insert_anomaly(conn, "A1", "obj-1")
    resp = client.get("/api/objects/obj-1")
    data = resp.json()
    assert len(data["anomalies"]) == 1
    assert "evidence" in data["anomalies"][0]


def test_get_object_with_malformed_evidence(client):
    conn = app.state.db
    _insert_object(conn, "obj-1")
    now = int(time.time())
    conn.execute(
        "INSERT INTO anomalies (anomaly_id, anomaly_type, severity, category, "
        "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("A-bad", "TEST", "LOW", "TEST", "test", "X1", "obj-1", "", now, "not-json", "UNVERIFIED"),
    )
    conn.commit()
    resp = client.get("/api/objects/obj-1")
    anomalies = resp.json()["anomalies"]
    assert len(anomalies) == 1
    assert anomalies[0]["evidence"] == {}


def test_get_object_parses_current_state(client):
    conn = app.state.db
    _insert_object(conn, "obj-1")
    resp = client.get("/api/objects/obj-1")
    obj = resp.json()["object"]
    assert obj["current_state"] == {"state": "online"}

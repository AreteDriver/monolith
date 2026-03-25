"""Tests for anomalies API — list, filter, bulk update, coordinated-buying."""

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


def _insert_anomaly(
    conn,
    anomaly_id,
    anomaly_type="ORPHAN_OBJECT",
    severity="MEDIUM",
    system_id="",
    status="UNVERIFIED",
):
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
            "test_checker",
            "C1",
            f"obj-{anomaly_id}",
            system_id,
            now,
            json.dumps({"description": f"Test anomaly {anomaly_id}"}),
            status,
        ),
    )
    conn.commit()


# --- List anomalies ---


def test_list_anomalies_empty(client):
    resp = client.get("/api/anomalies")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_list_anomalies_returns_data(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1")
    _insert_anomaly(conn, "A2")
    resp = client.get("/api/anomalies")
    assert len(resp.json()["data"]) == 2


def test_list_filter_severity(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1", severity="HIGH")
    _insert_anomaly(conn, "A2", severity="LOW")
    resp = client.get("/api/anomalies?severity=HIGH")
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["severity"] == "HIGH"


def test_list_filter_type(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1", anomaly_type="RESURRECTION")
    _insert_anomaly(conn, "A2", anomaly_type="ORPHAN_OBJECT")
    resp = client.get("/api/anomalies?anomaly_type=RESURRECTION")
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["anomaly_type"] == "RESURRECTION"


def test_list_filter_status(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1", status="CONFIRMED")
    _insert_anomaly(conn, "A2", status="UNVERIFIED")
    resp = client.get("/api/anomalies?status=CONFIRMED")
    assert len(resp.json()["data"]) == 1


def test_list_filter_system_id(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1", system_id="30012602")
    _insert_anomaly(conn, "A2", system_id="30004759")
    resp = client.get("/api/anomalies?system_id=30012602")
    assert len(resp.json()["data"]) == 1


def test_list_pagination(client):
    conn = app.state.db
    for i in range(5):
        _insert_anomaly(conn, f"A{i}")
    resp = client.get("/api/anomalies?limit=2&offset=0")
    assert len(resp.json()["data"]) == 2
    resp2 = client.get("/api/anomalies?limit=2&offset=2")
    assert len(resp2.json()["data"]) == 2


# --- Get single anomaly ---


def test_get_anomaly_not_found(client):
    resp = client.get("/api/anomalies/NONEXISTENT")
    assert resp.json()["error"] == "not_found"


def test_get_anomaly_parses_evidence(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1")
    resp = client.get("/api/anomalies/A1")
    body = resp.json()
    assert "evidence" in body
    assert body["evidence"]["description"] == "Test anomaly A1"


# --- Bulk status update ---


def test_bulk_update_status(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1", anomaly_type="ORPHAN_OBJECT")
    _insert_anomaly(conn, "A2", anomaly_type="ORPHAN_OBJECT")
    _insert_anomaly(conn, "A3", anomaly_type="RESURRECTION")  # Different type
    resp = client.patch(
        "/api/anomalies/bulk/status",
        json={"anomaly_type": "ORPHAN_OBJECT", "status": "FALSE_POSITIVE"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == 2
    # Verify A3 unchanged
    a3 = client.get("/api/anomalies/A3").json()
    assert a3["status"] == "UNVERIFIED"


# --- Coordinated buying ---


def test_coordinated_buying_empty(client):
    resp = client.get("/api/anomalies/coordinated-buying")
    assert resp.status_code == 200
    assert resp.json()["signals"] == []


def test_coordinated_buying_returns_only_cb(client):
    conn = app.state.db
    _insert_anomaly(conn, "CB1", anomaly_type="COORDINATED_BUYING", severity="HIGH")
    _insert_anomaly(conn, "A1", anomaly_type="ORPHAN_OBJECT")
    resp = client.get("/api/anomalies/coordinated-buying")
    signals = resp.json()["signals"]
    assert len(signals) == 1
    assert signals[0]["anomaly_type"] == "COORDINATED_BUYING"


def test_coordinated_buying_filter_system(client):
    conn = app.state.db
    _insert_anomaly(conn, "CB1", anomaly_type="COORDINATED_BUYING", system_id="30012602")
    _insert_anomaly(conn, "CB2", anomaly_type="COORDINATED_BUYING", system_id="30004759")
    resp = client.get("/api/anomalies/coordinated-buying?system_id=30012602")
    assert len(resp.json()["signals"]) == 1


def test_coordinated_buying_filter_severity(client):
    conn = app.state.db
    _insert_anomaly(conn, "CB1", anomaly_type="COORDINATED_BUYING", severity="HIGH")
    _insert_anomaly(conn, "CB2", anomaly_type="COORDINATED_BUYING", severity="LOW")
    resp = client.get("/api/anomalies/coordinated-buying?severity=HIGH")
    assert len(resp.json()["signals"]) == 1


# --- System name enrichment ---


def test_anomaly_no_system_id_gets_null_name(client):
    conn = app.state.db
    _insert_anomaly(conn, "A1", system_id="")
    resp = client.get("/api/anomalies/A1")
    assert resp.json()["system_name"] is None

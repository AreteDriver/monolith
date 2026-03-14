"""Tests for stats API — ledger and pod anomaly endpoints."""

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


def _insert_ledger_row(conn, assembly_id, item_type_id, event_type="TRANSFER", quantity=10):
    now = int(time.time())
    conn.execute(
        "INSERT INTO item_ledger "
        "(assembly_id, item_type_id, event_type, quantity, event_id, transaction_hash, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (assembly_id, item_type_id, event_type, quantity, f"evt-{now}", f"tx-{now}", now),
    )
    conn.commit()


def _insert_anomaly(conn, anomaly_id, detector="pod_checker", anomaly_type="POD_MISMATCH"):
    now = int(time.time())
    conn.execute(
        "INSERT INTO anomalies (anomaly_id, anomaly_type, severity, category, "
        "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            anomaly_id,
            anomaly_type,
            "HIGH",
            "ECONOMIC",
            detector,
            "P1",
            "obj-1",
            "30012602",
            now,
            "{}",
            "UNVERIFIED",
        ),
    )
    conn.commit()


def test_stats_ledger_empty(client):
    resp = client.get("/api/stats/ledger")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_items_tracked"] == 0
    assert body["total_events"] == 0
    assert body["top_assemblies"] == []
    assert body["by_event_type"] == {}


def test_stats_ledger_with_data(client):
    conn = app.state.db
    _insert_ledger_row(conn, "asm-1", "item-A", "TRANSFER", 10)
    _insert_ledger_row(conn, "asm-1", "item-B", "MINT", 5)
    _insert_ledger_row(conn, "asm-2", "item-A", "TRANSFER", 20)
    resp = client.get("/api/stats/ledger")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_events"] == 3
    assert body["top_assemblies"][0]["assembly_id"] == "asm-1"
    assert body["top_assemblies"][0]["event_count"] == 2
    assert body["by_event_type"]["TRANSFER"] == 2
    assert body["by_event_type"]["MINT"] == 1


def test_pod_anomalies_count(client):
    conn = app.state.db
    _insert_anomaly(conn, "POD-1", detector="pod_checker", anomaly_type="POD_MISMATCH")
    _insert_anomaly(conn, "OTHER-1", detector="continuity_checker", anomaly_type="STATE_GAP")
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pod_anomalies_24h"] == 1

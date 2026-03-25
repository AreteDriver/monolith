"""Tests for NEXUS webhook consumer — event ingestion and signature verification."""

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.db.database import init_db
from backend.ingestion.nexus_consumer import (
    _verify_signature,
    configure,
)
from backend.main import app


@pytest.fixture
def client():
    conn = init_db(":memory:")
    app.state.db = conn
    configure("")  # Reset secret
    yield TestClient(app, raise_server_exceptions=False)
    conn.close()


# --- Signature verification ---


def test_verify_no_secret():
    assert _verify_signature(b"data", "sig", "") is False


def test_verify_no_signature():
    assert _verify_signature(b"data", "", "secret") is False


def test_verify_valid():
    secret = "test-secret"  # noqa: S105
    payload = b'{"event": "test"}'
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert _verify_signature(payload, sig, secret) is True


def test_verify_invalid():
    assert _verify_signature(b"data", "wrong-signature", "secret") is False


# --- Webhook endpoint ---


def test_nexus_killmail(client):
    payload = {
        "event_type": "killmail",
        "killmail_id": "km-001",
        "solar_system_id": "30012602",
        "victim": {"id": "obj-v1", "name": "Victim"},
        "killer": {"id": "obj-k1", "name": "Killer"},
    }
    resp = client.post(
        "/api/nexus/webhook",
        content=json.dumps(payload),
        headers={"X-Nexus-Event": "killmail"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    # Verify stored in nexus_events
    conn = app.state.db
    row = conn.execute("SELECT * FROM nexus_events WHERE event_type = 'killmail'").fetchone()
    assert row is not None
    assert row["event_id"] == "km-001"


def test_nexus_killmail_enriches_objects(client):
    conn = app.state.db
    now = int(time.time())
    conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("obj-v1", "SmartStorageUnit", "{}", now, now),
    )
    conn.commit()

    payload = {
        "event_type": "killmail",
        "killmail_id": "km-002",
        "solar_system_id": "30012602",
        "victim": {"id": "obj-v1"},
        "killer": {},
    }
    client.post(
        "/api/nexus/webhook",
        content=json.dumps(payload),
        headers={"X-Nexus-Event": "killmail"},
    )
    row = conn.execute("SELECT system_id FROM objects WHERE object_id = 'obj-v1'").fetchone()
    assert row["system_id"] == "30012602"


def test_nexus_gate_transit(client):
    payload = {
        "gate_id": "gate-001",
        "timestamp": 12345,
        "solar_system_id": "30001234",
    }
    resp = client.post(
        "/api/nexus/webhook",
        content=json.dumps(payload),
        headers={"X-Nexus-Event": "gate_transit"},
    )
    assert resp.json()["status"] == "accepted"
    conn = app.state.db
    row = conn.execute("SELECT * FROM nexus_events WHERE event_type = 'gate_transit'").fetchone()
    assert row is not None


def test_nexus_gate_permit(client):
    payload = {
        "permit_id": "permit-001",
        "solar_system_id": "30001234",
    }
    resp = client.post(
        "/api/nexus/webhook",
        content=json.dumps(payload),
        headers={"X-Nexus-Event": "gate_permit"},
    )
    assert resp.json()["status"] == "accepted"
    conn = app.state.db
    row = conn.execute("SELECT * FROM nexus_events WHERE event_type = 'gate_permit'").fetchone()
    assert row is not None


def test_nexus_unknown_event(client):
    resp = client.post(
        "/api/nexus/webhook",
        content=json.dumps({"event_type": "mystery"}),
        headers={"X-Nexus-Event": "mystery"},
    )
    assert resp.json()["status"] == "ignored"


def test_nexus_invalid_json(client):
    resp = client.post(
        "/api/nexus/webhook",
        content=b"not-json",
        headers={"X-Nexus-Event": "killmail"},
    )
    assert resp.json()["status"] == "rejected"


def test_nexus_signature_rejection(client):
    configure("real-secret")
    resp = client.post(
        "/api/nexus/webhook",
        content=json.dumps({"event_type": "killmail", "killmail_id": "km-x"}),
        headers={"X-Nexus-Event": "killmail", "X-Nexus-Signature": "bad-sig"},
    )
    assert resp.json()["status"] == "rejected"
    configure("")  # Reset


def test_nexus_signature_pass(client):
    secret = "test-secret-123"  # noqa: S105
    configure(secret)
    payload = json.dumps({"event_type": "killmail", "killmail_id": "km-sig"}).encode()
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    resp = client.post(
        "/api/nexus/webhook",
        content=payload,
        headers={"X-Nexus-Event": "killmail", "X-Nexus-Signature": sig},
    )
    assert resp.json()["status"] == "accepted"
    configure("")  # Reset

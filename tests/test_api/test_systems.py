"""Tests for systems API endpoints."""

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


def _insert_reference(conn, data_id, name, data_json=None):
    now = int(time.time())
    conn.execute(
        "INSERT INTO reference_data (data_type, data_id, name, data_json, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("solarsystems", data_id, name, data_json or "{}", now),
    )
    conn.commit()


def test_resolve_empty_ids(client):
    resp = client.get("/api/systems/resolve", params={"ids": ""})
    assert resp.status_code == 200
    assert resp.json() == {"data": {}}


def test_resolve_known_system(client):
    conn = app.state.db
    _insert_reference(conn, "30012602", "Jita")
    resp = client.get("/api/systems/resolve", params={"ids": "30012602"})
    assert resp.status_code == 200
    assert resp.json()["data"]["30012602"] == "Jita"


def test_resolve_unknown_system(client):
    resp = client.get("/api/systems/resolve", params={"ids": "99999999"})
    assert resp.status_code == 200
    assert resp.json()["data"] == {}


def test_get_system_found(client):
    conn = app.state.db
    payload = json.dumps({"x": 1.0, "y": 2.0, "z": 3.0})
    _insert_reference(conn, "30012602", "Jita", data_json=payload)
    resp = client.get("/api/systems/30012602")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Jita"
    assert body["data"]["x"] == 1.0


def test_get_system_not_found(client):
    resp = client.get("/api/systems/99999999")
    assert resp.status_code == 200
    assert resp.json()["error"] == "not_found"


def test_get_system_malformed_json(client):
    conn = app.state.db
    _insert_reference(conn, "30012602", "Jita", data_json="not-valid-json")
    resp = client.get("/api/systems/30012602")
    body = resp.json()
    assert body["name"] == "Jita"
    assert body["data"] == {}


def test_resolve_multiple_systems(client):
    conn = app.state.db
    _insert_reference(conn, "30012602", "Jita")
    _insert_reference(conn, "30004759", "Amarr")
    resp = client.get("/api/systems/resolve", params={"ids": "30012602,30004759"})
    data = resp.json()["data"]
    assert data["30012602"] == "Jita"
    assert data["30004759"] == "Amarr"

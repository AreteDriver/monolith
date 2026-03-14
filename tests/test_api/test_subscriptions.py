"""Tests for subscriptions API endpoints."""

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


def _create_sub(client, webhook_url="https://discord.com/api/webhooks/test"):
    return client.post(
        "/api/subscriptions",
        json={
            "webhook_url": webhook_url,
            "severity_filter": ["CRITICAL"],
            "event_types": ["RESURRECTION"],
        },
    )


def test_create_subscription(client):
    resp = _create_sub(client)
    assert resp.status_code == 200
    body = resp.json()
    assert "sub_id" in body
    assert body["webhook_url"] == "https://discord.com/api/webhooks/test"
    assert body["severity_filter"] == ["CRITICAL"]


def test_list_subscriptions(client):
    _create_sub(client, "https://discord.com/api/webhooks/one")
    _create_sub(client, "https://discord.com/api/webhooks/two")
    resp = client.get("/api/subscriptions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2


def test_delete_subscription(client):
    create_resp = _create_sub(client)
    sub_id = create_resp.json()["sub_id"]
    del_resp = client.delete(f"/api/subscriptions/{sub_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] == sub_id
    # Verify not in active list
    list_resp = client.get("/api/subscriptions")
    assert len(list_resp.json()["data"]) == 0


def test_delete_nonexistent(client):
    resp = client.delete("/api/subscriptions/does-not-exist")
    assert resp.status_code == 200
    assert resp.json()["error"] == "not_found"

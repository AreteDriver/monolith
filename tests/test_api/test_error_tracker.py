"""Tests for error tracker — ring buffer and admin endpoint."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.api.error_tracker import _error_buffer, capture_error, get_errors
from backend.db.database import init_db
from backend.main import app


@pytest.fixture(autouse=True)
def clear_buffer():
    _error_buffer.clear()
    yield
    _error_buffer.clear()


@pytest.fixture
def client():
    conn = init_db(":memory:")
    app.state.db = conn
    yield TestClient(app, raise_server_exceptions=False)
    conn.close()


def test_capture_error():
    request = MagicMock()
    request.url.path = "/api/test"
    request.method = "GET"

    try:
        raise ValueError("test error")
    except ValueError as e:
        capture_error(request, e)

    errors = get_errors()
    assert len(errors) == 1
    assert errors[0]["path"] == "/api/test"
    assert errors[0]["method"] == "GET"
    assert errors[0]["error_type"] == "ValueError"
    assert "test error" in errors[0]["message"]
    assert "traceback" in errors[0]


def test_get_errors_empty():
    assert get_errors() == []


def test_capture_multiple_errors():
    for i in range(3):
        request = MagicMock()
        request.url.path = f"/api/test{i}"
        request.method = "POST"
        try:
            raise RuntimeError(f"error {i}")
        except RuntimeError as e:
            capture_error(request, e)

    errors = get_errors()
    assert len(errors) == 3


def test_admin_errors_no_key(client):
    """Admin endpoint returns 403 when no admin key configured."""
    settings = MagicMock()
    settings.admin_key = ""
    app.state.settings = settings

    resp = client.get("/api/admin/errors")
    assert resp.status_code == 403


def test_admin_errors_wrong_key(client):
    settings = MagicMock()
    settings.admin_key = "real-key"
    app.state.settings = settings

    resp = client.get("/api/admin/errors", headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 403


def test_admin_errors_valid_key(client):
    settings = MagicMock()
    settings.admin_key = "real-key"
    app.state.settings = settings

    resp = client.get("/api/admin/errors", headers={"X-Admin-Key": "real-key"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["errors"] == []

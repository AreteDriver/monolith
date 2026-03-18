"""Tests for reports API endpoints."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.db.database import init_db
from backend.main import app


@pytest.fixture
def client():
    """Test client with in-memory DB."""
    conn = init_db(":memory:")
    app.state.db = conn

    class FakeSettings:
        anthropic_api_key = ""

    app.state.settings = FakeSettings()
    yield TestClient(app, raise_server_exceptions=False)
    conn.close()


def _insert_anomaly(conn, anomaly_id="ANM-001", anomaly_type="ORPHAN_OBJECT"):
    now = int(time.time())
    conn.execute(
        "INSERT INTO anomalies (anomaly_id, anomaly_type, severity, category, "
        "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            anomaly_id,
            anomaly_type,
            "MEDIUM",
            "CONTINUITY",
            "continuity_checker",
            "C1",
            "obj-1",
            "30012602",
            now,
            json.dumps({"description": "Test anomaly", "transaction_hash": "0xabc"}),
            "UNVERIFIED",
        ),
    )
    conn.commit()


def _insert_report(conn, report_id="RPT-001", anomaly_id="ANM-001"):
    now = int(time.time())
    conn.execute(
        "INSERT INTO bug_reports (report_id, anomaly_id, title, severity, category, "
        "summary, evidence_json, plain_english, chain_references, "
        "reproduction_context, recommended_investigation, generated_at, "
        "format_markdown, format_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            report_id,
            anomaly_id,
            "Test Report",
            "MEDIUM",
            "CONTINUITY",
            "Test summary",
            "{}",
            "Plain text.",
            "[]",
            "{}",
            "[]",
            now,
            "# Report",
            "{}",
        ),
    )
    conn.commit()


def test_list_reports_empty(client):
    """Empty reports list returns empty data array."""
    resp = client.get("/api/reports")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_list_reports_with_data(client):
    """Reports list returns stored reports."""
    conn = app.state.db
    _insert_anomaly(conn)
    _insert_report(conn)

    resp = client.get("/api/reports")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["report_id"] == "RPT-001"


def test_list_reports_severity_filter(client):
    """Reports list filters by severity."""
    conn = app.state.db
    _insert_anomaly(conn, "ANM-1")
    _insert_report(conn, "RPT-1", "ANM-1")

    resp = client.get("/api/reports?severity=CRITICAL")
    assert resp.json()["data"] == []

    resp = client.get("/api/reports?severity=MEDIUM")
    assert len(resp.json()["data"]) == 1


def test_get_report_not_found(client):
    """Get report returns error for unknown ID."""
    resp = client.get("/api/reports/NONEXISTENT")
    assert resp.status_code == 200
    assert resp.json()["error"] == "not_found"


def test_get_report_json(client):
    """Get report returns JSON format by default."""
    conn = app.state.db
    _insert_anomaly(conn)
    _insert_report(conn)

    resp = client.get("/api/reports/RPT-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_id"] == "RPT-001"


def test_get_report_markdown(client):
    """Get report returns markdown when requested."""
    conn = app.state.db
    _insert_anomaly(conn)
    _insert_report(conn)

    resp = client.get("/api/reports/RPT-001?fmt=markdown")
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "markdown"
    assert "MONOLITH" in data["content"]
    assert "FIELD DISPATCH" in data["content"]


def test_get_report_text(client):
    """Get report returns plain text when requested."""
    conn = app.state.db
    _insert_anomaly(conn)
    _insert_report(conn)

    resp = client.get("/api/reports/RPT-001?fmt=text")
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "text"
    assert "MONOLITH" in data["content"]
    assert "FIELD DISPATCH" in data["content"]


def test_generate_report_missing_anomaly(client):
    """Generate report returns error for unknown anomaly."""
    resp = client.post("/api/reports/generate?anomaly_id=NONEXISTENT")
    assert resp.status_code == 200
    assert resp.json()["error"] == "anomaly_not_found"


def test_generate_report_success(client):
    """Generate report creates a new report from anomaly."""
    conn = app.state.db
    _insert_anomaly(conn)

    resp = client.post("/api/reports/generate?anomaly_id=ANM-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] is True
    assert data["report_id"].startswith("MNLT-")
    assert data["anomaly_id"] == "ANM-001"

    # Verify persisted
    row = conn.execute(
        "SELECT * FROM bug_reports WHERE report_id = ?", (data["report_id"],)
    ).fetchone()
    assert row is not None


def test_generate_report_duplicate_blocked(client):
    """Cannot generate two reports for same anomaly."""
    conn = app.state.db
    _insert_anomaly(conn)

    resp1 = client.post("/api/reports/generate?anomaly_id=ANM-001")
    assert resp1.json()["generated"] is True

    resp2 = client.post("/api/reports/generate?anomaly_id=ANM-001")
    assert resp2.json()["error"] == "report_exists"

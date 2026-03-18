"""Tests for report builder — build, store, and helpers."""

import json
import time

from backend.reports.report_builder import (
    build_report,
    generate_report_id,
    store_report,
)


def test_report_id_format():
    """Report ID matches MNLT-YYYYMMDD-NNNN format."""
    rid = generate_report_id()
    assert rid.startswith("MNLT-")
    parts = rid.split("-")
    assert len(parts) == 3
    assert len(parts[1]) == 8  # YYYYMMDD
    assert len(parts[2]) == 4  # seq


def _make_anomaly_row(anomaly_type="ORPHAN_OBJECT", severity="MEDIUM", category="CONTINUITY"):
    now = int(time.time())
    return {
        "anomaly_id": f"MNLT-20260311-{now % 10000:04d}",
        "anomaly_type": anomaly_type,
        "severity": severity,
        "category": category,
        "detector": "continuity_checker",
        "rule_id": "C1",
        "object_id": "0xabcdef1234567890abcdef1234567890abcdef12",
        "system_id": "30012602",
        "detected_at": now,
        "evidence_json": json.dumps(
            {
                "description": "Event for unknown object",
                "transaction_hash": "0xdeadbeef",
                "block_number": 12345,
            }
        ),
        "status": "UNVERIFIED",
    }


def test_build_report_has_all_sections():
    """Built report contains all required fields."""
    report = build_report(_make_anomaly_row())

    assert report["report_id"].startswith("MNLT-")
    assert report["severity"] == "MEDIUM"
    assert report["category"] == "CONTINUITY"
    assert report["summary"]
    assert isinstance(report["affected_entities"], dict)
    assert report["evidence_json"]
    assert report["chain_references"]
    assert report["reproduction_context"]
    assert report["recommended_investigation"]
    assert report["generated_at"] > 0
    assert report["plain_english"] == ""  # filled by narrator later


def test_build_report_chain_references():
    """Chain references extracted from evidence."""
    report = build_report(_make_anomaly_row())
    refs = json.loads(report["chain_references"])
    assert len(refs) == 2  # tx + block
    assert refs[0]["type"] == "transaction"
    assert refs[0]["hash"] == "0xdeadbeef"
    assert refs[1]["type"] == "block"
    assert refs[1]["number"] == 12345


def test_build_report_investigation_steps():
    """Investigation steps match anomaly type."""
    report = build_report(_make_anomaly_row("RESURRECTION", "CRITICAL", "CONTINUITY"))
    steps = json.loads(report["recommended_investigation"])
    assert isinstance(steps, list)
    assert len(steps) >= 3
    assert any("destruction" in s.lower() for s in steps)


def test_build_report_title_truncates_long_ids():
    """Title truncates long object IDs."""
    report = build_report(_make_anomaly_row())
    assert "..." in report["title"]


def test_build_report_with_db_enrichment(db_conn):
    """Build report enriches affected entities from objects table."""
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, current_owner, current_state, "
        "last_seen, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("obj-enrich", "SmartGate", "0xowner123", "{}", int(time.time()), int(time.time())),
    )
    db_conn.commit()

    row = _make_anomaly_row()
    row["object_id"] = "obj-enrich"
    report = build_report(row, db_conn)

    assert report["affected_entities"]["object_type"] == "SmartGate"
    assert report["affected_entities"]["owner"] == "0xowner123"


def test_store_report(db_conn):
    """Store report persists to bug_reports table and links anomaly."""
    now = int(time.time())
    # Insert anomaly first (FK)
    db_conn.execute(
        "INSERT INTO anomalies (anomaly_id, anomaly_type, severity, category, "
        "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "ANM-001",
            "ORPHAN_OBJECT",
            "MEDIUM",
            "CONTINUITY",
            "continuity_checker",
            "C1",
            "obj-1",
            "",
            now,
            "{}",
            "UNVERIFIED",
        ),
    )
    db_conn.commit()

    report = build_report({**_make_anomaly_row(), "anomaly_id": "ANM-001"})
    report["format_markdown"] = "# Test"
    report["format_json"] = "{}"

    assert store_report(report, db_conn) is True

    row = db_conn.execute(
        "SELECT * FROM bug_reports WHERE report_id = ?", (report["report_id"],)
    ).fetchone()
    assert row is not None
    assert row["anomaly_id"] == "ANM-001"

    # Verify anomaly was updated
    anomaly = db_conn.execute(
        "SELECT report_id FROM anomalies WHERE anomaly_id = 'ANM-001'"
    ).fetchone()
    assert anomaly["report_id"] == report["report_id"]

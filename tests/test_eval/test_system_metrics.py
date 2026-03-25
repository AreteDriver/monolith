"""Tests for eval/system_metrics.py metric collectors."""

import time

from eval.system_metrics import (
    collect_anomaly_rate,
    collect_cost,
    collect_db_health,
    collect_latency,
    collect_poll_drift,
)


def _insert_anomaly(conn, anomaly_id):
    now = int(time.time())
    conn.execute(
        "INSERT OR IGNORE INTO anomalies (anomaly_id, anomaly_type, severity, category, "
        "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (anomaly_id, "TEST", "HIGH", "TEST", "t", "X1", "obj", "", now, "{}", "UNVERIFIED"),
    )
    conn.commit()


# --- collect_latency ---


def test_latency_no_table(db_conn):
    """Gracefully handles missing detection_cycles table."""
    # detection_cycles exists in our schema now, so this always works
    result = collect_latency(db_conn)
    # No data yet
    assert result.sample_count == 0


def test_latency_with_data(db_conn):
    now = time.time()
    for i in range(5):
        db_conn.execute(
            "INSERT INTO detection_cycles (started_at, finished_at, anomalies_found) "
            "VALUES (?, ?, ?)",
            (now + i * 300, now + i * 300 + 0.2 + i * 0.1, i),
        )
    db_conn.commit()
    result = collect_latency(db_conn)
    assert result.available is True
    assert result.sample_count == 5
    assert result.p50_ms is not None
    assert result.p95_ms is not None
    assert result.p50_ms > 0


# --- collect_cost ---


def test_cost_no_token_data(db_conn):
    """Reports exist but no token data."""
    now = int(time.time())
    _insert_anomaly(db_conn, "A1")
    db_conn.execute(
        "INSERT INTO bug_reports (report_id, anomaly_id, generated_at) VALUES (?, ?, ?)",
        ("R1", "A1", now),
    )
    db_conn.commit()
    result = collect_cost(db_conn)
    assert result.total_reports == 1
    assert result.reports_with_token_data == 0
    assert result.estimated_cost_per_report_usd is None


def test_cost_with_token_data(db_conn):
    now = int(time.time())
    _insert_anomaly(db_conn, "A1")
    db_conn.execute(
        "INSERT INTO bug_reports "
        "(report_id, anomaly_id, generated_at, input_tokens, output_tokens) "
        "VALUES (?, ?, ?, ?, ?)",
        ("R1", "A1", now, 500, 100),
    )
    db_conn.commit()
    result = collect_cost(db_conn)
    assert result.reports_with_token_data == 1
    assert result.avg_input_tokens == 500.0
    assert result.avg_output_tokens == 100.0
    assert result.estimated_cost_per_report_usd is not None
    assert result.estimated_cost_per_report_usd > 0


# --- collect_anomaly_rate ---


def test_anomaly_rate_empty(db_conn):
    result = collect_anomaly_rate(db_conn, window_hours=24)
    assert result.anomalies_in_window == 0
    assert result.rate_per_hour == 0.0


def test_anomaly_rate_with_data(db_conn):
    now = int(time.time())
    for i in range(10):
        db_conn.execute(
            "INSERT INTO anomalies (anomaly_id, anomaly_type, severity, category, "
            "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"A{i}",
                "TEST",
                "HIGH" if i < 7 else "LOW",
                "TEST",
                "t",
                "X1",
                f"obj-{i}",
                "",
                now - 100,
                "{}",
                "UNVERIFIED",
            ),
        )
    db_conn.commit()
    result = collect_anomaly_rate(db_conn, window_hours=24)
    assert result.anomalies_in_window == 10
    assert result.rate_per_hour > 0
    assert result.severity_breakdown.get("HIGH") == 7
    assert result.severity_breakdown.get("LOW") == 3


# --- collect_poll_drift ---


def test_poll_drift_insufficient_data(db_conn):
    result = collect_poll_drift(db_conn)
    assert result.available is False


def test_poll_drift_with_data(db_conn):
    now = time.time()
    for i in range(5):
        db_conn.execute(
            "INSERT INTO detection_cycles (started_at, finished_at) VALUES (?, ?)",
            (now + i * 300, now + i * 300 + 0.5),
        )
    db_conn.commit()
    result = collect_poll_drift(db_conn)
    assert result.available is True
    assert result.avg_actual_interval_s is not None
    assert result.drift_pct is not None
    assert result.sample_count == 5


# --- collect_db_health ---


def test_db_health(db_conn):
    result = collect_db_health(db_conn)
    assert result.chain_events == 0
    assert result.anomalies == 0
    assert result.bug_reports == 0
    assert result.detection_cycles == 0

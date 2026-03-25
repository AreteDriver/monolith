"""Tests for detection engine — orchestration, dedup, persistence."""

import time

from backend.detection.engine import DetectionEngine


def _insert_chain_event(conn, event_id, object_id="unknown-obj"):
    conn.execute(
        "INSERT INTO chain_events (event_id, event_type, object_id, block_number, "
        "transaction_hash, timestamp, processed) VALUES (?, ?, ?, ?, ?, ?, 0)",
        (event_id, "test", object_id, 100, f"tx-{event_id}", int(time.time())),
    )
    conn.commit()


def test_engine_registers_all_checkers(db_conn):
    """Engine registers all 18 checker types."""
    engine = DetectionEngine(db_conn)
    assert len(engine._checkers) == 18


def test_engine_runs_and_stores_anomalies(db_conn):
    """Engine detects and stores anomalies in the database."""
    # Create an orphan event (C1 should fire)
    _insert_chain_event(db_conn, "evt-orphan", object_id="nonexistent-obj")

    engine = DetectionEngine(db_conn)
    new = engine.run_cycle()

    assert len(new) >= 1
    # Verify it was persisted
    row = db_conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()
    assert row[0] >= 1


def test_engine_deduplicates(db_conn):
    """Engine does not create duplicate anomalies for same type+object."""
    _insert_chain_event(db_conn, "evt-1", object_id="orphan-obj")

    engine = DetectionEngine(db_conn)
    first_run = engine.run_cycle()
    second_run = engine.run_cycle()

    # First run should find anomalies, second run should find 0 new
    assert len(first_run) >= 1
    assert len(second_run) == 0


def test_engine_anomaly_counts(db_conn):
    """Engine tracks anomaly counts by severity and type."""
    _insert_chain_event(db_conn, "evt-1", object_id="orphan-1")
    _insert_chain_event(db_conn, "evt-2", object_id="orphan-2")

    engine = DetectionEngine(db_conn)
    engine.run_cycle()

    counts = engine.get_anomaly_counts()
    assert "by_severity" in counts
    assert "by_type" in counts
    # Should have at least MEDIUM severity (C1 = MEDIUM)
    assert sum(counts["by_severity"].values()) >= 2

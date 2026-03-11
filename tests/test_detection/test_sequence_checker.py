"""Tests for sequence checker — S2, S4 rules."""

import time

from backend.detection.sequence_checker import SequenceChecker


def _insert_event(conn, event_id, tx_hash, block, event_type="test"):
    conn.execute(
        "INSERT INTO chain_events (event_id, event_type, object_id, block_number, "
        "transaction_hash, timestamp, processed) VALUES (?, ?, ?, ?, ?, ?, 0)",
        (event_id, event_type, "", block, tx_hash, int(time.time())),
    )
    conn.commit()


def test_s2_high_event_count(db_conn):
    """S2: Transaction with >20 events triggers DUPLICATE_TRANSACTION."""
    for i in range(25):
        _insert_event(db_conn, f"tx-spam:0x{i:02x}", "tx-spam", 100)

    checker = SequenceChecker(db_conn)
    anomalies = checker.check()

    dupes = [a for a in anomalies if a.anomaly_type == "DUPLICATE_TRANSACTION"]
    assert len(dupes) >= 1
    assert dupes[0].evidence["event_count"] == 25


def test_s2_normal_event_count_no_flag(db_conn):
    """S2: Transaction with <=20 events does not trigger."""
    for i in range(5):
        _insert_event(db_conn, f"tx-ok:0x{i}", "tx-ok", 100)

    checker = SequenceChecker(db_conn)
    anomalies = checker.check()

    dupes = [a for a in anomalies if a.anomaly_type == "DUPLICATE_TRANSACTION"]
    assert len(dupes) == 0


def test_s4_block_gap(db_conn):
    """S4: Large block gap triggers BLOCK_PROCESSING_GAP."""
    _insert_event(db_conn, "evt-1", "tx-1", 1000)
    _insert_event(db_conn, "evt-2", "tx-2", 1200)  # gap of 200

    checker = SequenceChecker(db_conn)
    anomalies = checker.check()

    gaps = [a for a in anomalies if a.anomaly_type == "BLOCK_PROCESSING_GAP"]
    assert len(gaps) >= 1
    assert gaps[0].evidence["gap_size"] == 200


def test_s4_no_gap_within_threshold(db_conn):
    """S4: Small block gap does not trigger."""
    _insert_event(db_conn, "evt-1", "tx-1", 1000)
    _insert_event(db_conn, "evt-2", "tx-2", 1050)  # gap of 50, under 100

    checker = SequenceChecker(db_conn)
    anomalies = checker.check()

    gaps = [a for a in anomalies if a.anomaly_type == "BLOCK_PROCESSING_GAP"]
    assert len(gaps) == 0

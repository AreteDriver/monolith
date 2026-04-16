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


def test_s2_disabled(db_conn):
    """S2: DUPLICATE_TRANSACTION rule is disabled (high FP rate from batch ops)."""
    for i in range(55):
        _insert_event(db_conn, f"tx-spam:0x{i:02x}", "tx-spam", 100)

    checker = SequenceChecker(db_conn)
    anomalies = checker.check()

    dupes = [a for a in anomalies if a.anomaly_type == "DUPLICATE_TRANSACTION"]
    assert len(dupes) == 0


def test_s2_fuel_events_excluded(db_conn):
    """S2: Fuel batch ticks (30+ per tx) do not trigger — normal game behavior."""
    fuel_type = "0xd12a70c74c1e::fuel::FuelEvent"
    for i in range(60):
        _insert_event(db_conn, f"fuel:{i}", "tx-fuel-batch", 100, fuel_type)

    checker = SequenceChecker(db_conn)
    anomalies = checker.check()

    dupes = [a for a in anomalies if a.anomaly_type == "DUPLICATE_TRANSACTION"]
    assert len(dupes) == 0


def test_s2_normal_event_count_no_flag(db_conn):
    """S2: Transaction with <=50 non-fuel events does not trigger."""
    for i in range(20):
        _insert_event(db_conn, f"tx-ok:0x{i}", "tx-ok", 100)

    checker = SequenceChecker(db_conn)
    anomalies = checker.check()

    dupes = [a for a in anomalies if a.anomaly_type == "DUPLICATE_TRANSACTION"]
    assert len(dupes) == 0


def test_s2_mixed_fuel_and_nonfuel(db_conn):
    """S2: Mixed tx with fuel + non-fuel only counts non-fuel events."""
    fuel_type = "0xd12a70c74c1e::fuel::FuelEvent"
    # 40 fuel events (excluded) + 10 non-fuel events (under threshold)
    for i in range(40):
        _insert_event(db_conn, f"fuel-mix:{i}", "tx-mixed", 100, fuel_type)
    for i in range(10):
        _insert_event(db_conn, f"other-mix:{i}", "tx-mixed", 100, "GateEvent")

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


# ── S2 direct method tests (disabled in check() but logic still exists) ──────


def test_s2_direct_high_event_count(db_conn):
    """S2: Direct call to _check_s2 flags >50 non-fuel events per tx."""
    for i in range(55):
        _insert_event(db_conn, f"spam:{i}", "tx-spam", 100, "0xpkg::gate::GateEvent")

    checker = SequenceChecker(db_conn)
    anomalies = checker._check_s2_duplicate_transactions()

    assert len(anomalies) == 1
    assert anomalies[0].anomaly_type == "DUPLICATE_TRANSACTION"
    assert anomalies[0].evidence["event_count"] == 55


def test_s2_direct_under_threshold(db_conn):
    """S2: Direct call with <=50 events does not flag."""
    for i in range(50):
        _insert_event(db_conn, f"ok:{i}", "tx-ok", 100, "0xpkg::gate::GateEvent")

    checker = SequenceChecker(db_conn)
    anomalies = checker._check_s2_duplicate_transactions()
    assert len(anomalies) == 0


def test_s2_direct_fuel_excluded(db_conn):
    """S2: Direct call excludes fuel events from count."""
    fuel_type = "0xd12a::fuel::FuelEvent"
    for i in range(60):
        _insert_event(db_conn, f"fuel-only:{i}", "tx-fuel", 100, fuel_type)

    checker = SequenceChecker(db_conn)
    anomalies = checker._check_s2_duplicate_transactions()
    assert len(anomalies) == 0


def test_s4_single_block_no_gap(db_conn):
    """S4: Single block number produces no gap anomaly."""
    _insert_event(db_conn, "single-1", "tx-1", 500)

    checker = SequenceChecker(db_conn)
    anomalies = checker.check()
    gaps = [a for a in anomalies if a.anomaly_type == "BLOCK_PROCESSING_GAP"]
    assert len(gaps) == 0


def test_s4_multiple_gaps(db_conn):
    """S4: Multiple large gaps each produce an anomaly."""
    _insert_event(db_conn, "evt-a", "tx-a", 1000)
    _insert_event(db_conn, "evt-b", "tx-b", 1200)  # gap 200
    _insert_event(db_conn, "evt-c", "tx-c", 1500)  # gap 300

    checker = SequenceChecker(db_conn)
    anomalies = checker.check()
    gaps = [a for a in anomalies if a.anomaly_type == "BLOCK_PROCESSING_GAP"]
    assert len(gaps) == 2
    assert gaps[0].evidence["gap_size"] == 200
    assert gaps[1].evidence["gap_size"] == 300


def test_s4_zero_block_numbers_excluded(db_conn):
    """S4: Block number 0 is excluded from gap analysis."""
    _insert_event(db_conn, "evt-zero", "tx-z", 0)
    _insert_event(db_conn, "evt-real", "tx-r", 500)

    checker = SequenceChecker(db_conn)
    anomalies = checker.check()
    gaps = [a for a in anomalies if a.anomaly_type == "BLOCK_PROCESSING_GAP"]
    assert len(gaps) == 0

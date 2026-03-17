"""Tests for coordinated buying checker — fleet staging signal detection."""

import json
import time

from backend.detection.coordinated_buying_checker import (
    MIN_BUYERS_CRITICAL,
    MIN_BUYERS_MEDIUM,
    WINDOW_SECONDS,
    CoordinatedBuyingChecker,
)


def _seed_event(
    conn,
    event_id: str,
    sender: str,
    system_id: str,
    event_type: str = "ItemDepositedEvent",
    timestamp: int | None = None,
):
    """Insert a chain event with sender in raw_json."""
    ts = timestamp or int(time.time())
    raw = json.dumps({"sender": sender, "type": event_type})
    conn.execute(
        """INSERT INTO chain_events
           (event_id, event_type, object_id, object_type, system_id,
            block_number, transaction_hash, timestamp, raw_json, processed)
           VALUES (?, ?, ?, '', ?, 0, ?, ?, ?, 1)""",
        (event_id, f"pkg::{event_type}", system_id, system_id, event_id, ts, raw),
    )
    conn.commit()


def test_below_threshold_no_anomaly(db_conn):
    """2 buyers in same system — below threshold, no anomaly."""
    checker = CoordinatedBuyingChecker(db_conn)
    now = int(time.time())
    _seed_event(db_conn, "e1", "0xbuyer1", "sys-100", timestamp=now)
    _seed_event(db_conn, "e2", "0xbuyer2", "sys-100", timestamp=now)

    anomalies = checker.check()
    assert len(anomalies) == 0


def test_medium_severity_three_buyers(db_conn):
    """3 unique buyers in same system → CB1 medium."""
    checker = CoordinatedBuyingChecker(db_conn)
    now = int(time.time())
    for i in range(MIN_BUYERS_MEDIUM):
        _seed_event(db_conn, f"e{i}", f"0xbuyer{i}", "sys-200", timestamp=now)

    anomalies = checker.check()
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.rule_id == "CB1"
    assert a.severity == "MEDIUM"
    assert a.anomaly_type == "COORDINATED_BUYING"
    assert a.system_id == "sys-200"
    assert a.evidence["buyer_count"] == MIN_BUYERS_MEDIUM
    assert a.evidence["confidence"] == 0.65


def test_critical_severity_five_buyers(db_conn):
    """5+ unique buyers in same system → CB2 critical."""
    checker = CoordinatedBuyingChecker(db_conn)
    now = int(time.time())
    for i in range(MIN_BUYERS_CRITICAL):
        _seed_event(db_conn, f"e{i}", f"0xbuyer{i}", "sys-300", timestamp=now)

    anomalies = checker.check()
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.rule_id == "CB2"
    assert a.severity == "CRITICAL"
    assert a.evidence["buyer_count"] == MIN_BUYERS_CRITICAL
    assert a.evidence["confidence"] == 0.92


def test_critical_fleet_intel_three_buyers(db_conn):
    """3 buyers + 3 fleet-type events → CB2 critical."""
    checker = CoordinatedBuyingChecker(db_conn)
    now = int(time.time())
    # OwnerCapTransferred = "fleet" intel type
    for i in range(3):
        _seed_event(
            db_conn,
            f"e{i}",
            f"0xbuyer{i}",
            "sys-400",
            event_type="OwnerCapTransferred",
            timestamp=now,
        )

    anomalies = checker.check()
    assert len(anomalies) == 1
    assert anomalies[0].rule_id == "CB2"


def test_window_pruning(db_conn):
    """Events outside the window are excluded."""
    checker = CoordinatedBuyingChecker(db_conn)
    now = int(time.time())
    old = now - WINDOW_SECONDS - 60  # 1 minute before window

    # 2 old events + 1 new = only 1 buyer in window
    _seed_event(db_conn, "e1", "0xbuyer1", "sys-500", timestamp=old)
    _seed_event(db_conn, "e2", "0xbuyer2", "sys-500", timestamp=old)
    _seed_event(db_conn, "e3", "0xbuyer3", "sys-500", timestamp=now)

    anomalies = checker.check()
    assert len(anomalies) == 0


def test_different_systems_not_merged(db_conn):
    """Buyers in different systems are counted separately."""
    checker = CoordinatedBuyingChecker(db_conn)
    now = int(time.time())
    _seed_event(db_conn, "e1", "0xbuyer1", "sys-A", timestamp=now)
    _seed_event(db_conn, "e2", "0xbuyer2", "sys-A", timestamp=now)
    _seed_event(db_conn, "e3", "0xbuyer3", "sys-B", timestamp=now)

    anomalies = checker.check()
    assert len(anomalies) == 0  # Neither system hits 3 buyers


def test_same_buyer_counted_once(db_conn):
    """Same buyer making multiple purchases counts as 1 unique buyer."""
    checker = CoordinatedBuyingChecker(db_conn)
    now = int(time.time())
    # Same buyer, 5 events
    for i in range(5):
        _seed_event(db_conn, f"e{i}", "0xsame_buyer", "sys-600", timestamp=now)
    # Plus 1 other buyer
    _seed_event(db_conn, "e99", "0xother_buyer", "sys-600", timestamp=now)

    anomalies = checker.check()
    assert len(anomalies) == 0  # Only 2 unique buyers


def test_evidence_contains_buyer_list(db_conn):
    """Evidence includes sorted buyer list (capped at 10)."""
    checker = CoordinatedBuyingChecker(db_conn)
    now = int(time.time())
    for i in range(4):
        _seed_event(db_conn, f"e{i}", f"0xbuyer{i:02d}", "sys-700", timestamp=now)

    anomalies = checker.check()
    assert len(anomalies) == 1
    buyers = anomalies[0].evidence["buyers"]
    assert len(buyers) == 4
    assert buyers == sorted(buyers)  # Sorted


def test_no_events_no_anomalies(db_conn):
    """Empty database produces no anomalies."""
    checker = CoordinatedBuyingChecker(db_conn)
    assert checker.check() == []


def test_events_without_sender_skipped(db_conn):
    """Events with no sender in raw_json are ignored."""
    checker = CoordinatedBuyingChecker(db_conn)
    now = int(time.time())
    # Insert event with no sender
    conn = db_conn
    conn.execute(
        """INSERT INTO chain_events
           (event_id, event_type, object_id, object_type, system_id,
            block_number, transaction_hash, timestamp, raw_json, processed)
           VALUES (?, ?, ?, '', ?, 0, ?, ?, ?, 1)""",
        ("e1", "pkg::ItemDepositedEvent", "obj1", "sys-800", "e1", now, "{}"),
    )
    conn.commit()

    anomalies = checker.check()
    assert len(anomalies) == 0

"""Tests for wallet concentration checker — WC1 rule."""

import json
import time

from backend.detection.wallet_concentration_checker import WalletConcentrationChecker


def _insert_event(conn, event_id, system_id, sender, timestamp=None):
    """Insert a chain_event with raw_json containing sender."""
    ts = timestamp or int(time.time())
    conn.execute(
        "INSERT INTO chain_events (event_id, event_type, object_id, system_id, "
        "transaction_hash, timestamp, raw_json, processed) "
        "VALUES (?, 'test', '', ?, ?, ?, ?, 0)",
        (event_id, system_id, f"tx-{event_id}", ts,
         json.dumps({"sender": sender})),
    )
    conn.commit()


def test_wc1_concentration_above_threshold(db_conn):
    """WC1: Single wallet >50% of 10+ events triggers anomaly."""
    now = int(time.time())
    # 8 events from dominant wallet + 2 from another = 80% concentration
    for i in range(8):
        _insert_event(db_conn, f"dom-{i}", "sys-1", "0xdominant", now)
    for i in range(2):
        _insert_event(db_conn, f"other-{i}", "sys-1", "0xother", now)

    checker = WalletConcentrationChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 1
    assert anomalies[0].anomaly_type == "ASSET_CONCENTRATION"
    assert anomalies[0].evidence["wallet"] == "0xdominant"
    assert anomalies[0].evidence["concentration_ratio"] == 0.8


def test_wc1_below_min_events_no_trigger(db_conn):
    """WC1: System with < 10 events does not trigger."""
    now = int(time.time())
    for i in range(5):
        _insert_event(db_conn, f"few-{i}", "sys-small", "0xonly", now)

    checker = WalletConcentrationChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0


def test_wc1_balanced_no_trigger(db_conn):
    """WC1: Even distribution across wallets does not trigger."""
    now = int(time.time())
    for i in range(12):
        _insert_event(db_conn, f"bal-{i}", "sys-balanced", f"0xwallet{i % 4}", now)

    checker = WalletConcentrationChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0


def test_wc1_bad_json_skipped(db_conn):
    """WC1: Malformed raw_json is skipped without error."""
    now = int(time.time())
    # Insert events with bad JSON
    for i in range(12):
        db_conn.execute(
            "INSERT INTO chain_events (event_id, event_type, object_id, system_id, "
            "transaction_hash, timestamp, raw_json, processed) "
            "VALUES (?, 'test', '', 'sys-bad', ?, ?, ?, 0)",
            (f"bad-{i}", f"tx-bad-{i}", now, "not valid json"),
        )
    db_conn.commit()

    checker = WalletConcentrationChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0


def test_wc1_empty_sender_skipped(db_conn):
    """WC1: Events with empty sender are not counted."""
    now = int(time.time())
    for i in range(12):
        _insert_event(db_conn, f"nosender-{i}", "sys-nosend", "", now)

    checker = WalletConcentrationChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0


def test_wc1_old_events_excluded(db_conn):
    """WC1: Events older than 24h are excluded."""
    old = int(time.time()) - 90000  # 25 hours ago
    for i in range(12):
        _insert_event(db_conn, f"old-{i}", "sys-old", "0xold", old)

    checker = WalletConcentrationChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0


def test_wc1_null_raw_json(db_conn):
    """WC1: NULL raw_json is handled gracefully."""
    now = int(time.time())
    for i in range(12):
        db_conn.execute(
            "INSERT INTO chain_events (event_id, event_type, object_id, system_id, "
            "transaction_hash, timestamp, raw_json, processed) "
            "VALUES (?, 'test', '', 'sys-null', ?, ?, NULL, 0)",
            (f"null-{i}", f"tx-null-{i}", now),
        )
    db_conn.commit()

    checker = WalletConcentrationChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0

"""Tests for economic checker — E1-E4 rules."""

import json
import time

from backend.detection.economic_checker import EconomicChecker


def _insert_object(conn, object_id, state, obj_type="smartassemblies", system_id=""):
    conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, system_id, "
        "last_seen, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (object_id, obj_type, json.dumps(state), system_id, int(time.time()), int(time.time())),
    )
    conn.commit()


def _insert_snapshot(conn, object_id, state, snapshot_time, obj_type="smartassemblies"):
    conn.execute(
        "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
        "VALUES (?, ?, ?, ?, 'world_api')",
        (object_id, obj_type, json.dumps(state), snapshot_time),
    )
    conn.commit()


def test_e3_duplicate_mint(db_conn):
    """E3: Duplicate tx+event_type triggers DUPLICATE_MINT."""
    # Insert events with same tx hash but different log indexes
    for i in range(3):
        db_conn.execute(
            "INSERT INTO chain_events (event_id, event_type, object_id, block_number, "
            "transaction_hash, timestamp, processed) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (f"tx-dup:0x{i}", "0xmint_event", f"obj-{i}", 100, "tx-dup", int(time.time())),
        )
    db_conn.commit()

    checker = EconomicChecker(db_conn)
    anomalies = checker.check()

    dupes = [a for a in anomalies if a.anomaly_type == "DUPLICATE_MINT"]
    assert len(dupes) >= 1


def test_e4_negative_balance(db_conn):
    """E4: Negative fuel triggers NEGATIVE_BALANCE."""
    state = {
        "type": "NetworkNode",
        "state": "online",
        "networkNode": {"fuel": {"amount": -50}},
    }
    _insert_object(db_conn, "obj-neg", state)

    checker = EconomicChecker(db_conn)
    anomalies = checker.check()

    negatives = [a for a in anomalies if a.anomaly_type == "NEGATIVE_BALANCE"]
    assert len(negatives) >= 1
    assert negatives[0].severity == "CRITICAL"
    assert negatives[0].evidence["fuel_amount"] == -50


def test_e4_positive_balance_no_anomaly(db_conn):
    """E4: Positive fuel does not trigger."""
    state = {
        "type": "NetworkNode",
        "state": "online",
        "networkNode": {"fuel": {"amount": 100}},
    }
    _insert_object(db_conn, "obj-ok", state)

    checker = EconomicChecker(db_conn)
    anomalies = checker.check()

    negatives = [a for a in anomalies if a.anomaly_type == "NEGATIVE_BALANCE"]
    assert len(negatives) == 0


def test_e1_supply_discrepancy(db_conn):
    """E1: Fuel decreased without chain events triggers SUPPLY_DISCREPANCY."""
    now = int(time.time())
    obj_id = "node-fuel"
    _insert_object(
        db_conn,
        obj_id,
        {"type": "NetworkNode", "networkNode": {"fuel": {"amount": 80}}},
    )
    # Two snapshots: fuel went from 100 to 80
    _insert_snapshot(
        db_conn,
        obj_id,
        {"networkNode": {"fuel": {"amount": 100}}},
        now - 60,
    )
    _insert_snapshot(
        db_conn,
        obj_id,
        {"networkNode": {"fuel": {"amount": 80}}},
        now,
    )

    checker = EconomicChecker(db_conn)
    anomalies = checker.check()

    supply = [a for a in anomalies if a.anomaly_type == "SUPPLY_DISCREPANCY"]
    assert len(supply) >= 1
    assert supply[0].evidence["delta"] == 20

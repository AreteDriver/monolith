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
    """E3: 4+ duplicate events for same object in same tx triggers DUPLICATE_MINT."""
    # Threshold is >2 (i.e. 3+ events). Insert 4 to trigger.
    for i in range(4):
        db_conn.execute(
            "INSERT INTO chain_events (event_id, event_type, object_id, block_number, "
            "transaction_hash, timestamp, processed) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (
                f"tx-dup:0x{i}",
                "0xpkg::status::StatusChangedEvent",
                "obj-same",
                100,
                "tx-dup",
                int(time.time()),
            ),
        )
    db_conn.commit()

    checker = EconomicChecker(db_conn)
    anomalies = checker.check()

    dupes = [a for a in anomalies if a.anomaly_type == "DUPLICATE_MINT"]
    assert len(dupes) >= 1


def test_e3_batch_inventory_not_flagged(db_conn):
    """E3: Batch inventory events (ItemMintedEvent) are NOT flagged as duplicates."""
    for i in range(5):
        db_conn.execute(
            "INSERT INTO chain_events (event_id, event_type, object_id, block_number, "
            "transaction_hash, timestamp, processed) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (
                f"tx-batch:0x{i}",
                "0xpkg::inventory::ItemMintedEvent",
                "asm-batch",
                100,
                "tx-batch",
                int(time.time()),
            ),
        )
    db_conn.commit()

    checker = EconomicChecker(db_conn)
    anomalies = checker.check()

    dupes = [a for a in anomalies if a.anomaly_type == "DUPLICATE_MINT"]
    assert len(dupes) == 0


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


def test_e1_item_supply_discrepancy(db_conn):
    """E1: Item ledger vs state mismatch triggers SUPPLY_DISCREPANCY."""
    obj_id = "asm-items"
    _insert_object(db_conn, obj_id, {"inventory": {"type-a": 50}})

    # Ledger says 100 minted, 30 burned = 70 expected, but state says 50
    db_conn.execute(
        "INSERT INTO item_ledger (assembly_id, item_type_id, event_type, quantity, "
        "event_id, transaction_hash, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (obj_id, "type-a", "minted", 100, "evt-1", "tx-1", int(time.time())),
    )
    db_conn.execute(
        "INSERT INTO item_ledger (assembly_id, item_type_id, event_type, quantity, "
        "event_id, transaction_hash, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (obj_id, "type-a", "burned", 30, "evt-2", "tx-2", int(time.time())),
    )
    db_conn.commit()

    checker = EconomicChecker(db_conn)
    anomalies = checker.check()

    supply = [
        a
        for a in anomalies
        if a.anomaly_type == "SUPPLY_DISCREPANCY" and a.evidence.get("item_type_id")
    ]
    assert len(supply) >= 1
    assert supply[0].evidence["expected_balance"] == 70
    assert supply[0].evidence["actual_balance"] == 50


def test_e4_negative_item_balance(db_conn):
    """E4: Negative item inventory triggers NEGATIVE_BALANCE."""
    state = {"inventory": {"type-x": -10}}
    _insert_object(db_conn, "asm-neg-inv", state)

    checker = EconomicChecker(db_conn)
    anomalies = checker.check()

    negatives = [
        a
        for a in anomalies
        if a.anomaly_type == "NEGATIVE_BALANCE" and a.evidence.get("item_type_id")
    ]
    assert len(negatives) >= 1
    assert negatives[0].evidence["balance"] == -10

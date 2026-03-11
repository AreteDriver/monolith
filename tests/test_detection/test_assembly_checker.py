"""Tests for assembly checker — A1, A4, A5 rules."""

import json
import time

from backend.detection.assembly_checker import AssemblyChecker


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


def test_a4_phantom_change(db_conn):
    """A4: Property changed without events triggers PHANTOM_ITEM_CHANGE."""
    now = int(time.time())
    _insert_object(db_conn, "asm-001", {"state": "online", "energyUsage": 50})

    _insert_snapshot(db_conn, "asm-001", {"state": "online", "energyUsage": 50}, now - 60)
    _insert_snapshot(db_conn, "asm-001", {"state": "online", "energyUsage": 100}, now)

    checker = AssemblyChecker(db_conn)
    anomalies = checker.check()

    phantoms = [a for a in anomalies if a.anomaly_type == "PHANTOM_ITEM_CHANGE"]
    assert len(phantoms) >= 1
    assert "energyUsage" in phantoms[0].evidence["changes"]


def test_a4_no_phantom_when_unchanged(db_conn):
    """A4: Identical snapshots do not trigger."""
    now = int(time.time())
    state = {"state": "online", "energyUsage": 50}
    _insert_object(db_conn, "asm-001", state)
    _insert_snapshot(db_conn, "asm-001", state, now - 60)
    _insert_snapshot(db_conn, "asm-001", state, now)

    checker = AssemblyChecker(db_conn)
    anomalies = checker.check()

    phantoms = [a for a in anomalies if a.anomaly_type == "PHANTOM_ITEM_CHANGE"]
    assert len(phantoms) == 0


def test_a5_ownership_change(db_conn):
    """A5: Owner changed without transfer event triggers UNEXPLAINED_OWNERSHIP_CHANGE."""
    now = int(time.time())
    _insert_object(
        db_conn,
        "asm-own",
        {"owner": {"address": "0xabc"}, "solarSystem": {"id": 30012602}},
    )
    _insert_snapshot(
        db_conn,
        "asm-own",
        {"owner": {"address": "0xabc"}, "solarSystem": {"id": 30012602}},
        now - 60,
    )
    _insert_snapshot(
        db_conn,
        "asm-own",
        {"owner": {"address": "0xdef"}, "solarSystem": {"id": 30012602}},
        now,
    )

    checker = AssemblyChecker(db_conn)
    anomalies = checker.check()

    ownership = [a for a in anomalies if a.anomaly_type == "UNEXPLAINED_OWNERSHIP_CHANGE"]
    assert len(ownership) >= 1
    assert ownership[0].severity == "CRITICAL"
    assert ownership[0].evidence["old_owner"] == "0xabc"
    assert ownership[0].evidence["new_owner"] == "0xdef"


def test_a5_no_flag_for_null_address(db_conn):
    """A5: Change from null address is not flagged (initial ownership)."""
    now = int(time.time())
    null_addr = "0x" + "0" * 40
    _insert_object(db_conn, "asm-null", {"owner": {"address": null_addr}})
    _insert_snapshot(db_conn, "asm-null", {"owner": {"address": null_addr}}, now - 60)
    _insert_snapshot(db_conn, "asm-null", {"owner": {"address": "0xabc"}}, now)

    checker = AssemblyChecker(db_conn)
    anomalies = checker.check()

    ownership = [a for a in anomalies if a.anomaly_type == "UNEXPLAINED_OWNERSHIP_CHANGE"]
    assert len(ownership) == 0

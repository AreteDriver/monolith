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


def _insert_chain_event(conn, event_id, event_type, object_id, tx_hash, ts, raw_json=None):
    conn.execute(
        "INSERT INTO chain_events (event_id, event_type, object_id, transaction_hash, "
        "timestamp, raw_json, processed) VALUES (?, ?, ?, ?, ?, ?, 1)",
        (event_id, event_type, object_id, tx_hash, ts, json.dumps(raw_json or {})),
    )
    conn.commit()


def _insert_transition(conn, object_id, from_state, to_state, ts):
    conn.execute(
        "INSERT INTO state_transitions (object_id, from_state, to_state, timestamp) "
        "VALUES (?, ?, ?, ?)",
        (object_id, json.dumps(from_state), json.dumps(to_state), ts),
    )
    conn.commit()


def test_a1_state_mismatch(db_conn):
    """A1: API state diverges from last recorded transition state."""
    now = int(time.time())
    _insert_object(db_conn, "asm-a1", {"state": "online"}, system_id="sys-1")
    _insert_transition(db_conn, "asm-a1", {"state": "offline"}, {"state": "online"}, now - 120)
    _insert_snapshot(db_conn, "asm-a1", {"state": "offline"}, now)

    checker = AssemblyChecker(db_conn)
    anomalies = checker.check()

    mismatches = [a for a in anomalies if a.anomaly_type == "CONTRACT_STATE_MISMATCH"]
    assert len(mismatches) >= 1
    assert mismatches[0].evidence["api_state"] == "offline"
    assert mismatches[0].evidence["transition_state"] == "online"


def test_a1_no_mismatch_when_states_match(db_conn):
    """A1: Matching states produce no anomaly."""
    now = int(time.time())
    _insert_object(db_conn, "asm-match", {"state": "online"})
    _insert_transition(db_conn, "asm-match", {"state": "offline"}, {"state": "online"}, now - 120)
    _insert_snapshot(db_conn, "asm-match", {"state": "online"}, now)

    checker = AssemblyChecker(db_conn)
    anomalies = checker.check()
    mismatches = [a for a in anomalies if a.anomaly_type == "CONTRACT_STATE_MISMATCH"]
    assert len(mismatches) == 0


def test_a2_free_gate_jump(db_conn):
    """A2: Jump event without fuel event triggers FREE_GATE_JUMP."""
    now = int(time.time())
    _insert_chain_event(db_conn, "jump-1", "0xpkg::gate::JumpEvent", "gate-1", "tx-a2", now)

    checker = AssemblyChecker(db_conn)
    anomalies = checker.check()

    free_jumps = [a for a in anomalies if a.anomaly_type == "FREE_GATE_JUMP"]
    assert len(free_jumps) == 1
    assert free_jumps[0].evidence["transaction_hash"] == "tx-a2"


def test_a2_no_free_jump_when_fuel_exists(db_conn):
    """A2: Jump with fuel event is normal — no anomaly."""
    now = int(time.time())
    _insert_chain_event(db_conn, "jump-2", "0xpkg::gate::JumpEvent", "gate-2", "tx-a2b", now)
    _insert_chain_event(db_conn, "fuel-2", "0xpkg::fuel::FuelEvent", "gate-2", "tx-a2b", now)

    checker = AssemblyChecker(db_conn)
    anomalies = checker.check()

    free_jumps = [a for a in anomalies if a.anomaly_type == "FREE_GATE_JUMP"]
    assert len(free_jumps) == 0


def test_a3_failed_transport(db_conn):
    """A3: Fuel event on a gate without jump triggers FAILED_GATE_TRANSPORT."""
    now = int(time.time())
    _insert_object(db_conn, "gate-3", {}, obj_type="gate")
    _insert_chain_event(
        db_conn,
        "fuel-3",
        "0xpkg::fuel::FuelEvent",
        "gate-3",
        "tx-a3",
        now,
        raw_json={"parsedJson": {"action": {"variant": "TRANSPORT_BURN"}}},
    )

    checker = AssemblyChecker(db_conn)
    anomalies = checker.check()

    failed = [a for a in anomalies if a.anomaly_type == "FAILED_GATE_TRANSPORT"]
    assert len(failed) == 1


def test_a3_passive_burn_ignored(db_conn):
    """A3: BURNING_UPDATED fuel events are passive ticks — not flagged."""
    now = int(time.time())
    _insert_object(db_conn, "gate-4", {}, obj_type="gate")
    _insert_chain_event(
        db_conn,
        "fuel-4",
        "0xpkg::fuel::FuelEvent",
        "gate-4",
        "tx-a3b",
        now,
        raw_json={"parsedJson": {"action": {"variant": "BURNING_UPDATED"}}},
    )

    checker = AssemblyChecker(db_conn)
    anomalies = checker.check()

    failed = [a for a in anomalies if a.anomaly_type == "FAILED_GATE_TRANSPORT"]
    assert len(failed) == 0


def test_extract_owner_dict(db_conn):
    """Static method: extracts address from owner dict."""
    assert AssemblyChecker._extract_owner({"owner": {"address": "0xabc"}}) == "0xabc"


def test_extract_owner_string(db_conn):
    """Static method: handles string owner."""
    assert AssemblyChecker._extract_owner({"owner": "0xdef"}) == "0xdef"


def test_extract_owner_empty(db_conn):
    """Static method: returns empty for missing owner."""
    assert AssemblyChecker._extract_owner({}) == ""


def test_find_significant_changes_fuel(db_conn):
    """Static method: detects nested fuel amount changes."""
    old = {"state": "online", "networkNode": {"fuel": {"amount": 100}}}
    new = {"state": "online", "networkNode": {"fuel": {"amount": 50}}}
    changes = AssemblyChecker._find_significant_changes(old, new)
    assert "fuel.amount" in changes
    assert changes["fuel.amount"]["old"] == 100
    assert changes["fuel.amount"]["new"] == 50


def test_find_significant_changes_none(db_conn):
    """Static method: identical states produce no changes."""
    state = {"state": "online", "networkNode": {"fuel": {"amount": 100}}}
    changes = AssemblyChecker._find_significant_changes(state, state)
    assert changes == {}

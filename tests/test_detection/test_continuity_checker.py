"""Tests for continuity checker — C1-C4 rules."""

import json
import time

from backend.detection.continuity_checker import ContinuityChecker


def _insert_chain_event(conn, event_id, object_id="obj-001", event_type="test", ts=None):
    """Helper to insert a chain event."""
    conn.execute(
        "INSERT INTO chain_events (event_id, event_type, object_id, block_number, "
        "transaction_hash, timestamp, processed) VALUES (?, ?, ?, ?, ?, ?, 0)",
        (event_id, event_type, object_id, 100, f"tx-{event_id}", ts or int(time.time())),
    )
    conn.commit()


def _insert_object(conn, object_id, obj_type="smartassemblies", state=None, **kwargs):
    """Helper to insert a tracked object."""
    state = state or {}
    conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, system_id, "
        "last_seen, created_at, destroyed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            object_id,
            obj_type,
            json.dumps(state),
            kwargs.get("system_id", ""),
            kwargs.get("last_seen", int(time.time())),
            kwargs.get("created_at", int(time.time())),
            kwargs.get("destroyed_at"),
        ),
    )
    conn.commit()


def _insert_snapshot(conn, object_id, state_data, snapshot_time=None, obj_type="smartassemblies"):
    """Helper to insert a world state snapshot."""
    conn.execute(
        "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
        "VALUES (?, ?, ?, ?, 'world_api')",
        (object_id, obj_type, json.dumps(state_data), snapshot_time or int(time.time())),
    )
    conn.commit()


def test_c1_orphan_event(db_conn):
    """C1: Event for unknown object triggers ORPHAN_OBJECT."""
    _insert_chain_event(db_conn, "evt-001", object_id="unknown-obj")
    checker = ContinuityChecker(db_conn)
    anomalies = checker.check()

    orphans = [a for a in anomalies if a.anomaly_type == "ORPHAN_OBJECT"]
    assert len(orphans) >= 1
    assert orphans[0].rule_id == "C1"
    assert orphans[0].object_id == "unknown-obj"


def test_c1_no_orphan_when_object_exists(db_conn):
    """C1: No orphan if object is tracked."""
    _insert_object(db_conn, "obj-001")
    _insert_chain_event(db_conn, "evt-001", object_id="obj-001")
    checker = ContinuityChecker(db_conn)
    anomalies = checker.check()

    orphans = [a for a in anomalies if a.anomaly_type == "ORPHAN_OBJECT"]
    assert len(orphans) == 0


def test_c2_resurrection(db_conn):
    """C2: Post-destruction activity triggers RESURRECTION."""
    now = int(time.time())
    _insert_object(db_conn, "obj-001", destroyed_at=now - 100, last_seen=now - 100)
    _insert_chain_event(db_conn, "evt-001", object_id="obj-001", ts=now)
    checker = ContinuityChecker(db_conn)
    anomalies = checker.check()

    resurrected = [a for a in anomalies if a.anomaly_type == "RESURRECTION"]
    assert len(resurrected) >= 1
    assert resurrected[0].severity == "CRITICAL"


def test_c3_state_gap(db_conn):
    """C3: Invalid state transition triggers STATE_GAP."""
    now = int(time.time())
    _insert_object(db_conn, "obj-001")
    # Snapshot 1: online
    _insert_snapshot(
        db_conn, "obj-001", {"state": "online", "solarSystem": {"id": 30012602}}, now - 60
    )
    # Snapshot 2: unanchored (invalid from online — must go through offline first... actually
    # unanchored IS valid from online per our transition map)
    # Let's use a truly invalid transition: online -> destroyed (not in valid transitions)
    _insert_snapshot(db_conn, "obj-001", {"state": "destroyed"}, now)

    checker = ContinuityChecker(db_conn)
    anomalies = checker.check()

    gaps = [a for a in anomalies if a.anomaly_type == "STATE_GAP"]
    # "destroyed" is not in VALID_TRANSITIONS for "online", so this should flag
    assert len(gaps) >= 1
    assert gaps[0].evidence["from_state"] == "online"
    assert gaps[0].evidence["to_state"] == "destroyed"


def test_c3_valid_transition_no_anomaly(db_conn):
    """C3: Valid state transition does not trigger."""
    now = int(time.time())
    _insert_object(db_conn, "obj-001")
    _insert_snapshot(db_conn, "obj-001", {"state": "online"}, now - 60)
    _insert_snapshot(db_conn, "obj-001", {"state": "offline"}, now)

    checker = ContinuityChecker(db_conn)
    anomalies = checker.check()

    gaps = [a for a in anomalies if a.anomaly_type == "STATE_GAP"]
    assert len(gaps) == 0


def test_c1_deduplicates_same_object(db_conn):
    """C1: Multiple events for same unknown object produce one anomaly."""
    _insert_chain_event(db_conn, "evt-001", object_id="unknown-obj")
    _insert_chain_event(db_conn, "evt-002", object_id="unknown-obj")
    checker = ContinuityChecker(db_conn)
    anomalies = checker.check()
    orphans = [a for a in anomalies if a.anomaly_type == "ORPHAN_OBJECT"]
    assert len(orphans) == 1


def test_c2_no_resurrection_if_alive(db_conn):
    """C2: No resurrection for non-destroyed objects."""
    now = int(time.time())
    _insert_object(db_conn, "obj-001", last_seen=now)
    _insert_chain_event(db_conn, "evt-001", object_id="obj-001", ts=now)
    checker = ContinuityChecker(db_conn)
    anomalies = checker.check()
    resurrected = [a for a in anomalies if a.anomaly_type == "RESURRECTION"]
    assert len(resurrected) == 0


def test_c3_same_state_no_gap(db_conn):
    """C3: Same state in both snapshots — no gap."""
    now = int(time.time())
    _insert_object(db_conn, "obj-001")
    _insert_snapshot(db_conn, "obj-001", {"state": "online"}, now - 60)
    _insert_snapshot(db_conn, "obj-001", {"state": "online"}, now)
    checker = ContinuityChecker(db_conn)
    anomalies = checker.check()
    gaps = [a for a in anomalies if a.anomaly_type == "STATE_GAP"]
    assert len(gaps) == 0


def test_c4_stuck_object(db_conn):
    """C4: Object in transitional state with no recent activity triggers STUCK_OBJECT."""
    now = int(time.time())
    # Object in "anchored" state, last seen over 2 hours ago
    _insert_object(
        db_conn,
        "obj-stuck",
        state={"state": "anchored"},
        last_seen=now - 7200 - 60,
        created_at=now - 86400,
    )
    checker = ContinuityChecker(db_conn)
    anomalies = checker.check()
    stuck = [a for a in anomalies if a.anomaly_type == "STUCK_OBJECT"]
    assert len(stuck) >= 1
    assert stuck[0].rule_id == "C4"


def test_c4_not_stuck_if_online(db_conn):
    """C4: Object in 'online' state is NOT stuck (only transitional states)."""
    now = int(time.time())
    _insert_object(
        db_conn,
        "obj-ok",
        state={"state": "online"},
        last_seen=now - 7200 - 60,
        created_at=now - 86400,
    )
    checker = ContinuityChecker(db_conn)
    anomalies = checker.check()
    stuck = [a for a in anomalies if a.anomaly_type == "STUCK_OBJECT"]
    assert len(stuck) == 0

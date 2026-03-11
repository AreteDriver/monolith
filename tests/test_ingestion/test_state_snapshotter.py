"""Tests for state snapshotter — delta detection between snapshots."""

import json

from backend.ingestion.state_snapshotter import StateSnapshotter


def test_compute_delta_identical():
    """Identical states return None."""
    snapper = StateSnapshotter.__new__(StateSnapshotter)
    result = snapper.compute_delta(
        {"state_data": '{"fuel": 100}'},
        {"state_data": '{"fuel": 100}'},
    )
    assert result is None


def test_compute_delta_changed():
    """Changed states return the delta."""
    snapper = StateSnapshotter.__new__(StateSnapshotter)
    result = snapper.compute_delta(
        {"state_data": '{"fuel": 100, "name": "Gate A"}'},
        {"state_data": '{"fuel": 80, "name": "Gate A"}'},
    )
    assert result is not None
    assert "fuel" in result
    assert result["fuel"]["old"] == 100
    assert result["fuel"]["new"] == 80


def test_record_transition(db_conn):
    """Transition is recorded to state_transitions table."""
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, last_seen) VALUES (?, ?, ?)",
        ("obj-001", "gate", 1000),
    )
    db_conn.commit()
    snapper = StateSnapshotter(db_conn)
    snapper.record_transition(
        object_id="obj-001",
        from_state="active",
        to_state="destroyed",
        timestamp=1000,
        event_id="evt-001",
    )
    db_conn.commit()

    row = db_conn.execute(
        "SELECT * FROM state_transitions WHERE object_id = ?", ("obj-001",)
    ).fetchone()
    assert row is not None
    assert row["from_state"] == "active"
    assert row["to_state"] == "destroyed"


def test_process_all_objects_no_data(db_conn):
    """No objects returns 0 deltas."""
    snapper = StateSnapshotter(db_conn)
    assert snapper.process_all_objects() == 0


def test_process_all_objects_with_delta(db_conn):
    """Delta detected between two snapshots."""
    # Insert an object
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, last_seen) VALUES (?, ?, ?)",
        ("obj-001", "gate", 1000),
    )
    # Insert two snapshots with different state
    db_conn.execute(
        "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
        "VALUES (?, ?, ?, ?, ?)",
        ("obj-001", "gate", json.dumps({"fuel": 100}), 1000, "world_api"),
    )
    db_conn.execute(
        "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
        "VALUES (?, ?, ?, ?, ?)",
        ("obj-001", "gate", json.dumps({"fuel": 80}), 2000, "world_api"),
    )
    db_conn.commit()

    snapper = StateSnapshotter(db_conn)
    result = snapper.process_all_objects()
    assert result == 1

    transitions = db_conn.execute(
        "SELECT * FROM state_transitions WHERE object_id = ?", ("obj-001",)
    ).fetchall()
    assert len(transitions) == 1

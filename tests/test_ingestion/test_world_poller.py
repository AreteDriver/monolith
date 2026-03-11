"""Tests for world poller — snapshot storage and object upsert."""

import json

from backend.ingestion.world_poller import WorldPoller


def test_store_snapshot(db_conn):
    """Snapshot is stored with correct fields."""
    poller = WorldPoller(db_conn, base_url="http://test")
    poller.store_snapshot("obj-001", "smartassemblies", {"fuel": 100})
    db_conn.commit()

    row = db_conn.execute("SELECT * FROM world_states WHERE object_id = ?", ("obj-001",)).fetchone()
    assert row is not None
    assert row["source"] == "world_api"
    data = json.loads(row["state_data"])
    assert data["fuel"] == 100


def test_upsert_object_new(db_conn):
    """New object is inserted."""
    poller = WorldPoller(db_conn, base_url="http://test")
    poller.upsert_object("obj-001", "gate", {"ownerId": "player-1", "solarSystemId": "sys-001"})
    db_conn.commit()

    row = db_conn.execute("SELECT * FROM objects WHERE object_id = ?", ("obj-001",)).fetchone()
    assert row is not None
    assert row["current_owner"] == "player-1"
    assert row["system_id"] == "sys-001"


def test_upsert_object_update(db_conn):
    """Existing object is updated on conflict."""
    poller = WorldPoller(db_conn, base_url="http://test")
    poller.upsert_object("obj-001", "gate", {"ownerId": "player-1"})
    db_conn.commit()

    poller.upsert_object("obj-001", "gate", {"ownerId": "player-2"})
    db_conn.commit()

    row = db_conn.execute("SELECT * FROM objects WHERE object_id = ?", ("obj-001",)).fetchone()
    assert row["current_owner"] == "player-2"


def test_get_snapshots_empty(db_conn):
    """No snapshots returns empty list."""
    poller = WorldPoller(db_conn, base_url="http://test")
    result = poller.get_snapshots("nonexistent")
    assert result == []


def test_get_snapshots_time_filter(db_conn):
    """Snapshots filtered by time window."""
    poller = WorldPoller(db_conn, base_url="http://test")

    # Manually insert snapshots with specific times
    for t in [1000, 2000, 3000]:
        db_conn.execute(
            "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
            "VALUES (?, ?, ?, ?, ?)",
            ("obj-001", "gate", "{}", t, "world_api"),
        )
    db_conn.commit()

    result = poller.get_snapshots("obj-001", start_time=1500, end_time=2500)
    assert len(result) == 1
    assert result[0]["snapshot_time"] == 2000

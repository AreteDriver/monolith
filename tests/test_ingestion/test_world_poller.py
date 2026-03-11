"""Tests for world poller — snapshot storage, object upsert, field extraction."""

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
    """New object is inserted with correct owner/system extraction."""
    poller = WorldPoller(db_conn, base_url="http://test")
    poller.upsert_object(
        "obj-001",
        "smartassemblies",
        {
            "owner": {"address": "0xabc", "name": "Player1"},
            "solarSystem": {"id": 30012602, "name": "I6L-RFG"},
        },
    )
    db_conn.commit()

    row = db_conn.execute("SELECT * FROM objects WHERE object_id = ?", ("obj-001",)).fetchone()
    assert row is not None
    assert row["current_owner"] == "0xabc"
    assert row["system_id"] == "30012602"


def test_upsert_object_update(db_conn):
    """Existing object is updated on conflict."""
    poller = WorldPoller(db_conn, base_url="http://test")
    poller.upsert_object("obj-001", "gate", {"owner": {"address": "0xabc"}})
    db_conn.commit()

    poller.upsert_object("obj-001", "gate", {"owner": {"address": "0xdef"}})
    db_conn.commit()

    row = db_conn.execute("SELECT * FROM objects WHERE object_id = ?", ("obj-001",)).fetchone()
    assert row["current_owner"] == "0xdef"


def test_extract_owner_nested(db_conn):
    """Owner extraction handles nested owner dict."""
    poller = WorldPoller(db_conn, base_url="http://test")
    assert poller._extract_owner({"owner": {"address": "0xabc", "name": "P1"}}) == "0xabc"


def test_extract_owner_flat(db_conn):
    """Owner extraction handles flat ownerId."""
    poller = WorldPoller(db_conn, base_url="http://test")
    assert poller._extract_owner({"ownerId": "player-1"}) == "player-1"


def test_extract_system_id_nested(db_conn):
    """System ID extraction handles nested solarSystem dict."""
    poller = WorldPoller(db_conn, base_url="http://test")
    assert poller._extract_system_id({"solarSystem": {"id": 30012602}}) == "30012602"


def test_extract_system_id_flat(db_conn):
    """System ID extraction handles flat solarSystemId."""
    poller = WorldPoller(db_conn, base_url="http://test")
    assert poller._extract_system_id({"solarSystemId": "sys-001"}) == "sys-001"


def test_extract_id_from_item(db_conn):
    """ID extraction handles various field names."""
    poller = WorldPoller(db_conn, base_url="http://test")
    assert poller._extract_id({"id": "123"}) == "123"
    assert poller._extract_id({"address": "0xabc"}) == "0xabc"
    assert poller._extract_id({"smartAssemblyId": "sa-1"}) == "sa-1"


def test_get_snapshots_empty(db_conn):
    """No snapshots returns empty list."""
    poller = WorldPoller(db_conn, base_url="http://test")
    result = poller.get_snapshots("nonexistent")
    assert result == []


def test_get_snapshots_time_filter(db_conn):
    """Snapshots filtered by time window."""
    poller = WorldPoller(db_conn, base_url="http://test")

    for t in [1000, 2000, 3000]:
        db_conn.execute(
            "INSERT INTO world_states "
            "(object_id, object_type, state_data, snapshot_time, source) "
            "VALUES (?, ?, ?, ?, ?)",
            ("obj-001", "gate", "{}", t, "world_api"),
        )
    db_conn.commit()

    result = poller.get_snapshots("obj-001", start_time=1500, end_time=2500)
    assert len(result) == 1
    assert result[0]["snapshot_time"] == 2000

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


def test_resolve_name(db_conn):
    """Name resolution returns stored names or empty string."""
    poller = WorldPoller(db_conn, base_url="http://test")
    # No data yet
    assert poller.resolve_name("solarsystems", "123") == ""
    # Store reference data
    db_conn.execute(
        "INSERT INTO reference_data (data_type, data_id, name, data_json, updated_at) "
        "VALUES ('solarsystems', '123', 'Jita', '{}', 0)"
    )
    db_conn.commit()
    assert poller.resolve_system_name("123") == "Jita"
    assert poller.resolve_type_name("456") == ""


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


def test_flush_polled_data(db_conn):
    """flush_polled_data clears orbital_zones, feral_ai_events, reference_data, tribe_cache."""
    poller = WorldPoller(db_conn, base_url="http://test")

    # Seed data into each table
    db_conn.execute(
        "INSERT INTO reference_data (data_type, data_id, name, data_json, updated_at) "
        "VALUES ('types', '1', 'Ship', '{}', 0)"
    )
    db_conn.execute(
        "INSERT INTO orbital_zones (zone_id, zone_name, system_id, feral_ai_tier, "
        "threat_level, zone_data, discovered_at, last_polled) "
        "VALUES ('z1', 'Zone Alpha', 'sys-1', 1, 'low', '{}', 0, 0)"
    )
    db_conn.commit()

    counts = poller.flush_polled_data()
    assert counts["reference_data"] == 1
    assert counts["orbital_zones"] == 1

    # Verify tables are empty
    assert db_conn.execute("SELECT COUNT(*) FROM reference_data").fetchone()[0] == 0
    assert db_conn.execute("SELECT COUNT(*) FROM orbital_zones").fetchone()[0] == 0


def test_resolve_ship_name(db_conn):
    """resolve_ship_name looks up ships in reference data."""
    poller = WorldPoller(db_conn, base_url="http://test")
    db_conn.execute(
        "INSERT INTO reference_data (data_type, data_id, name, data_json, updated_at) "
        "VALUES ('ships', '42', 'Frigate', '{}', 0)"
    )
    db_conn.commit()
    assert poller.resolve_ship_name("42") == "Frigate"
    assert poller.resolve_ship_name("999") == ""


def test_get_ship_stats(db_conn):
    """get_ship_stats returns parsed JSON for known ships."""
    poller = WorldPoller(db_conn, base_url="http://test")
    stats = {"id": "42", "name": "Frigate", "speed": 300}
    db_conn.execute(
        "INSERT INTO reference_data (data_type, data_id, name, data_json, updated_at) "
        "VALUES ('ships', '42', 'Frigate', ?, 0)",
        (json.dumps(stats),),
    )
    db_conn.commit()
    result = poller.get_ship_stats("42")
    assert result["speed"] == 300
    assert poller.get_ship_stats("999") is None


def test_get_ship_stats_invalid_json(db_conn):
    """get_ship_stats returns None for invalid JSON."""
    poller = WorldPoller(db_conn, base_url="http://test")
    db_conn.execute(
        "INSERT INTO reference_data (data_type, data_id, name, data_json, updated_at) "
        "VALUES ('ships', '99', 'Bad', 'not-json', 0)"
    )
    db_conn.commit()
    assert poller.get_ship_stats("99") is None


def test_resolve_constellation_name(db_conn):
    """resolve_constellation_name looks up constellations."""
    poller = WorldPoller(db_conn, base_url="http://test")
    db_conn.execute(
        "INSERT INTO reference_data (data_type, data_id, name, data_json, updated_at) "
        "VALUES ('constellations', 'c1', 'Alpha Cluster', '{}', 0)"
    )
    db_conn.commit()
    assert poller.resolve_constellation_name("c1") == "Alpha Cluster"


def test_store_tribe_new(db_conn):
    """store_tribe inserts a new tribe into tribe_cache."""
    poller = WorldPoller(db_conn, base_url="http://test")
    poller.store_tribe({"id": "tribe-1", "name": "Raiders", "nameShort": "RDR", "memberCount": 42, "taxRate": 0.1})
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM tribe_cache WHERE tribe_id = 'tribe-1'").fetchone()
    assert row is not None
    assert row["name"] == "Raiders"
    assert row["member_count"] == 42


def test_store_tribe_update(db_conn):
    """store_tribe updates existing tribe and tracks changes."""
    poller = WorldPoller(db_conn, base_url="http://test")
    poller.store_tribe({"id": "tribe-2", "name": "Old", "nameShort": "OLD", "memberCount": 10, "taxRate": 0.0})
    db_conn.commit()
    poller.store_tribe({"id": "tribe-2", "name": "New", "nameShort": "NEW", "memberCount": 20, "taxRate": 0.5})
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM tribe_cache WHERE tribe_id = 'tribe-2'").fetchone()
    assert row["name"] == "New"
    assert row["member_count"] == 20


def test_resolve_tribe(db_conn):
    """resolve_tribe returns tribe info with staleness."""
    poller = WorldPoller(db_conn, base_url="http://test")
    poller.store_tribe({"id": "tribe-3", "name": "Test", "nameShort": "TST", "memberCount": 5, "taxRate": 0.0})
    db_conn.commit()
    result = poller.resolve_tribe("tribe-3")
    assert result is not None
    assert result["name"] == "Test"
    assert result["is_stale"] is False
    assert poller.resolve_tribe("nonexistent") is None


def test_get_stale_tribes(db_conn):
    """get_stale_tribes returns tribes marked as stale."""
    poller = WorldPoller(db_conn, base_url="http://test")
    poller.store_tribe({"id": "tribe-4", "name": "Stale", "nameShort": "STL", "memberCount": 1, "taxRate": 0.0})
    db_conn.execute("UPDATE tribe_cache SET is_stale = 1 WHERE tribe_id = 'tribe-4'")
    db_conn.commit()
    stale = poller.get_stale_tribes()
    assert len(stale) == 1
    assert stale[0]["tribe_id"] == "tribe-4"


def test_check_health_no_base_url(db_conn):
    """check_health returns unavailable when no base_url."""
    import asyncio
    poller = WorldPoller(db_conn, base_url="")
    result = asyncio.get_event_loop().run_until_complete(
        poller.check_health(None)
    )
    assert result["available"] is False


def test_no_base_url_poll_static(db_conn):
    """poll_static_data returns empty when no base_url."""
    import asyncio
    poller = WorldPoller(db_conn, base_url="")
    result = asyncio.get_event_loop().run_until_complete(
        poller.poll_static_data(None)
    )
    assert result == {}


def test_no_base_url_poll_tribes(db_conn):
    """poll_tribes returns 0 when no base_url."""
    import asyncio
    poller = WorldPoller(db_conn, base_url="")
    result = asyncio.get_event_loop().run_until_complete(
        poller.poll_tribes(None)
    )
    assert result == 0


def test_no_base_url_poll_orbital_zones(db_conn):
    """poll_orbital_zones returns 0 when no base_url."""
    import asyncio
    poller = WorldPoller(db_conn, base_url="")
    result = asyncio.get_event_loop().run_until_complete(
        poller.poll_orbital_zones(None)
    )
    assert result == 0

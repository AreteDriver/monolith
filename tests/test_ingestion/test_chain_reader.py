"""Tests for chain reader — Sui event storage, deduplication, cursor persistence."""

from backend.ingestion.chain_reader import ChainReader

PACKAGE_ID = "0xpkg123"


def _make_event(
    tx_digest: str = "ABC123",
    event_seq: str = "0",
    module: str = "killmail",
    event_name: str = "KillmailCreatedEvent",
    parsed_json: dict | None = None,
    timestamp_ms: str = "1710000000000",
) -> dict:
    """Create a minimal Sui event for testing."""
    return {
        "id": {"txDigest": tx_digest, "eventSeq": event_seq},
        "packageId": PACKAGE_ID,
        "transactionModule": module,
        "sender": "0xsender",
        "type": f"{PACKAGE_ID}::{module}::{event_name}",
        "parsedJson": parsed_json or {"victim_id": "0xvictim"},
        "timestampMs": timestamp_ms,
    }


def test_store_event_new(db_conn):
    """New event is stored successfully."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    event = _make_event()
    result = reader.store_event(event)
    assert result is True

    row = db_conn.execute("SELECT * FROM chain_events WHERE event_id = ?", ("ABC123:0",)).fetchone()
    assert row is not None
    assert row["transaction_hash"] == "ABC123"


def test_store_event_duplicate(db_conn):
    """Duplicate event returns False, no crash."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    event = _make_event()
    assert reader.store_event(event) is True
    assert reader.store_event(event) is False


def test_store_event_extracts_event_type(db_conn):
    """Event type is the full Sui type string."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    reader.store_event(_make_event())

    row = db_conn.execute("SELECT event_type FROM chain_events").fetchone()
    assert row["event_type"] == f"{PACKAGE_ID}::killmail::KillmailCreatedEvent"


def test_store_event_extracts_object_id(db_conn):
    """Object ID is extracted from parsedJson based on module."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    reader.store_event(_make_event(parsed_json={"victim_id": "0xvictim123"}))

    row = db_conn.execute("SELECT object_id FROM chain_events").fetchone()
    assert row["object_id"] == "0xvictim123"


def test_store_event_extracts_assembly_id(db_conn):
    """Assembly events use assembly_id field."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    reader.store_event(
        _make_event(
            module="status",
            event_name="StatusChangedEvent",
            parsed_json={"assembly_id": "0xassembly1", "status": "online"},
        )
    )

    row = db_conn.execute("SELECT object_id FROM chain_events").fetchone()
    assert row["object_id"] == "0xassembly1"


def test_store_event_extracts_system_id(db_conn):
    """System ID extracted from parsedJson when present."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    reader.store_event(_make_event(parsed_json={"victim_id": "0xv", "solar_system_id": "30012602"}))

    row = db_conn.execute("SELECT system_id FROM chain_events").fetchone()
    assert row["system_id"] == "30012602"


def test_store_event_timestamp_conversion(db_conn):
    """Timestamp is converted from milliseconds to seconds."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    reader.store_event(_make_event(timestamp_ms="1710000000000"))

    row = db_conn.execute("SELECT timestamp FROM chain_events").fetchone()
    assert row["timestamp"] == 1710000000


def test_get_last_block_empty(db_conn):
    """Last block is 0 on empty database."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    assert reader.get_last_block() == 0


def test_get_unprocessed_count(db_conn):
    """Unprocessed count tracks correctly."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    assert reader.get_unprocessed_count() == 0

    reader.store_event(_make_event())
    assert reader.get_unprocessed_count() == 1


def test_mark_processed(db_conn):
    """Mark processed clears unprocessed flag."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    reader.store_event(_make_event())
    reader.mark_processed(["ABC123:0"])
    assert reader.get_unprocessed_count() == 0


def test_multiple_events_different_sequences(db_conn):
    """Multiple events from same tx with different event sequences are stored."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    assert reader.store_event(_make_event(event_seq="0")) is True
    assert reader.store_event(_make_event(event_seq="1")) is True
    assert reader.get_unprocessed_count() == 2


def test_cursor_persistence(db_conn):
    """Cursors are saved and loaded correctly."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)

    # No cursor initially
    assert reader._load_cursor("test_event") is None

    # Save and reload
    cursor = {"txDigest": "XYZ789", "eventSeq": "3"}
    reader._save_cursor("test_event", cursor)
    loaded = reader._load_cursor("test_event")
    assert loaded == cursor


def test_cursor_upsert(db_conn):
    """Cursor upsert overwrites previous value."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)

    reader._save_cursor("test_event", {"txDigest": "A", "eventSeq": "0"})
    reader._save_cursor("test_event", {"txDigest": "B", "eventSeq": "5"})

    loaded = reader._load_cursor("test_event")
    assert loaded["txDigest"] == "B"
    assert loaded["eventSeq"] == "5"


def test_extract_object_id_fallback(db_conn):
    """Object ID extraction falls back to first field containing 'id'."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    event = {
        "transactionModule": "unknown_module",
        "parsedJson": {"some_entity_id": "0xfallback"},
    }
    assert reader._extract_object_id(event) == "0xfallback"


def test_extract_object_id_empty(db_conn):
    """Object ID extraction returns empty string when no ID found."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    event = {
        "transactionModule": "unknown_module",
        "parsedJson": {"name": "test", "value": 42},
    }
    assert reader._extract_object_id(event) == ""


def test_event_types_resolved(db_conn):
    """Event type strings have package ID substituted."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id="0xABC")
    assert "0xABC::killmail::KillmailCreatedEvent" in reader.events
    assert "0xABC::gate::JumpEvent" in reader.events
    assert "{pkg}" not in str(reader.events)

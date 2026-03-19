"""Tests for chain reader — Sui event storage, deduplication, cursor persistence."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

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


def test_clear_cursor(db_conn):
    """_clear_cursor removes stored cursor."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    reader._save_cursor("test_event", {"txDigest": "A", "eventSeq": "0"})
    assert reader._load_cursor("test_event") is not None

    reader._clear_cursor("test_event")
    assert reader._load_cursor("test_event") is None


def test_enrich_system_ids(db_conn):
    """_enrich_system_ids backfills objects.system_id from location events."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)

    # Create object without system_id
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, last_seen, created_at) "
        "VALUES ('obj-1', 'smartassemblies', 1710000000, 1710000000)"
    )
    # Create location event with system_id
    db_conn.execute(
        "INSERT INTO chain_events (event_id, event_type, object_id, object_type, "
        "system_id, transaction_hash, timestamp, processed) "
        "VALUES ('loc:0', ?, 'obj-1', 'location', 'sys-42', 'tx-loc', 1710000000, 0)",
        (f"{PACKAGE_ID}::location::LocationRevealedEvent",),
    )
    db_conn.commit()

    reader._enrich_system_ids()

    obj = db_conn.execute("SELECT system_id FROM objects WHERE object_id = 'obj-1'").fetchone()
    assert obj["system_id"] == "sys-42"


def test_mark_processed_empty_list(db_conn):
    """mark_processed with empty list is a no-op."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    reader.mark_processed([])  # Should not crash


@pytest.mark.asyncio
async def test_query_events_success(db_conn):
    """query_events returns parsed events from RPC response."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "result": {
            "data": [_make_event()],
            "nextCursor": {"txDigest": "NEXT", "eventSeq": "0"},
            "hasNextPage": False,
        }
    }

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp

    events, cursor, has_next = await reader.query_events(client, "test_type")
    assert len(events) == 1
    assert cursor == {"txDigest": "NEXT", "eventSeq": "0"}
    assert has_next is False


@pytest.mark.asyncio
async def test_query_events_rpc_error(db_conn):
    """query_events handles RPC error gracefully."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "error": {"code": -32000, "message": "Internal error"}
    }

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp

    events, cursor, has_next = await reader.query_events(client, "test_type")
    assert events == []
    assert cursor is None
    assert has_next is False


@pytest.mark.asyncio
async def test_query_events_stale_cursor(db_conn):
    """query_events raises _StaleCursorError for pruned transactions."""
    from backend.ingestion.chain_reader import _StaleCursorError

    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "error": {"message": "Could not find the referenced transaction"}
    }

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp

    with pytest.raises(_StaleCursorError):
        await reader.query_events(client, "test_type")


@pytest.mark.asyncio
async def test_poll_no_package_id(db_conn):
    """poll() with no package_id returns 0."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id="")
    client = AsyncMock(spec=httpx.AsyncClient)
    assert await reader.poll(client) == 0


@pytest.mark.asyncio
async def test_poll_stores_events(db_conn):
    """poll() fetches and stores events from RPC."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "result": {
            "data": [_make_event(tx_digest="POLL1")],
            "nextCursor": None,
            "hasNextPage": False,
        }
    }

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp

    total = await reader.poll(client)
    # Each event type gets polled — first one stores, rest are empty
    assert total >= 1
    assert reader.get_unprocessed_count() >= 1


@pytest.mark.asyncio
async def test_get_chain_info_success(db_conn):
    """get_chain_info returns chain status."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": "12345"}

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp

    info = await reader.get_chain_info(client)
    assert info["connected"] is True
    assert info["latest_checkpoint"] == 12345


@pytest.mark.asyncio
async def test_get_chain_info_failure(db_conn):
    """get_chain_info handles RPC failure."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = httpx.ConnectError("Connection refused")

    info = await reader.get_chain_info(client)
    assert info["connected"] is False
    assert "error" in info


def test_extract_system_id_from_location(db_conn):
    """System ID extracted from nested location object."""
    reader = ChainReader(db_conn, rpc_url="http://test", package_id=PACKAGE_ID)
    event = {
        "transactionModule": "location",
        "parsedJson": {"location": {"solarSystemId": "30001234"}},
    }
    assert reader._extract_system_id(event) == "30001234"

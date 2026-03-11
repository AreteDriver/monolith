"""Tests for chain reader — event storage and deduplication."""

from backend.ingestion.chain_reader import ChainReader


def test_store_event_new(db_conn):
    """New event is stored successfully."""
    reader = ChainReader(db_conn, rpc_url="http://test")
    event = {
        "id": {"txDigest": "abc123", "eventSeq": 0},
        "type": "0x1::module::EventType",
        "timestampMs": 1710000000000,
        "parsedJson": {"object_id": "obj-001", "object_type": "gate", "system_id": "sys-001"},
    }
    result = reader.store_event(event)
    assert result is True

    row = db_conn.execute("SELECT * FROM chain_events WHERE event_id = ?", ("abc123:0",)).fetchone()
    assert row is not None
    assert row["event_type"] == "0x1::module::EventType"


def test_store_event_duplicate(db_conn):
    """Duplicate event returns False, no crash."""
    reader = ChainReader(db_conn, rpc_url="http://test")
    event = {
        "id": {"txDigest": "abc123", "eventSeq": 0},
        "type": "test",
        "timestampMs": 1710000000000,
        "parsedJson": {},
    }
    assert reader.store_event(event) is True
    assert reader.store_event(event) is False


def test_get_last_block_empty(db_conn):
    """Last block is 0 on empty database."""
    reader = ChainReader(db_conn, rpc_url="http://test")
    assert reader.get_last_block() == 0


def test_get_unprocessed_count(db_conn):
    """Unprocessed count tracks correctly."""
    reader = ChainReader(db_conn, rpc_url="http://test")
    assert reader.get_unprocessed_count() == 0

    event = {
        "id": {"txDigest": "tx1", "eventSeq": 0},
        "type": "test",
        "timestampMs": 1710000000000,
        "parsedJson": {},
    }
    reader.store_event(event)
    assert reader.get_unprocessed_count() == 1


def test_mark_processed(db_conn):
    """Mark processed clears unprocessed flag."""
    reader = ChainReader(db_conn, rpc_url="http://test")
    event = {
        "id": {"txDigest": "tx1", "eventSeq": 0},
        "type": "test",
        "timestampMs": 1710000000000,
        "parsedJson": {},
    }
    reader.store_event(event)
    reader.mark_processed(["tx1:0"])
    assert reader.get_unprocessed_count() == 0

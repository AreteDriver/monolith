"""Tests for chain reader — log storage and deduplication."""

from backend.ingestion.chain_reader import ChainReader

WORLD_CONTRACT = "0x1dacc0b64b7da0cc6e2b2fe1bd72f58ebd37363c"


def _make_log(tx_hash: str = "0xabc123", log_index: str = "0x0", block: str = "0x100") -> dict:
    """Create a minimal EVM log entry for testing."""
    return {
        "transactionHash": tx_hash,
        "logIndex": log_index,
        "blockNumber": block,
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000abcdef1234567890abcdef1234567890abcdef12",
        ],
        "data": "0x",
        "address": WORLD_CONTRACT,
    }


def test_store_log_new(db_conn):
    """New log is stored successfully."""
    reader = ChainReader(db_conn, rpc_url="http://test", world_contract=WORLD_CONTRACT)
    log = _make_log()
    result = reader.store_log(log)
    assert result is True

    row = db_conn.execute(
        "SELECT * FROM chain_events WHERE event_id = ?", ("0xabc123:0x0",)
    ).fetchone()
    assert row is not None
    assert row["block_number"] == 256  # 0x100


def test_store_log_duplicate(db_conn):
    """Duplicate log returns False, no crash."""
    reader = ChainReader(db_conn, rpc_url="http://test", world_contract=WORLD_CONTRACT)
    log = _make_log()
    assert reader.store_log(log) is True
    assert reader.store_log(log) is False


def test_store_log_extracts_event_type(db_conn):
    """Event type is extracted from first topic."""
    reader = ChainReader(db_conn, rpc_url="http://test", world_contract=WORLD_CONTRACT)
    log = _make_log()
    reader.store_log(log)

    row = db_conn.execute("SELECT event_type FROM chain_events").fetchone()
    assert row["event_type"].startswith("0xddf252")


def test_store_log_extracts_object_id(db_conn):
    """Object ID is extracted from second topic."""
    reader = ChainReader(db_conn, rpc_url="http://test", world_contract=WORLD_CONTRACT)
    log = _make_log()
    reader.store_log(log)

    row = db_conn.execute("SELECT object_id FROM chain_events").fetchone()
    assert "abcdef" in row["object_id"]


def test_get_last_block_empty(db_conn):
    """Last block is 0 on empty database."""
    reader = ChainReader(db_conn, rpc_url="http://test", world_contract=WORLD_CONTRACT)
    assert reader.get_last_block() == 0


def test_get_unprocessed_count(db_conn):
    """Unprocessed count tracks correctly."""
    reader = ChainReader(db_conn, rpc_url="http://test", world_contract=WORLD_CONTRACT)
    assert reader.get_unprocessed_count() == 0

    reader.store_log(_make_log())
    assert reader.get_unprocessed_count() == 1


def test_mark_processed(db_conn):
    """Mark processed clears unprocessed flag."""
    reader = ChainReader(db_conn, rpc_url="http://test", world_contract=WORLD_CONTRACT)
    reader.store_log(_make_log())
    reader.mark_processed(["0xabc123:0x0"])
    assert reader.get_unprocessed_count() == 0


def test_multiple_logs_different_indexes(db_conn):
    """Multiple logs from same tx with different log indexes are stored."""
    reader = ChainReader(db_conn, rpc_url="http://test", world_contract=WORLD_CONTRACT)
    assert reader.store_log(_make_log(log_index="0x0")) is True
    assert reader.store_log(_make_log(log_index="0x1")) is True
    assert reader.get_unprocessed_count() == 2

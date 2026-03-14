"""Tests for event processor — item inventory tracking."""

import json
import time

from backend.ingestion.event_processor import EventProcessor


def _make_event(event_type, object_id, parsed_json, tx_hash="tx-test"):
    """Create a minimal chain_event row dict."""
    return {
        "id": 1,
        "event_id": f"{tx_hash}:0",
        "event_type": event_type,
        "object_id": object_id,
        "object_type": "inventory",
        "system_id": "",
        "transaction_hash": tx_hash,
        "timestamp": int(time.time()),
        "raw_json": json.dumps({"parsedJson": parsed_json}),
    }


def test_item_minted_updates_ledger(db_conn):
    """ItemMintedEvent creates ledger entry and updates inventory state."""
    # Pre-create the object
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("asm-1", "smartassemblies", "{}", int(time.time()), int(time.time())),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::inventory::ItemMintedEvent",
        "asm-1",
        {"quantity": 50, "itemTypeId": "ore-123"},
    )
    processor._dispatch_event(event)

    # Check ledger
    row = db_conn.execute(
        "SELECT * FROM item_ledger WHERE assembly_id = 'asm-1'"
    ).fetchone()
    assert row is not None
    assert row["quantity"] == 50
    assert row["event_type"] == "minted"
    assert row["item_type_id"] == "ore-123"

    # Check state has inventory
    obj = db_conn.execute(
        "SELECT current_state FROM objects WHERE object_id = 'asm-1'"
    ).fetchone()
    state = json.loads(obj["current_state"])
    assert state["inventory"]["ore-123"] == 50


def test_item_burned_decrements_inventory(db_conn):
    """ItemBurnedEvent decreases inventory balance."""
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "asm-2",
            "smartassemblies",
            json.dumps({"inventory": {"ore-1": 100}}),
            int(time.time()),
            int(time.time()),
        ),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::inventory::ItemBurnedEvent",
        "asm-2",
        {"quantity": 30, "itemTypeId": "ore-1"},
        tx_hash="tx-burn",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT current_state FROM objects WHERE object_id = 'asm-2'"
    ).fetchone()
    state = json.loads(obj["current_state"])
    assert state["inventory"]["ore-1"] == 70


def test_item_event_no_quantity_still_updates_last_seen(db_conn):
    """Item event without quantity/type still updates last_seen."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("asm-3", "smartassemblies", "{}", now - 100, now - 100),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::inventory::ItemDepositedEvent",
        "asm-3",
        {},
        tx_hash="tx-deposit",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT last_seen FROM objects WHERE object_id = 'asm-3'"
    ).fetchone()
    assert obj["last_seen"] >= now

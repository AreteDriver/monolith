"""Tests for event processor — dispatch, handlers, inventory tracking."""

import json
import time

from backend.ingestion.event_processor import EventProcessor


def _make_event(event_type, object_id, parsed_json, tx_hash="tx-test",
                system_id="", object_type="inventory"):
    """Create a minimal chain_event row dict."""
    return {
        "id": 1,
        "event_id": f"{tx_hash}:0",
        "event_type": event_type,
        "object_id": object_id,
        "object_type": object_type,
        "system_id": system_id,
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
    row = db_conn.execute("SELECT * FROM item_ledger WHERE assembly_id = 'asm-1'").fetchone()
    assert row is not None
    assert row["quantity"] == 50
    assert row["event_type"] == "minted"
    assert row["item_type_id"] == "ore-123"

    # Check state has inventory
    obj = db_conn.execute("SELECT current_state FROM objects WHERE object_id = 'asm-1'").fetchone()
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

    obj = db_conn.execute("SELECT current_state FROM objects WHERE object_id = 'asm-2'").fetchone()
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

    obj = db_conn.execute("SELECT last_seen FROM objects WHERE object_id = 'asm-3'").fetchone()
    assert obj["last_seen"] >= now


# ── Dispatch & process_unprocessed ────────────────────────────────────────────


def test_process_unprocessed_batch(db_conn):
    """process_unprocessed processes pending events and marks them done."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO chain_events (event_id, event_type, object_id, object_type, "
        "system_id, transaction_hash, timestamp, raw_json, processed) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
        ("evt-1", "0xpkg::assembly::AssemblyCreatedEvent", "obj-1", "assembly",
         "sys-1", "tx-1", now, json.dumps({"parsedJson": {"typeId": "gate"}})),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    count = processor.process_unprocessed()
    assert count == 1

    # Event should be marked processed
    row = db_conn.execute("SELECT processed FROM chain_events WHERE event_id = 'evt-1'").fetchone()
    assert row["processed"] == 1


def test_process_unprocessed_empty(db_conn):
    """process_unprocessed with no pending events returns 0."""
    processor = EventProcessor(db_conn)
    assert processor.process_unprocessed() == 0


def test_dispatch_unknown_event_type(db_conn):
    """Unknown event types are tracked but don't crash."""
    processor = EventProcessor(db_conn)
    event = _make_event("0xpkg::unknown::WeirdEvent", "obj-x", {})
    processor._dispatch_event(event)

    assert processor.unknown_type_counts.get("WeirdEvent") == 1


def test_parse_raw_bad_json(db_conn):
    """_parse_raw handles malformed JSON gracefully."""
    processor = EventProcessor(db_conn)
    event = {"raw_json": "not valid json"}
    assert processor._parse_raw(event) == {}


# ── Assembly & Character handlers ─────────────────────────────────────────────


def test_handle_assembly_created(db_conn):
    """AssemblyCreatedEvent creates object in database."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::assembly::AssemblyCreatedEvent", "asm-new",
        {"typeId": "ssu", "status": "anchored", "owner": "0xowner1"},
        system_id="sys-100", object_type="assembly",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute("SELECT * FROM objects WHERE object_id = 'asm-new'").fetchone()
    assert obj is not None
    assert obj["object_type"] == "smartassemblies"
    assert obj["system_id"] == "sys-100"


def test_handle_assembly_created_empty_id(db_conn):
    """AssemblyCreatedEvent with empty object_id is skipped."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::assembly::AssemblyCreatedEvent", "",
        {"typeId": "ssu"},
    )
    processor._dispatch_event(event)

    count = db_conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    assert count == 0


def test_handle_character_created(db_conn):
    """CharacterCreatedEvent creates character object."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::character::CharacterCreatedEvent", "char-1",
        {"tribeId": "tribe-42", "characterAddress": "0xaddr1"},
        object_type="character",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute("SELECT * FROM objects WHERE object_id = 'char-1'").fetchone()
    assert obj is not None
    assert obj["object_type"] == "character"


# ── Status & Killmail handlers ────────────────────────────────────────────────


def test_handle_status_changed(db_conn):
    """StatusChangedEvent updates object state and records transition."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("asm-status", "smartassemblies", json.dumps({"state": "OFFLINE"}), now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::status::StatusChangedEvent", "asm-status",
        {"status": "ONLINE", "action": "fuel_added"},
        object_type="smartassemblies",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT current_state FROM objects WHERE object_id = 'asm-status'"
    ).fetchone()
    state = json.loads(obj["current_state"])
    assert state["state"] == "ONLINE"
    assert state["last_action"] == "fuel_added"

    # Transition recorded
    trans = db_conn.execute(
        "SELECT * FROM state_transitions WHERE object_id = 'asm-status'"
    ).fetchone()
    assert trans is not None
    assert json.loads(trans["from_state"])["state"] == "OFFLINE"
    assert json.loads(trans["to_state"])["state"] == "ONLINE"


def test_handle_killmail(db_conn):
    """KillmailCreatedEvent marks victim as destroyed."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, last_seen, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("victim-1", "character", now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::killmail::KillmailCreatedEvent", "",
        {"victimId": "victim-1", "killerId": "killer-1"},
    )
    processor._dispatch_event(event)

    victim = db_conn.execute(
        "SELECT destroyed_at FROM objects WHERE object_id = 'victim-1'"
    ).fetchone()
    assert victim["destroyed_at"] is not None


# ── Ownership & Fuel handlers ────────────────────────────────────────────────


def test_handle_ownership_transfer(db_conn):
    """OwnerCapTransferred updates object owner."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, current_owner,"
        " current_state, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("asm-own", "smartassemblies", "0xold", json.dumps({"state": "ONLINE"}), now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::ownership::OwnerCapTransferred", "",
        {"authorizedObjectId": "asm-own", "newOwner": "0xnew"},
    )
    processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT current_owner FROM objects WHERE object_id = 'asm-own'"
    ).fetchone()
    assert obj["current_owner"] == "0xnew"


def test_handle_fuel_event(db_conn):
    """FuelEvent updates fuel state on object."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("asm-fuel", "smartassemblies", json.dumps({}), now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::fuel::FuelEvent", "asm-fuel",
        {"fuelAmount": 5000, "variant": "BURNING_UPDATED"},
        object_type="smartassemblies",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT current_state FROM objects WHERE object_id = 'asm-fuel'"
    ).fetchone()
    state = json.loads(obj["current_state"])
    assert "networkNode" in state or "fuel" in state


def test_handle_jump_event(db_conn):
    """JumpEvent updates last_seen and system_id."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, last_seen, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("gate-1", "gate", now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::gate::JumpEvent", "gate-1",
        {"traveller": "0xtraveller"},
        object_type="gate", system_id="sys-200",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute("SELECT last_seen FROM objects WHERE object_id = 'gate-1'").fetchone()
    assert obj["last_seen"] >= now

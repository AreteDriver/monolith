"""Tests for event processor — dispatch, handlers, inventory tracking."""

import json
import time

from backend.ingestion.event_processor import EventProcessor


def _make_event(
    event_type, object_id, parsed_json, tx_hash="tx-test", system_id="", object_type="inventory"
):
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
        (
            "evt-1",
            "0xpkg::assembly::AssemblyCreatedEvent",
            "obj-1",
            "assembly",
            "sys-1",
            "tx-1",
            now,
            json.dumps({"parsedJson": {"typeId": "gate"}}),
        ),
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
        "0xpkg::assembly::AssemblyCreatedEvent",
        "asm-new",
        {"typeId": "ssu", "status": "anchored", "owner": "0xowner1"},
        system_id="sys-100",
        object_type="assembly",
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
        "0xpkg::assembly::AssemblyCreatedEvent",
        "",
        {"typeId": "ssu"},
    )
    processor._dispatch_event(event)

    count = db_conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    assert count == 0


def test_handle_character_created(db_conn):
    """CharacterCreatedEvent creates character object."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::character::CharacterCreatedEvent",
        "char-1",
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
        "0xpkg::status::StatusChangedEvent",
        "asm-status",
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
        "INSERT INTO objects (object_id, object_type, last_seen, created_at) VALUES (?, ?, ?, ?)",
        ("victim-1", "character", now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::killmail::KillmailCreatedEvent",
        "",
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
        "0xpkg::ownership::OwnerCapTransferred",
        "",
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
        "0xpkg::fuel::FuelEvent",
        "asm-fuel",
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
        "INSERT INTO objects (object_id, object_type, last_seen, created_at) VALUES (?, ?, ?, ?)",
        ("gate-1", "gate", now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::gate::JumpEvent",
        "gate-1",
        {"traveller": "0xtraveller"},
        object_type="gate",
        system_id="sys-200",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute("SELECT last_seen FROM objects WHERE object_id = 'gate-1'").fetchone()
    assert obj["last_seen"] >= now


# ── Additional coverage — uncovered branches ────────────────────────────────


def test_process_unprocessed_exception_in_handler(db_conn):
    """process_unprocessed continues after a handler error and marks successful ones."""
    now = int(time.time())
    # Insert two events: one that will fail (bad object_id triggers nothing),
    # and one good one
    for i, (eid, etype, oid) in enumerate(
        [
            ("evt-ok", "0xpkg::assembly::AssemblyCreatedEvent", "obj-ok"),
            ("evt-bad", "0xpkg::status::StatusChangedEvent", ""),
        ]
    ):
        db_conn.execute(
            "INSERT INTO chain_events (event_id, event_type, object_id, object_type, "
            "system_id, transaction_hash, timestamp, raw_json, processed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (eid, etype, oid, "assembly", "sys-1", f"tx-{i}", now + i,
             json.dumps({"parsedJson": {}})),
        )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    count = processor.process_unprocessed()
    assert count == 2  # Both dispatched (empty ID just returns early, no error)


def test_character_created_empty_id_skipped(db_conn):
    """CharacterCreatedEvent with empty object_id is skipped."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::character::CharacterCreatedEvent",
        "",
        {"tribeId": "tribe-1"},
    )
    processor._dispatch_event(event)
    count = db_conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    assert count == 0


def test_status_changed_empty_id_skipped(db_conn):
    """StatusChangedEvent with empty object_id is skipped."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::status::StatusChangedEvent",
        "",
        {"status": "ONLINE"},
    )
    processor._dispatch_event(event)
    count = db_conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    assert count == 0


def test_status_changed_no_prior_state(db_conn):
    """StatusChangedEvent on object with no prior state does not record transition."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::status::StatusChangedEvent",
        "asm-fresh",
        {"status": "ONLINE"},
        system_id="sys-1",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT current_state FROM objects WHERE object_id = 'asm-fresh'"
    ).fetchone()
    assert obj is not None
    state = json.loads(obj["current_state"])
    assert state["state"] == "ONLINE"

    # No transition since there was no prior state
    trans = db_conn.execute(
        "SELECT COUNT(*) FROM state_transitions WHERE object_id = 'asm-fresh'"
    ).fetchone()[0]
    assert trans == 0


def test_extract_entity_id_nested_dict():
    """_extract_entity_id unwraps nested dict with id/address fields."""
    result = EventProcessor._extract_entity_id(
        {"victim": {"id": "v-123", "address": "0xvictim"}},
        "victim",
    )
    assert result == "v-123"


def test_extract_entity_id_nested_dict_address_fallback():
    """_extract_entity_id falls back to address when id missing."""
    result = EventProcessor._extract_entity_id(
        {"killer": {"address": "0xkiller"}},
        "killer",
    )
    assert result == "0xkiller"


def test_extract_entity_id_no_match():
    """_extract_entity_id returns empty string when no keys match."""
    result = EventProcessor._extract_entity_id({}, "missing_key")
    assert result == ""


def test_ownership_transfer_missing_fields_skipped(db_conn):
    """OwnerCapTransferred with no object_id or owner is skipped."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::ownership::OwnerCapTransferred",
        "",
        {},  # No authorizedObjectId or newOwner
    )
    processor._dispatch_event(event)
    count = db_conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    assert count == 0


def test_ownership_transfer_with_previous_owner(db_conn):
    """OwnerCapTransferred records previous_owner in state."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, current_owner,"
        " current_state, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("asm-prev", "smartassemblies", "0xold",
         json.dumps({"state": "ONLINE"}), now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::ownership::OwnerCapTransferred",
        "",
        {
            "authorizedObjectId": "asm-prev",
            "newOwner": "0xnew",
            "previousOwner": "0xold",
        },
    )
    processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT current_state FROM objects WHERE object_id = 'asm-prev'"
    ).fetchone()
    state = json.loads(obj["current_state"])
    assert state["previous_owner"] == "0xold"
    assert state["owner"]["address"] == "0xnew"


def test_item_event_empty_id_skipped(db_conn):
    """Item event with empty object_id is skipped."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::inventory::ItemMintedEvent",
        "",
        {"quantity": 10},
    )
    processor._dispatch_event(event)
    count = db_conn.execute("SELECT COUNT(*) FROM item_ledger").fetchone()[0]
    assert count == 0


def test_item_destroyed_handler(db_conn):
    """ItemDestroyedEvent marks object as destroyed."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("asm-destroy", "smartassemblies", "{}", now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::inventory::ItemDestroyedEvent",
        "asm-destroy",
        {},
        tx_hash="tx-destroy",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT destroyed_at FROM objects WHERE object_id = 'asm-destroy'"
    ).fetchone()
    assert obj["destroyed_at"] is not None


def test_item_destroyed_empty_id_skipped(db_conn):
    """ItemDestroyedEvent with empty object_id is skipped."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::inventory::ItemDestroyedEvent",
        "",
        {},
    )
    processor._dispatch_event(event)


def test_fuel_event_empty_id_skipped(db_conn):
    """FuelEvent with empty object_id is skipped."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::fuel::FuelEvent",
        "",
        {"newQuantity": 100},
    )
    processor._dispatch_event(event)
    count = db_conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    assert count == 0


def test_fuel_event_with_quantity_fields(db_conn):
    """FuelEvent properly stores new_quantity and old_quantity."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("asm-fuel2", "smartassemblies", "{}", now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::fuel::FuelEvent",
        "asm-fuel2",
        {"newQuantity": 500, "oldQuantity": 600, "action": "BURNING_UPDATED"},
    )
    processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT current_state FROM objects WHERE object_id = 'asm-fuel2'"
    ).fetchone()
    state = json.loads(obj["current_state"])
    fuel = state["networkNode"]["fuel"]
    assert fuel["amount"] == 500
    assert fuel["previous_amount"] == 600
    assert fuel["last_action"] == "BURNING_UPDATED"


def test_jump_event_tracks_source_dest_and_character(db_conn):
    """JumpEvent updates last_seen on source, dest gates and character."""
    now = int(time.time())
    for oid, otype in [("gate-src", "gate"), ("gate-dst", "gate"), ("char-j", "character")]:
        db_conn.execute(
            "INSERT INTO objects (object_id, object_type, last_seen, created_at) "
            "VALUES (?, ?, ?, ?)",
            (oid, otype, now - 1000, now - 1000),
        )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::gate::JumpEvent",
        "gate-src",
        {"sourceGateId": "gate-src", "destGateId": "gate-dst", "characterId": "char-j"},
    )
    processor._dispatch_event(event)

    for oid in ("gate-src", "gate-dst", "char-j"):
        obj = db_conn.execute(
            "SELECT last_seen FROM objects WHERE object_id = ?", (oid,)
        ).fetchone()
        assert obj["last_seen"] >= now


def test_gate_link_event(db_conn):
    """GateLinkedEvent updates last_seen on both gates."""
    now = int(time.time())
    for oid in ("gate-a", "gate-b"):
        db_conn.execute(
            "INSERT INTO objects (object_id, object_type, last_seen, created_at) "
            "VALUES (?, ?, ?, ?)",
            (oid, "gate", now - 1000, now - 1000),
        )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::gate::GateLinkedEvent",
        "gate-a",
        {"sourceGateId": "gate-a", "destGateId": "gate-b"},
    )
    processor._dispatch_event(event)

    for oid in ("gate-a", "gate-b"):
        obj = db_conn.execute(
            "SELECT last_seen FROM objects WHERE object_id = ?", (oid,)
        ).fetchone()
        assert obj["last_seen"] >= now


def test_gate_unlinked_event(db_conn):
    """GateUnlinkedEvent updates last_seen on both gates."""
    now = int(time.time())
    for oid in ("gate-c", "gate-d"):
        db_conn.execute(
            "INSERT INTO objects (object_id, object_type, last_seen, created_at) "
            "VALUES (?, ?, ?, ?)",
            (oid, "gate", now - 1000, now - 1000),
        )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::gate::GateUnlinkedEvent",
        "gate-c",
        {"sourceGateId": "gate-c", "destGateId": "gate-d"},
    )
    processor._dispatch_event(event)

    for oid in ("gate-c", "gate-d"):
        obj = db_conn.execute(
            "SELECT last_seen FROM objects WHERE object_id = ?", (oid,)
        ).fetchone()
        assert obj["last_seen"] >= now


def test_fta_jump_handler(db_conn):
    """FTA_JumpPermit tracks gate usage and creates fta_gate object."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, last_seen, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("fta-gate-1", "gate", now - 100, now - 100),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "fta::jump::FTA_JumpPermit",
        "fta-gate-1",
        {
            "source_gate_id": "fta-gate-1",
            "destination_gate_id": "fta-gate-2",
            "character_id": "char-fta",
        },
    )
    processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT * FROM objects WHERE object_id = 'fta-gate-1'"
    ).fetchone()
    assert obj is not None
    state = json.loads(obj["current_state"])
    assert state["last_jump_character"] == "char-fta"
    assert state["last_jump_dest"] == "fta-gate-2"


def test_fta_state_mutation_handler(db_conn):
    """FTA_StateMutation tracks mutation on FTA object."""
    from unittest.mock import patch

    processor = EventProcessor(db_conn)
    event = _make_event(
        "fta::state::FTA_StateMutation",
        "",
        {
            "created_objects": ["obj-1", "obj-2"],
            "deleted_objects": ["obj-3"],
            "sender": "0xsender",
        },
    )

    # Patch at the source module where it's imported from
    with patch("backend.ingestion.fta_poller.FTA_OBJECT_ID", "fta-test-object"):
        processor._dispatch_event(event)

    obj = db_conn.execute(
        "SELECT current_state FROM objects WHERE object_id = 'fta-test-object'"
    ).fetchone()
    assert obj is not None
    state = json.loads(obj["current_state"])
    assert state["created_count"] == 2
    assert state["deleted_count"] == 1
    assert state["sender"] == "0xsender"


def test_unknown_type_summary_logging(db_conn):
    """Unknown event types log summary at every 100 occurrences."""
    processor = EventProcessor(db_conn)
    for i in range(100):
        event = _make_event(f"0xpkg::mod::UnknownType{i % 5}", "obj-x", {})
        processor._dispatch_event(event)

    total = sum(processor.unknown_type_counts.values())
    assert total == 100


def test_parse_raw_dict_input(db_conn):
    """_parse_raw handles raw_json that's already a dict."""
    processor = EventProcessor(db_conn)
    event = {"raw_json": {"parsedJson": {"key": "value"}}}
    assert processor._parse_raw(event) == {"key": "value"}


def test_gate_created_event_sets_gate_type(db_conn):
    """GateCreatedEvent sets object_type to 'gate'."""
    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::gate::GateCreatedEvent",
        "gate-new",
        {"typeId": "smartgate", "owner": "0xgateowner"},
        system_id="sys-50",
        object_type="gate",
    )
    processor._dispatch_event(event)

    obj = db_conn.execute("SELECT * FROM objects WHERE object_id = 'gate-new'").fetchone()
    assert obj is not None
    assert obj["object_type"] == "gate"


def test_killmail_with_nested_victim(db_conn):
    """KillmailCreatedEvent handles nested victim dict."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, last_seen, created_at) VALUES (?, ?, ?, ?)",
        ("victim-nested", "character", now, now),
    )
    db_conn.commit()

    processor = EventProcessor(db_conn)
    event = _make_event(
        "0xpkg::killmail::KillmailCreatedEvent",
        "",
        {"victim": {"id": "victim-nested", "address": "0xvaddr"}},
    )
    processor._dispatch_event(event)

    victim = db_conn.execute(
        "SELECT destroyed_at FROM objects WHERE object_id = 'victim-nested'"
    ).fetchone()
    assert victim["destroyed_at"] is not None


def test_dispatch_event_no_colons_in_type(db_conn):
    """Event type without :: produces empty suffix, no handler called."""
    processor = EventProcessor(db_conn)
    event = _make_event("PlainEventName", "obj-1", {})
    # Should not crash — suffix is empty, so no handler and no unknown tracking
    processor._dispatch_event(event)
    assert len(processor.unknown_type_counts) == 0

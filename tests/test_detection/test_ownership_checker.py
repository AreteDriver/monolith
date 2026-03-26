"""Tests for ownership checker (OC1 rule) — OwnerCap transfer detection."""

import json
import time

import pytest

from backend.db.database import init_db
from backend.detection.ownership_checker import OwnershipChecker


@pytest.fixture
def db_conn():
    """In-memory SQLite database with full schema."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


def _insert_event(conn, event_id, event_type, object_id, ts, raw_json):
    """Insert a chain event."""
    conn.execute(
        "INSERT INTO chain_events "
        "(event_id, event_type, object_id, timestamp, raw_json, processed) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (event_id, event_type, object_id, ts, json.dumps(raw_json)),
    )
    conn.commit()


def test_no_events_no_anomalies(db_conn):
    """Empty chain_events produces no anomalies."""
    checker = OwnershipChecker(db_conn)
    anomalies = checker.check()
    assert anomalies == []


def test_oc1_ownercap_transfer_event(db_conn):
    """OC1: TransferObject event with OwnerCap in raw_json detected."""
    now = int(time.time())
    _insert_event(
        db_conn,
        "evt-oc1",
        "TransferObject",
        "0xabc123",
        now,
        {
            "parsedJson": {
                "objectId": "0xabc123",
                "sender": "0xold_owner",
                "recipient": "0xnew_owner",
            },
            "type": {"repr": "0xpkg::auth::OwnerCap"},
        },
    )

    checker = OwnershipChecker(db_conn)
    anomalies = checker.check()

    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.anomaly_type == "OWNERCAP_TRANSFER"
    assert a.rule_id == "OC1"
    assert a.evidence["from_address"] == "0xold_owner"
    assert a.evidence["to_address"] == "0xnew_owner"


def test_oc1_ownercap_in_raw_json(db_conn):
    """OC1: Event with OwnerCap mentioned in raw_json caught by LIKE search."""
    now = int(time.time())
    _insert_event(
        db_conn,
        "evt-oc2",
        "SomeCustomEvent",
        "0xdef456",
        now,
        {
            "parsedJson": {
                "objectId": "0xdef456",
                "from": "0xsender",
                "to": "0xreceiver",
            },
            "type": {"repr": "0xpkg::custom::OwnerCapTransfer"},
        },
    )

    checker = OwnershipChecker(db_conn)
    anomalies = checker.check()

    assert len(anomalies) == 1
    assert anomalies[0].evidence["from_address"] == "0xsender"


def test_non_ownercap_transfer_ignored(db_conn):
    """Non-OwnerCap transfer events are ignored."""
    now = int(time.time())
    _insert_event(
        db_conn,
        "evt-fuel",
        "FuelEvent",
        "0xgate1",
        now,
        {"parsedJson": {"amount": 100, "action": {"variant": "BURNING_UPDATED"}}},
    )

    checker = OwnershipChecker(db_conn)
    anomalies = checker.check()

    assert anomalies == []


def test_old_events_excluded(db_conn):
    """Events older than LOOKBACK_SECONDS are not checked."""
    old_ts = int(time.time()) - 48 * 3600  # 2 days ago
    _insert_event(
        db_conn,
        "evt-old",
        "TransferObject",
        "0xold",
        old_ts,
        {
            "parsedJson": {"sender": "0xa", "recipient": "0xb"},
            "type": {"repr": "0xpkg::auth::OwnerCap"},
        },
    )

    checker = OwnershipChecker(db_conn)
    anomalies = checker.check()

    assert anomalies == []


def test_ownercap_transferred_event_type(db_conn):
    """OC1: OwnerCapTransferred event type is detected directly."""
    now = int(time.time())
    _insert_event(
        db_conn,
        "evt-oct",
        "OwnerCapTransferred",
        "0xcap1",
        now,
        {
            "parsedJson": {
                "sender": "0xoriginal",
                "newOwner": "0xdelegate",
            }
        },
    )

    checker = OwnershipChecker(db_conn)
    anomalies = checker.check()

    assert len(anomalies) == 1
    assert anomalies[0].evidence["to_address"] == "0xdelegate"


def test_involves_ownercap_via_event_type(db_conn):
    """_involves_ownercap: returns True for known event types."""
    assert OwnershipChecker._involves_ownercap(
        {"event_type": "TransferObject", "raw_json": ""},
        {},
    ) is True


def test_involves_ownercap_via_raw_json(db_conn):
    """_involves_ownercap: returns True for OwnerCap in raw_json."""
    assert OwnershipChecker._involves_ownercap(
        {"event_type": "SomeEvent", "raw_json": '{"type":"OwnerCap"}'},
        {},
    ) is True


def test_involves_ownercap_via_type_repr(db_conn):
    """_involves_ownercap: returns True when type.repr contains OwnerCap."""
    assert OwnershipChecker._involves_ownercap(
        {"event_type": "Other", "raw_json": "{}"},
        {"type": {"repr": "0xpkg::auth::OwnerCap"}},
    ) is True


def test_involves_ownercap_false(db_conn):
    """_involves_ownercap: returns False for unrelated events."""
    assert OwnershipChecker._involves_ownercap(
        {"event_type": "FuelEvent", "raw_json": '{"amount": 100}'},
        {"type": {"repr": "0xpkg::fuel::FuelEvent"}},
    ) is False


def test_extract_address_string(db_conn):
    """_extract_address: returns string value for matching key."""
    assert OwnershipChecker._extract_address(
        {"sender": "0xabc", "recipient": "0xdef"},
        "sender",
    ) == "0xabc"


def test_extract_address_nested_dict(db_conn):
    """_extract_address: extracts address from nested dict."""
    assert OwnershipChecker._extract_address(
        {"sender": {"address": "0x123"}},
        "sender",
    ) == "0x123"


def test_extract_address_missing(db_conn):
    """_extract_address: returns empty for missing keys."""
    assert OwnershipChecker._extract_address({"foo": "bar"}, "sender", "from") == ""


def test_extract_owner_valid_json(db_conn):
    """_extract_owner: parses JSON and returns owner address."""
    state = json.dumps({"owner": {"address": "0xowner1"}})
    assert OwnershipChecker._extract_owner(state) == "0xowner1"


def test_extract_owner_string_owner(db_conn):
    """_extract_owner: handles string owner field."""
    state = json.dumps({"owner": "0xdirect"})
    assert OwnershipChecker._extract_owner(state) == "0xdirect"


def test_extract_owner_empty(db_conn):
    """_extract_owner: returns empty for None/empty input."""
    assert OwnershipChecker._extract_owner("") == ""
    assert OwnershipChecker._extract_owner(None) == ""


def test_extract_owner_invalid_json(db_conn):
    """_extract_owner: returns empty for invalid JSON."""
    assert OwnershipChecker._extract_owner("not json") == ""


def test_ownership_divergence_with_transfer(db_conn):
    """Ownership divergence with transfer event detected as OWNERCAP_DELEGATION."""
    now = int(time.time())
    # Insert two snapshots with different owners
    db_conn.execute(
        "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
        "VALUES (?, ?, ?, ?, ?)",
        ("obj-div", "SmartAssembly", json.dumps({"owner": {"address": "0xold"}}), now - 60, "test"),
    )
    db_conn.execute(
        "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
        "VALUES (?, ?, ?, ?, ?)",
        ("obj-div", "SmartAssembly", json.dumps({"owner": {"address": "0xnew"}}), now, "test"),
    )
    # Insert a transfer event
    _insert_event(
        db_conn, "evt-transfer", "TransferObject", "obj-div", now - 30,
        {"parsedJson": {"objectId": "obj-div"}, "type": {"repr": "OwnerCap"}},
    )
    db_conn.commit()

    checker = OwnershipChecker(db_conn)
    anomalies = checker.check()

    delegations = [a for a in anomalies if a.anomaly_type == "OWNERCAP_DELEGATION"]
    assert len(delegations) >= 1

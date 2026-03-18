"""Tests for killmail reconciliation checker (K1, K2 rules) — chain-internal."""

import json
import time

import pytest

from backend.db.database import init_db
from backend.detection.killmail_checker import (
    DUPLICATE_WINDOW_SECONDS,
    LOOKBACK_SECONDS,
    KillmailChecker,
)


@pytest.fixture
def db_conn():
    """In-memory SQLite database with full schema."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


def _insert_chain_kill(conn, event_id, victim_id, killer_id, ts, killmail_id="", reporter_id=""):
    """Insert a KillmailCreatedEvent into chain_events."""
    parsed = {
        "parsedJson": {
            "victim_id": victim_id,
            "killer_id": killer_id,
        }
    }
    if killmail_id:
        parsed["parsedJson"]["killmail_id"] = killmail_id
    if reporter_id:
        parsed["parsedJson"]["reported_by_character_id"] = reporter_id
    else:
        parsed["parsedJson"]["reported_by_character_id"] = killer_id
    conn.execute(
        "INSERT INTO chain_events "
        "(event_id, event_type, object_id, timestamp, raw_json, processed) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (event_id, "KillmailCreatedEvent", victim_id, ts, json.dumps(parsed)),
    )
    conn.commit()


def test_no_kills_no_anomalies(db_conn):
    """Empty chain_events produces no anomalies."""
    checker = KillmailChecker(db_conn)
    anomalies = checker.check()
    assert anomalies == []


def test_single_kill_no_anomalies(db_conn):
    """A single kill with matching reporter produces no anomalies."""
    now = int(time.time())
    _insert_chain_kill(db_conn, "evt-001", "victim-a", "killer-b", now)
    checker = KillmailChecker(db_conn)
    anomalies = checker.check()
    assert anomalies == []


def test_k1_duplicate_kills_same_victim(db_conn):
    """K1: Same victim killed twice within DUPLICATE_WINDOW_SECONDS."""
    now = int(time.time())
    _insert_chain_kill(db_conn, "evt-001", "victim-a", "killer-b", now)
    _insert_chain_kill(db_conn, "evt-002", "victim-a", "killer-c", now + 30)

    checker = KillmailChecker(db_conn)
    anomalies = checker.check()

    k1s = [a for a in anomalies if a.rule_id == "K1"]
    assert len(k1s) == 1
    assert k1s[0].anomaly_type == "DUPLICATE_KILLMAIL"
    assert k1s[0].object_id == "victim-a"
    assert k1s[0].evidence["time_delta_seconds"] == 30


def test_k1_no_duplicate_outside_window(db_conn):
    """K1: Same victim killed outside the window is NOT a duplicate."""
    now = int(time.time())
    gap = DUPLICATE_WINDOW_SECONDS + 60
    _insert_chain_kill(db_conn, "evt-001", "victim-a", "killer-b", now)
    _insert_chain_kill(db_conn, "evt-002", "victim-a", "killer-c", now + gap)

    checker = KillmailChecker(db_conn)
    anomalies = checker.check()

    k1s = [a for a in anomalies if a.rule_id == "K1"]
    assert len(k1s) == 0


def test_k1_different_victims_no_duplicate(db_conn):
    """K1: Different victims killed close together is NOT a duplicate."""
    now = int(time.time())
    _insert_chain_kill(db_conn, "evt-001", "victim-a", "killer-b", now)
    _insert_chain_kill(db_conn, "evt-002", "victim-b", "killer-c", now + 5)

    checker = KillmailChecker(db_conn)
    anomalies = checker.check()

    k1s = [a for a in anomalies if a.rule_id == "K1"]
    assert len(k1s) == 0


def test_k2_third_party_reporter(db_conn):
    """K2: Kill reported by someone other than the killer."""
    now = int(time.time())
    _insert_chain_kill(db_conn, "evt-001", "victim-a", "killer-b", now, reporter_id="bystander-c")

    checker = KillmailChecker(db_conn)
    anomalies = checker.check()

    k2s = [a for a in anomalies if a.rule_id == "K2"]
    assert len(k2s) == 1
    assert k2s[0].anomaly_type == "THIRD_PARTY_KILL_REPORT"
    assert k2s[0].evidence["killer_id"] == "killer-b"
    assert k2s[0].evidence["reporter_id"] == "bystander-c"


def test_k2_self_reported_no_anomaly(db_conn):
    """K2: Kill reported by the killer produces no anomaly."""
    now = int(time.time())
    _insert_chain_kill(db_conn, "evt-001", "victim-a", "killer-b", now, reporter_id="killer-b")

    checker = KillmailChecker(db_conn)
    anomalies = checker.check()

    k2s = [a for a in anomalies if a.rule_id == "K2"]
    assert len(k2s) == 0


def test_old_kills_excluded(db_conn):
    """Chain kills older than LOOKBACK_SECONDS are not checked."""
    old_ts = int(time.time()) - LOOKBACK_SECONDS - 3600
    _insert_chain_kill(db_conn, "evt-old", "victim-old", "killer-old", old_ts)

    checker = KillmailChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0


def test_camel_case_chain_fields(db_conn):
    """Chain events with camelCase parsedJson keys are parsed correctly."""
    now = int(time.time())
    parsed = {
        "parsedJson": {
            "victimId": "victim-cc",
            "killerId": "killer-cc",
            "reportedByCharacterId": "bystander-cc",
        },
    }
    db_conn.execute(
        "INSERT INTO chain_events "
        "(event_id, event_type, object_id, timestamp, raw_json, processed) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        ("evt-cc", "KillmailCreatedEvent", "victim-cc", now, json.dumps(parsed)),
    )
    db_conn.commit()

    checker = KillmailChecker(db_conn)
    anomalies = checker.check()

    k2s = [a for a in anomalies if a.rule_id == "K2"]
    assert len(k2s) == 1
    assert k2s[0].evidence["reporter_id"] == "bystander-cc"


def test_mixed_anomalies(db_conn):
    """Multiple kills: duplicate victim + third-party reporter detected together."""
    now = int(time.time())
    # Duplicate kills on same victim
    _insert_chain_kill(db_conn, "evt-d1", "victim-dup", "killer-a", now)
    _insert_chain_kill(db_conn, "evt-d2", "victim-dup", "killer-b", now + 10)
    # Third-party report
    _insert_chain_kill(db_conn, "evt-tp", "victim-other", "killer-c", now, reporter_id="witness-w")

    checker = KillmailChecker(db_conn)
    anomalies = checker.check()

    k1s = [a for a in anomalies if a.rule_id == "K1"]
    k2s = [a for a in anomalies if a.rule_id == "K2"]
    assert len(k1s) == 1
    assert len(k2s) == 1

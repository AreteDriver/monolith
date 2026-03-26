"""Tests for session checkers — ES1/ES2, DA1, EV1/EV2."""

import json
import time

from backend.detection.dead_assembly_checker import DeadAssemblyChecker
from backend.detection.engagement_checker import EngagementChecker
from backend.detection.velocity_checker import VelocityChecker

# -- SQL helpers ---------------------------------------------------------------

_INSERT_EVENT = (
    "INSERT INTO chain_events "
    "(event_id, event_type, object_id, object_type, system_id, "
    "block_number, transaction_hash, timestamp, raw_json, processed) "
    "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 1)"
)

_INSERT_OBJECT = (
    "INSERT INTO objects "
    "(object_id, object_type, created_at, last_seen, system_id) "
    "VALUES (?, ?, ?, ?, ?)"
)

_INSERT_LEDGER = (
    "INSERT INTO item_ledger "
    "(assembly_id, item_type_id, event_type, quantity, "
    "event_id, transaction_hash, timestamp) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)


def _seed_killmail(conn, event_id, killer_id, victim_id, ts, system_id="sys-1"):
    """Insert a killmail chain event with killer/victim in raw_json."""
    raw = json.dumps({"killer_id": killer_id, "victim_id": victim_id})
    conn.execute(
        _INSERT_EVENT,
        (
            event_id,
            "pkg::killmail::KillmailCreatedEvent",
            event_id,
            "killmail",
            system_id,
            event_id,
            ts,
            raw,
        ),
    )
    conn.commit()


def _seed_chain_event(conn, event_id, sender, ts, event_type="GateJumpEvent", system_id="sys-1"):
    """Insert a generic chain event with sender in raw_json."""
    raw = json.dumps({"sender": sender})
    conn.execute(
        _INSERT_EVENT,
        (
            event_id,
            f"pkg::{event_type}",
            sender,
            "",
            system_id,
            event_id,
            ts,
            raw,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# ES1 — Orphaned killmail
# ---------------------------------------------------------------------------


def test_es1_killmail_no_preceding_events(db_conn):
    """Killmail with no preceding killer events triggers ES1."""
    now = int(time.time())
    _seed_killmail(db_conn, "km-1", "0xkiller1", "0xvictim1", now)

    checker = EngagementChecker(db_conn)
    anomalies = checker.check()
    es1 = [a for a in anomalies if a.rule_id == "ES1"]
    assert len(es1) == 1
    assert es1[0].severity == "HIGH"
    assert es1[0].evidence["killer_id"] == "0xkiller1"


def test_es1_killmail_with_preceding_gate_jump(db_conn):
    """Killmail with preceding gate_jump for killer produces no ES1."""
    now = int(time.time())
    # Killer has a gate jump 2 minutes before
    _seed_chain_event(db_conn, "gate-1", "0xkiller2", now - 120)
    _seed_killmail(db_conn, "km-2", "0xkiller2", "0xvictim2", now)

    checker = EngagementChecker(db_conn)
    anomalies = checker.check()
    es1 = [a for a in anomalies if a.rule_id == "ES1"]
    assert len(es1) == 0


# ---------------------------------------------------------------------------
# ES2 — Ghost engagement
# ---------------------------------------------------------------------------


def test_es2_victim_no_prior_events(db_conn):
    """Victim with zero prior events triggers ES2."""
    now = int(time.time())
    _seed_killmail(db_conn, "km-3", "0xkiller3", "0xghost_victim", now)

    checker = EngagementChecker(db_conn)
    anomalies = checker.check()
    es2 = [a for a in anomalies if a.rule_id == "ES2"]
    assert len(es2) == 1
    assert es2[0].severity == "CRITICAL"
    assert es2[0].evidence["victim_id"] == "0xghost_victim"


def test_es2_nested_victim_id_extracted(db_conn):
    """Victim ID in nested dict format is unwrapped correctly (no false positive)."""
    now = int(time.time())
    victim_item_id = "2112000187"
    # Victim has prior activity under its actual item_id
    _seed_chain_event(db_conn, "fuel-nested-1", victim_item_id, now - 3600)
    # Killmail stores victim_id as nested dict (EVE Frontier format)
    raw = json.dumps(
        {
            "killer_id": "0xkiller_nested",
            "victim_id": {"item_id": victim_item_id, "tenant": "utopia"},
        }
    )
    db_conn.execute(
        _INSERT_EVENT,
        (
            "km-nested-1",
            "pkg::killmail::KillmailCreatedEvent",
            "km-nested-1",
            "killmail",
            "sys-1",
            "km-nested-1",
            now,
            raw,
        ),
    )
    db_conn.commit()

    checker = EngagementChecker(db_conn)
    anomalies = checker.check()
    es2 = [a for a in anomalies if a.rule_id == "ES2"]
    assert len(es2) == 0, "Nested victim_id with prior events should NOT trigger ES2"


def test_es2_nested_victim_id_no_history(db_conn):
    """Nested victim_id with genuinely zero history still triggers ES2."""
    now = int(time.time())
    raw = json.dumps(
        {
            "killer_id": "0xkiller_real",
            "victim_id": {"item_id": "9999999", "tenant": "stillness"},
        }
    )
    db_conn.execute(
        _INSERT_EVENT,
        (
            "km-nested-2",
            "pkg::killmail::KillmailCreatedEvent",
            "km-nested-2",
            "killmail",
            "sys-1",
            "km-nested-2",
            now,
            raw,
        ),
    )
    db_conn.commit()

    checker = EngagementChecker(db_conn)
    anomalies = checker.check()
    es2 = [a for a in anomalies if a.rule_id == "ES2"]
    assert len(es2) == 1
    assert es2[0].evidence["victim_id"] == "9999999"


def test_es2_victim_with_prior_events(db_conn):
    """Victim with prior events produces no ES2."""
    now = int(time.time())
    # Victim was active an hour before
    _seed_chain_event(db_conn, "fuel-1", "0xreal_victim", now - 3600)
    _seed_killmail(db_conn, "km-4", "0xkiller4", "0xreal_victim", now)

    checker = EngagementChecker(db_conn)
    anomalies = checker.check()
    es2 = [a for a in anomalies if a.rule_id == "ES2"]
    assert len(es2) == 0


# ---------------------------------------------------------------------------
# DA1 — Dead assembly
# ---------------------------------------------------------------------------


def test_da1_dead_assembly_with_old_fuel(db_conn):
    """Assembly silent 7+ days with old fuel events triggers DA1."""
    now = int(time.time())
    eight_days_ago = now - (8 * 86400)

    # Assembly last seen 8 days ago
    db_conn.execute(
        _INSERT_OBJECT,
        ("asm-dead-1", "gate", eight_days_ago - 86400, eight_days_ago, "sys-10"),
    )
    # Fuel event from 8 days ago
    db_conn.execute(
        _INSERT_EVENT,
        (
            "fuel-old-1",
            "pkg::fuel::FuelEvent",
            "asm-dead-1",
            "fuel",
            "sys-10",
            "fuel-old-1",
            eight_days_ago,
            "{}",
        ),
    )
    db_conn.commit()

    checker = DeadAssemblyChecker(db_conn)
    anomalies = checker.check()
    da1 = [a for a in anomalies if a.rule_id == "DA1"]
    assert len(da1) == 1
    assert da1[0].severity == "LOW"
    assert da1[0].evidence["days_silent"] >= 8.0


def test_da1_recently_active_assembly(db_conn):
    """Assembly active within 7 days produces no DA1."""
    now = int(time.time())

    # Assembly last seen 1 day ago
    db_conn.execute(
        _INSERT_OBJECT,
        ("asm-alive-1", "gate", now - 86400, now - 86400, "sys-20"),
    )
    # Recent fuel event
    db_conn.execute(
        _INSERT_EVENT,
        (
            "fuel-recent-1",
            "pkg::fuel::FuelEvent",
            "asm-alive-1",
            "fuel",
            "sys-20",
            "fuel-recent-1",
            now - 86400,
            "{}",
        ),
    )
    db_conn.commit()

    checker = DeadAssemblyChecker(db_conn)
    anomalies = checker.check()
    da1 = [a for a in anomalies if a.rule_id == "DA1"]
    assert len(da1) == 0


# ---------------------------------------------------------------------------
# EV1 — Velocity spike
# ---------------------------------------------------------------------------


def test_ev1_velocity_spike_detected(db_conn):
    """10 events in last hour vs 1/hr average triggers EV1."""
    now = int(time.time())

    # Seed 7-day baseline: 1 event per day = ~0.006/hr over 168 hours
    for i in range(7):
        day_ts = now - ((i + 1) * 86400)
        db_conn.execute(
            _INSERT_LEDGER,
            ("asm-spike-1", "item-X", "ItemDepositedEvent", 1, f"ev-old-{i}", f"tx-{i}", day_ts),
        )

    # Seed 10 events in the last hour (spike)
    for i in range(10):
        db_conn.execute(
            _INSERT_LEDGER,
            (
                "asm-spike-1",
                "item-X",
                "ItemDepositedEvent",
                1,
                f"ev-new-{i}",
                f"tx-new-{i}",
                now - 60 + i,
            ),
        )
    db_conn.commit()

    checker = VelocityChecker(db_conn)
    anomalies = checker.check()
    ev1 = [a for a in anomalies if a.rule_id == "EV1"]
    assert len(ev1) == 1
    assert ev1[0].severity == "HIGH"
    assert ev1[0].evidence["last_hour_count"] == 10
    assert ev1[0].evidence["spike_multiplier"] > 3


def test_ev1_normal_rate_no_anomaly(db_conn):
    """Normal flow rate produces no EV1."""
    now = int(time.time())

    # Steady 1 event per hour over 7 days (168 events)
    for i in range(168):
        ts = now - (i * 3600)
        db_conn.execute(
            _INSERT_LEDGER,
            ("asm-normal-1", "item-Y", "ItemDepositedEvent", 1, f"ev-{i}", f"tx-{i}", ts),
        )
    db_conn.commit()

    checker = VelocityChecker(db_conn)
    anomalies = checker.check()
    ev1 = [a for a in anomalies if a.rule_id == "EV1"]
    assert len(ev1) == 0


# ---------------------------------------------------------------------------
# EV2 — Velocity drop
# ---------------------------------------------------------------------------


def test_ev2_active_assembly_goes_silent(db_conn):
    """Active assembly with 0 events in 24h triggers EV2."""
    now = int(time.time())

    # Seed 5+ events/day over 7 days, but ALL older than 24h
    for i in range(40):
        # Spread events from 2 days ago to 7 days ago
        ts = now - 86400 * 2 - (i * 10800)  # Every 3 hours, starting 2 days ago
        db_conn.execute(
            _INSERT_LEDGER,
            ("asm-drop-1", "item-Z", "ItemDepositedEvent", 1, f"ev-drop-{i}", f"tx-{i}", ts),
        )
    db_conn.commit()

    checker = VelocityChecker(db_conn)
    anomalies = checker.check()
    ev2 = [a for a in anomalies if a.rule_id == "EV2"]
    assert len(ev2) == 1
    assert ev2[0].severity == "MEDIUM"
    assert ev2[0].evidence["last_24h_count"] == 0


def test_ev2_assembly_still_active(db_conn):
    """Assembly with recent events produces no EV2."""
    now = int(time.time())

    # Seed 5+ events/day over 7 days including recent ones
    for i in range(40):
        ts = now - (i * 10800)  # Every 3 hours, most recent is now
        db_conn.execute(
            _INSERT_LEDGER,
            ("asm-active-1", "item-W", "ItemDepositedEvent", 1, f"ev-act-{i}", f"tx-{i}", ts),
        )
    db_conn.commit()

    checker = VelocityChecker(db_conn)
    anomalies = checker.check()
    ev2 = [a for a in anomalies if a.rule_id == "EV2"]
    assert len(ev2) == 0

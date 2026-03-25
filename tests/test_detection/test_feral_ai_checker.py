"""Tests for feral AI checker — FA1/FA2 rules."""

import time

from backend.detection.feral_ai_checker import (
    MIN_HISTORY,
    SILENCE_THRESHOLD,
    SURGE_THRESHOLD,
    SURGE_WINDOW,
    FeralAIChecker,
)


def _seed_feral_event(conn, event_id, zone_id="zone-1", system_id="sys-1", detected_at=None):
    """Insert a feral AI event."""
    conn.execute(
        "INSERT INTO feral_ai_events "
        "(event_id, ai_entity_id, event_type, zone_id, system_id, detected_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            event_id,
            f"ai-{event_id}",
            "FeralSpawn",
            zone_id,
            system_id,
            detected_at or int(time.time()),
        ),
    )
    conn.commit()


# -- FA1 — Hive Surge --


def test_fa1_surge_triggers(db_conn):
    """5+ events in 30min window triggers FA1."""
    now = int(time.time())
    for i in range(SURGE_THRESHOLD + 1):
        _seed_feral_event(db_conn, f"surge-{i}", "zone-hot", detected_at=now - 60 * i)

    checker = FeralAIChecker(db_conn)
    anomalies = checker.check()
    fa1 = [a for a in anomalies if a.rule_id == "FA1"]
    assert len(fa1) == 1
    assert fa1[0].evidence["event_count"] >= SURGE_THRESHOLD


def test_fa1_below_threshold_no_trigger(db_conn):
    """Fewer than threshold events does not trigger FA1."""
    now = int(time.time())
    for i in range(SURGE_THRESHOLD - 1):
        _seed_feral_event(db_conn, f"low-{i}", "zone-quiet", detected_at=now - 60 * i)

    checker = FeralAIChecker(db_conn)
    anomalies = checker.check()
    fa1 = [a for a in anomalies if a.rule_id == "FA1"]
    assert len(fa1) == 0


def test_fa1_old_events_no_trigger(db_conn):
    """Events outside the surge window do not trigger FA1."""
    now = int(time.time())
    old = now - SURGE_WINDOW - 600  # Well outside window
    for i in range(SURGE_THRESHOLD + 2):
        _seed_feral_event(db_conn, f"old-{i}", "zone-old", detected_at=old - 60 * i)

    checker = FeralAIChecker(db_conn)
    anomalies = checker.check()
    fa1 = [a for a in anomalies if a.rule_id == "FA1"]
    assert len(fa1) == 0


# -- FA2 — Silent Zone --


def test_fa2_silent_zone_triggers(db_conn):
    """Previously active zone with no recent events triggers FA2."""
    now = int(time.time())
    old = now - SILENCE_THRESHOLD - 600
    for i in range(MIN_HISTORY + 1):
        _seed_feral_event(db_conn, f"hist-{i}", "zone-silent", detected_at=old - 3600 * i)

    checker = FeralAIChecker(db_conn)
    anomalies = checker.check()
    fa2 = [a for a in anomalies if a.rule_id == "FA2"]
    assert len(fa2) == 1
    assert fa2[0].evidence["silent_minutes"] > SILENCE_THRESHOLD // 60


def test_fa2_active_zone_no_trigger(db_conn):
    """Zone with recent events does not trigger FA2."""
    now = int(time.time())
    for i in range(MIN_HISTORY + 1):
        _seed_feral_event(db_conn, f"active-{i}", "zone-active", detected_at=now - 60 * i)

    checker = FeralAIChecker(db_conn)
    anomalies = checker.check()
    fa2 = [a for a in anomalies if a.rule_id == "FA2"]
    assert len(fa2) == 0


def test_fa2_low_history_no_trigger(db_conn):
    """Zone with too few historical events does not trigger FA2."""
    now = int(time.time())
    old = now - SILENCE_THRESHOLD - 600
    # Only 1 event (below MIN_HISTORY)
    _seed_feral_event(db_conn, "lonely-1", "zone-lonely", detected_at=old)

    checker = FeralAIChecker(db_conn)
    anomalies = checker.check()
    fa2 = [a for a in anomalies if a.rule_id == "FA2"]
    assert len(fa2) == 0

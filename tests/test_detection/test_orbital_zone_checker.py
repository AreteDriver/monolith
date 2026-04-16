"""Tests for orbital zone checker — OZ1/OZ2 rules."""

import time

from backend.detection.orbital_zone_checker import BLIND_SPOT_THRESHOLD, OrbitalZoneChecker


def _seed_zone(
    conn,
    zone_id,
    zone_name="Zone-A",
    system_id="sys-1",
    tier=0,
    threat="LOW",
    last_polled=None,
):
    """Insert an orbital zone."""
    conn.execute(
        "INSERT INTO orbital_zones "
        "(zone_id, zone_name, system_id, feral_ai_tier, threat_level, last_polled, discovered_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (zone_id, zone_name, system_id, tier, threat, last_polled, int(time.time())),
    )
    conn.commit()


def _seed_feral_event(conn, event_id, zone_id, system_id="sys-1", detected_at=None):
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


# -- OZ1 — Blind Spot --


def test_oz1_stale_zone_triggers(db_conn):
    """Zone not polled within threshold triggers OZ1."""
    stale_time = int(time.time()) - BLIND_SPOT_THRESHOLD - 60
    _seed_zone(db_conn, "zone-stale-1", last_polled=stale_time)

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker.check()
    oz1 = [a for a in anomalies if a.rule_id == "OZ1"]
    assert len(oz1) == 1
    assert oz1[0].evidence["dark_minutes"] > BLIND_SPOT_THRESHOLD // 60


def test_oz1_fresh_zone_no_trigger(db_conn):
    """Recently polled zone does not trigger OZ1."""
    _seed_zone(db_conn, "zone-fresh-1", last_polled=int(time.time()))

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker.check()
    oz1 = [a for a in anomalies if a.rule_id == "OZ1"]
    assert len(oz1) == 0


def test_oz1_null_polled_triggers(db_conn):
    """Zone with NULL last_polled triggers OZ1."""
    _seed_zone(db_conn, "zone-null-1", last_polled=None)

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker.check()
    oz1 = [a for a in anomalies if a.rule_id == "OZ1"]
    assert len(oz1) == 1


# -- OZ2 — Tier Escalation --


def test_oz2_active_tier_triggers(db_conn):
    """Zone with tier > 0 and 3+ recent events triggers OZ2."""
    now = int(time.time())
    _seed_zone(db_conn, "zone-hot-1", tier=3, threat="HIGH", last_polled=now)
    for i in range(4):
        _seed_feral_event(db_conn, f"fe-{i}", "zone-hot-1", detected_at=now - 60 * i)

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker.check()
    oz2 = [a for a in anomalies if a.rule_id == "OZ2"]
    assert len(oz2) == 1
    assert oz2[0].evidence["current_tier"] == 3
    assert oz2[0].evidence["recent_events"] >= 3


def test_oz2_low_events_no_trigger(db_conn):
    """Zone with tier > 0 but < 3 recent events does not trigger OZ2."""
    now = int(time.time())
    _seed_zone(db_conn, "zone-calm-1", tier=2, threat="MEDIUM", last_polled=now)
    _seed_feral_event(db_conn, "fe-single-1", "zone-calm-1", detected_at=now)

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker.check()
    oz2 = [a for a in anomalies if a.rule_id == "OZ2"]
    assert len(oz2) == 0


def test_oz2_tier_zero_no_trigger(db_conn):
    """Zone with tier 0 does not trigger OZ2 even with events."""
    now = int(time.time())
    _seed_zone(db_conn, "zone-safe-1", tier=0, last_polled=now)
    for i in range(5):
        _seed_feral_event(db_conn, f"fe-safe-{i}", "zone-safe-1", detected_at=now)

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker.check()
    oz2 = [a for a in anomalies if a.rule_id == "OZ2"]
    assert len(oz2) == 0


# ── Exception handling ───────────────────────────────────────────────────────


def test_oz1_handles_missing_table(db_conn):
    """OZ1: Returns empty when orbital_zones table is missing."""
    db_conn.execute("DROP TABLE IF EXISTS orbital_zones")
    db_conn.commit()

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker._check_oz1_blind_spot()
    assert anomalies == []


def test_oz2_handles_missing_table(db_conn):
    """OZ2: Returns empty when tables are missing."""
    db_conn.execute("DROP TABLE IF EXISTS feral_ai_events")
    db_conn.execute("DROP TABLE IF EXISTS orbital_zones")
    db_conn.commit()

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker._check_oz2_tier_escalation()
    assert anomalies == []


def test_oz1_zone_with_null_name(db_conn):
    """OZ1: Zone with NULL name uses zone_id in description."""
    stale = int(time.time()) - BLIND_SPOT_THRESHOLD - 60
    _seed_zone(db_conn, "zone-noname", zone_name=None, last_polled=stale)

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker.check()
    oz1 = [a for a in anomalies if a.rule_id == "OZ1"]
    assert len(oz1) == 1
    assert "zone-noname" in oz1[0].evidence["description"]


def test_oz2_zone_with_null_system(db_conn):
    """OZ2: Zone with NULL system_id defaults to empty string."""
    now = int(time.time())
    _seed_zone(db_conn, "zone-nosys", zone_name="Hot Zone", system_id=None,
               tier=2, last_polled=now)
    for i in range(4):
        _seed_feral_event(db_conn, f"fe-nosys-{i}", "zone-nosys",
                          system_id="", detected_at=now - 60 * i)

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker.check()
    oz2 = [a for a in anomalies if a.rule_id == "OZ2"]
    assert len(oz2) == 1
    assert oz2[0].system_id == ""


def test_oz1_multiple_stale_zones(db_conn):
    """OZ1: Multiple stale zones each produce an anomaly."""
    stale = int(time.time()) - BLIND_SPOT_THRESHOLD - 120
    _seed_zone(db_conn, "zone-s1", zone_name="Alpha", last_polled=stale)
    _seed_zone(db_conn, "zone-s2", zone_name="Beta", last_polled=stale)

    checker = OrbitalZoneChecker(db_conn)
    anomalies = checker.check()
    oz1 = [a for a in anomalies if a.rule_id == "OZ1"]
    assert len(oz1) == 2

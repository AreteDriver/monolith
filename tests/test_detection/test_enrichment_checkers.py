"""Tests for enrichment checkers — OV1/OV2, WC1, CC1, IA1, BP1, TH1."""

import json
import time

from backend.detection.bot_pattern_checker import BotPatternChecker
from backend.detection.config_change_checker import ConfigChangeChecker
from backend.detection.inventory_audit_checker import InventoryAuditChecker
from backend.detection.object_version_checker import ObjectVersionChecker
from backend.detection.tribe_hopping_checker import TribeHoppingChecker
from backend.detection.wallet_concentration_checker import (
    WalletConcentrationChecker,
)

# -- SQL helpers to keep lines short ----------------------------------------

_INSERT_OBJ_VER = (
    "INSERT INTO object_versions "
    "(object_id, version, digest, state_json, fetched_at) "
    "VALUES (?, ?, ?, ?, ?)"
)

_INSERT_CONFIG = (
    "INSERT INTO config_snapshots "
    "(config_type, config_address, version, state_json, fetched_at) "
    "VALUES (?, ?, ?, ?, ?)"
)

_INSERT_LEDGER = (
    "INSERT INTO item_ledger "
    "(assembly_id, item_type_id, event_type, quantity, "
    "event_id, transaction_hash, timestamp) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_INSERT_WALLET = (
    "INSERT INTO wallet_activity "
    "(wallet_address, tx_count, avg_interval_seconds, "
    "interval_stddev, first_tx, last_tx, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_INSERT_ENTITY = (
    "INSERT INTO entity_names "
    "(entity_id, display_name, entity_type, updated_at) "
    "VALUES (?, ?, ?, ?)"
)

# ---------------------------------------------------------------------------
# OV1 — State rollback
# ---------------------------------------------------------------------------


def test_ov1_version_decrease_detected(db_conn):
    """Version decrease across snapshots triggers OV1."""
    now = int(time.time())
    db_conn.execute(_INSERT_OBJ_VER, ("obj-A", 10, "d1", "{}", now - 100))
    db_conn.execute(_INSERT_OBJ_VER, ("obj-A", 5, "d2", "{}", now))
    db_conn.commit()

    checker = ObjectVersionChecker(db_conn)
    anomalies = checker.check()
    ov1 = [a for a in anomalies if a.rule_id == "OV1"]
    assert len(ov1) == 1
    assert ov1[0].object_id == "obj-A"
    assert ov1[0].severity == "CRITICAL"


def test_ov1_monotonic_versions_no_anomaly(db_conn):
    """Monotonically increasing versions produce no OV1."""
    now = int(time.time())
    for i, ver in enumerate([1, 2, 3]):
        db_conn.execute(
            _INSERT_OBJ_VER,
            ("obj-B", ver, f"d{i}", "{}", now + i),
        )
    db_conn.commit()

    checker = ObjectVersionChecker(db_conn)
    anomalies = checker.check()
    ov1 = [a for a in anomalies if a.rule_id == "OV1"]
    assert len(ov1) == 0


# ---------------------------------------------------------------------------
# OV2 — Unauthorized state modification
# ---------------------------------------------------------------------------


def test_ov2_version_bump_no_event(db_conn):
    """Version bump with no chain event triggers OV2."""
    now = int(time.time())
    db_conn.execute(_INSERT_OBJ_VER, ("obj-C", 1, "d1", "{}", now - 100))
    db_conn.execute(_INSERT_OBJ_VER, ("obj-C", 5, "d2", "{}", now))
    db_conn.commit()

    checker = ObjectVersionChecker(db_conn)
    anomalies = checker.check()
    ov2 = [a for a in anomalies if a.rule_id == "OV2"]
    assert len(ov2) == 1
    assert ov2[0].object_id == "obj-C"
    assert ov2[0].evidence["version_delta"] == 4


# ---------------------------------------------------------------------------
# WC1 — Wallet concentration
# ---------------------------------------------------------------------------


def _seed_chain_event(conn, event_id, sender, system_id, ts=None):
    """Insert a chain event with sender in raw_json."""
    ts = ts or int(time.time())
    raw = json.dumps({"sender": sender})
    conn.execute(
        """INSERT INTO chain_events
           (event_id, event_type, object_id, object_type,
            system_id, block_number, transaction_hash,
            timestamp, raw_json, processed)
           VALUES (?, 'SomeEvent', '', '', ?, 0, ?, ?, ?, 1)""",
        (event_id, system_id, event_id, ts, raw),
    )
    conn.commit()


def test_wc1_dominant_wallet_flagged(db_conn):
    """One wallet with >50% of 10+ events triggers WC1."""
    now = int(time.time())
    for i in range(8):
        _seed_chain_event(db_conn, f"e-dom-{i}", "0xdominant", "sys-100", now)
    _seed_chain_event(db_conn, "e-other-1", "0xother1", "sys-100", now)
    _seed_chain_event(db_conn, "e-other-2", "0xother2", "sys-100", now)

    checker = WalletConcentrationChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 1
    assert anomalies[0].rule_id == "WC1"
    assert anomalies[0].evidence["concentration_ratio"] == 0.8


def test_wc1_evenly_distributed_no_anomaly(db_conn):
    """Evenly distributed events produce no WC1."""
    now = int(time.time())
    for i in range(10):
        _seed_chain_event(db_conn, f"e-even-{i}", f"0xwallet{i}", "sys-200", now)

    checker = WalletConcentrationChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0


# ---------------------------------------------------------------------------
# CC1 — Config version change
# ---------------------------------------------------------------------------


def test_cc1_config_version_change(db_conn):
    """Two config versions for same type triggers CC1."""
    now = int(time.time())
    db_conn.execute(
        _INSERT_CONFIG,
        ("Energy", "0xconfig1", 1, '{"rate": 100}', now - 3600),
    )
    db_conn.execute(
        _INSERT_CONFIG,
        ("Energy", "0xconfig1", 2, '{"rate": 200}', now),
    )
    db_conn.commit()

    checker = ConfigChangeChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 1
    assert anomalies[0].rule_id == "CC1"
    assert anomalies[0].severity == "CRITICAL"
    assert anomalies[0].evidence["old_version"] == 1
    assert anomalies[0].evidence["new_version"] == 2


def test_cc1_single_version_no_anomaly(db_conn):
    """Single config version produces no CC1."""
    now = int(time.time())
    db_conn.execute(
        _INSERT_CONFIG,
        ("Fuel", "0xconfig2", 1, '{"burn_rate": 50}', now),
    )
    db_conn.commit()

    checker = ConfigChangeChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0


# ---------------------------------------------------------------------------
# IA1 — Inventory conservation violation
# ---------------------------------------------------------------------------


def test_ia1_negative_net_flow(db_conn):
    """More outflow than inflow triggers IA1."""
    now = int(time.time())
    db_conn.execute(
        _INSERT_LEDGER,
        ("asm-1", "item-A", "ItemDepositedEvent", 5, "ev1", "tx1", now),
    )
    db_conn.execute(
        _INSERT_LEDGER,
        ("asm-1", "item-A", "ItemWithdrawnEvent", 10, "ev2", "tx2", now),
    )
    db_conn.commit()

    checker = InventoryAuditChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 1
    assert anomalies[0].rule_id == "IA1"
    assert anomalies[0].severity == "CRITICAL"
    assert anomalies[0].evidence["net_balance"] == -5


def test_ia1_balanced_flow_no_anomaly(db_conn):
    """Balanced inflow/outflow produces no IA1."""
    now = int(time.time())
    db_conn.execute(
        _INSERT_LEDGER,
        ("asm-2", "item-B", "ItemMintedEvent", 10, "ev3", "tx3", now),
    )
    db_conn.execute(
        _INSERT_LEDGER,
        ("asm-2", "item-B", "ItemBurnedEvent", 5, "ev4", "tx4", now),
    )
    db_conn.commit()

    checker = InventoryAuditChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0


# ---------------------------------------------------------------------------
# BP1 — Bot pattern
# ---------------------------------------------------------------------------


def test_bp1_low_cv_detected(db_conn):
    """Low coefficient of variation triggers BP1."""
    now = int(time.time())
    db_conn.execute(
        _INSERT_WALLET,
        ("0xbot_wallet", 50, 60.0, 5.0, now - 3600, now, now),
    )
    db_conn.commit()

    checker = BotPatternChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 1
    assert anomalies[0].rule_id == "BP1"
    assert anomalies[0].evidence["coefficient_of_variation"] < 0.15


def test_bp1_high_cv_no_anomaly(db_conn):
    """High CV (human-like variance) produces no BP1."""
    now = int(time.time())
    db_conn.execute(
        _INSERT_WALLET,
        ("0xhuman_wallet", 15, 120.0, 80.0, now - 7200, now, now),
    )
    db_conn.commit()

    checker = BotPatternChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0


# ---------------------------------------------------------------------------
# TH1 — Tribe hopping
# ---------------------------------------------------------------------------


def test_th1_three_tribes_flagged(db_conn):
    """Character with 3+ tribe_ids in versions triggers TH1."""
    now = int(time.time())
    db_conn.execute(
        _INSERT_ENTITY,
        ("char-1", "TestPilot", "character", now),
    )
    for i, tribe in enumerate(["tribe-A", "tribe-B", "tribe-C"]):
        state = json.dumps({"tribe_id": tribe})
        db_conn.execute(
            _INSERT_OBJ_VER,
            ("char-1", i + 1, f"d{i}", state, now - (100 * (3 - i))),
        )
    db_conn.commit()

    checker = TribeHoppingChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 1
    assert anomalies[0].rule_id == "TH1"
    assert anomalies[0].evidence["tribe_count"] == 3


def test_th1_single_tribe_no_anomaly(db_conn):
    """Character staying in one tribe produces no TH1."""
    now = int(time.time())
    db_conn.execute(
        _INSERT_ENTITY,
        ("char-2", "LoyalPilot", "character", now),
    )
    for i in range(3):
        state = json.dumps({"tribe_id": "tribe-X"})
        db_conn.execute(
            _INSERT_OBJ_VER,
            ("char-2", i + 1, f"d{i}", state, now - (100 * (3 - i))),
        )
    db_conn.commit()

    checker = TribeHoppingChecker(db_conn)
    anomalies = checker.check()
    assert len(anomalies) == 0

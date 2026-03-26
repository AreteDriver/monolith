"""Tests for market manipulation checker — MM1, MM2, MM3 rules."""

import json
import sqlite3
import time

import pytest

from backend.detection.market_manipulation_checker import MarketManipulationChecker


@pytest.fixture()
def db():
    """In-memory SQLite with required tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE objects (
            object_id TEXT PRIMARY KEY,
            object_type TEXT,
            owner TEXT,
            system_id TEXT,
            current_state TEXT,
            last_seen INTEGER,
            destroyed_at INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE item_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assembly_id TEXT,
            item_type_id TEXT,
            event_type TEXT,
            quantity INTEGER,
            timestamp INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE chain_events (
            event_id TEXT,
            event_type TEXT,
            object_id TEXT,
            object_type TEXT,
            system_id TEXT,
            block_number INTEGER,
            transaction_hash TEXT,
            timestamp INTEGER,
            processed INTEGER DEFAULT 0,
            raw_json TEXT
        )"""
    )
    conn.commit()
    return conn


class TestMM1WashTrading:
    """MM1: Circular item flows between wallets."""

    def test_detects_wash_trading_same_owner(self, db):
        """Round trips between assemblies owned by the same wallet."""
        now = int(time.time())
        # Two assemblies, same owner
        db.execute(
            "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("asm-a", "smartassemblies", "wallet-1", "sys-1", "{}", now, None),
        )
        db.execute(
            "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("asm-b", "smartassemblies", "wallet-1", "sys-1", "{}", now, None),
        )

        # Round trip: withdraw from A, deposit to B (twice)
        for i in range(3):
            db.execute(
                "INSERT INTO item_ledger (assembly_id, item_type_id, "
                "event_type, quantity, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                ("asm-a", "fuel-001", "withdrawn", 100, now - 200 + i),
            )
            db.execute(
                "INSERT INTO item_ledger (assembly_id, item_type_id, "
                "event_type, quantity, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                ("asm-b", "fuel-001", "deposited", 100, now - 199 + i),
            )
        db.commit()

        checker = MarketManipulationChecker(db)
        anomalies = checker.check()

        mm1 = [a for a in anomalies if a.rule_id == "MM1"]
        assert len(mm1) >= 1
        assert mm1[0].evidence["same_owner"] is True
        assert mm1[0].evidence["confidence"] == 0.85

    def test_no_false_positive_single_transfer(self, db):
        """A single transfer should not trigger."""
        now = int(time.time())
        db.execute(
            "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("asm-a", "smartassemblies", "wallet-1", "sys-1", "{}", now, None),
        )
        db.execute(
            "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("asm-b", "smartassemblies", "wallet-2", "sys-1", "{}", now, None),
        )
        db.execute(
            "INSERT INTO item_ledger VALUES (NULL, ?, ?, ?, ?, ?)",
            ("asm-a", "fuel-001", "withdrawn", 100, now),
        )
        db.execute(
            "INSERT INTO item_ledger VALUES (NULL, ?, ?, ?, ?, ?)",
            ("asm-b", "fuel-001", "deposited", 100, now + 1),
        )
        db.commit()

        checker = MarketManipulationChecker(db)
        anomalies = checker.check()
        mm1 = [a for a in anomalies if a.rule_id == "MM1"]
        assert len(mm1) == 0


class TestMM2PriceFixing:
    """MM2: Coordinated pricing by multiple assemblies."""

    def test_detects_price_fixing(self, db):
        """3+ assemblies setting same price in same system within window."""
        now = int(time.time())
        for i in range(4):
            db.execute(
                "INSERT INTO chain_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"ev-{i}",
                    "TollSet",
                    f"asm-{i}",
                    "smartassemblies",
                    "sys-123",
                    100,
                    f"tx-{i}",
                    now - 100 + i,
                    0,
                    json.dumps({"price": 500}),
                ),
            )
        db.commit()

        checker = MarketManipulationChecker(db)
        anomalies = checker.check()
        mm2 = [a for a in anomalies if a.rule_id == "MM2"]
        assert len(mm2) >= 1
        assert mm2[0].evidence["price_value"] == 500
        assert mm2[0].evidence["assembly_count"] >= 3

    def test_no_false_positive_different_prices(self, db):
        """Different prices should not trigger."""
        now = int(time.time())
        for i in range(4):
            db.execute(
                "INSERT INTO chain_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"ev-{i}",
                    "TollSet",
                    f"asm-{i}",
                    "smartassemblies",
                    "sys-123",
                    100,
                    f"tx-{i}",
                    now - 100,
                    0,
                    json.dumps({"price": 100 * (i + 1)}),
                ),
            )
        db.commit()

        checker = MarketManipulationChecker(db)
        anomalies = checker.check()
        mm2 = [a for a in anomalies if a.rule_id == "MM2"]
        assert len(mm2) == 0


class TestMM3ArtificialScarcity:
    """MM3: Single wallet hoarding majority of an item type."""

    def test_detects_hoarding(self, db):
        """One wallet holding >60% of an item type's supply."""
        now = int(time.time())
        # Wallet-1 owns asm-a with 80 units
        db.execute(
            "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("asm-a", "smartassemblies", "wallet-1", "sys-1", "{}", now, None),
        )
        # Wallet-2 owns asm-b with 20 units
        db.execute(
            "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("asm-b", "smartassemblies", "wallet-2", "sys-1", "{}", now, None),
        )

        db.execute(
            "INSERT INTO item_ledger VALUES (NULL, ?, ?, ?, ?, ?)",
            ("asm-a", "rare-ore", "deposited", 80, now),
        )
        db.execute(
            "INSERT INTO item_ledger VALUES (NULL, ?, ?, ?, ?, ?)",
            ("asm-b", "rare-ore", "deposited", 20, now),
        )
        db.commit()

        checker = MarketManipulationChecker(db)
        anomalies = checker.check()
        mm3 = [a for a in anomalies if a.rule_id == "MM3"]
        assert len(mm3) >= 1
        assert mm3[0].evidence["market_share"] == 80.0

    def test_no_false_positive_balanced(self, db):
        """50/50 split should not trigger."""
        now = int(time.time())
        db.execute(
            "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("asm-a", "smartassemblies", "wallet-1", "sys-1", "{}", now, None),
        )
        db.execute(
            "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("asm-b", "smartassemblies", "wallet-2", "sys-1", "{}", now, None),
        )
        db.execute(
            "INSERT INTO item_ledger VALUES (NULL, ?, ?, ?, ?, ?)",
            ("asm-a", "rare-ore", "deposited", 50, now),
        )
        db.execute(
            "INSERT INTO item_ledger VALUES (NULL, ?, ?, ?, ?, ?)",
            ("asm-b", "rare-ore", "deposited", 50, now),
        )
        db.commit()

        checker = MarketManipulationChecker(db)
        anomalies = checker.check()
        mm3 = [a for a in anomalies if a.rule_id == "MM3"]
        assert len(mm3) == 0


class TestClassification:
    """Verify rule classification in anomaly_scorer."""

    def test_mm_rules_classified(self):
        from backend.detection.anomaly_scorer import classify_anomaly

        sev, cat = classify_anomaly("MM1")
        assert sev == "HIGH"
        assert cat == "BEHAVIORAL"

        sev, cat = classify_anomaly("MM2")
        assert sev == "HIGH"
        assert cat == "BEHAVIORAL"

        sev, cat = classify_anomaly("MM3")
        assert sev == "MEDIUM"
        assert cat == "BEHAVIORAL"

    def test_mm_display_names(self):
        from backend.detection.anomaly_scorer import display_name

        assert display_name("MM1") == "Wash Cycle"
        assert display_name("MM2") == "Price Cartel"
        assert display_name("MM3") == "Supply Corner"


class TestRegistration:
    """Verify checker is registered in the detection engine."""

    def test_registered_in_engine(self, db):
        from backend.detection.engine import DetectionEngine

        engine = DetectionEngine(db)
        checker_names = [c.name for c in engine._checkers]
        assert "market_manipulation_checker" in checker_names

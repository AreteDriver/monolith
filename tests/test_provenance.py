"""Tests for provenance chains — creation, serialization, storage, parsing, and population.

Validates the full lifecycle of ProvenanceEntry from dataclass creation through
DB storage and API retrieval, plus checker-level population for C1, A2, and S4 rules.
"""

import json
import time

import pytest

from backend.db.database import init_db
from backend.detection.assembly_checker import AssemblyChecker
from backend.detection.base import Anomaly, ProvenanceEntry
from backend.detection.continuity_checker import ContinuityChecker
from backend.detection.engine import _serialize_provenance
from backend.detection.sequence_checker import SequenceChecker
from backend.warden.warden import Warden


@pytest.fixture
def db_conn():
    """In-memory SQLite database with full schema."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provenance_entry(**overrides):
    """Create a ProvenanceEntry with sensible defaults."""
    defaults = {
        "source_type": "chain_event",
        "source_id": "tx-abc123",
        "timestamp": int(time.time()),
        "derivation": "C1: orphan event detected",
    }
    defaults.update(overrides)
    return ProvenanceEntry(**defaults)


def _insert_chain_event(
    conn,
    event_id,
    object_id="obj-001",
    event_type="test",
    ts=None,
    block_number=100,
    tx_hash=None,
    raw_json=None,
):
    """Helper to insert a chain event."""
    conn.execute(
        "INSERT INTO chain_events (event_id, event_type, object_id, block_number, "
        "transaction_hash, timestamp, processed, raw_json) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
        (
            event_id,
            event_type,
            object_id,
            block_number,
            tx_hash or f"tx-{event_id}",
            ts or int(time.time()),
            raw_json,
        ),
    )
    conn.commit()


def _insert_object(conn, object_id, obj_type="smartassemblies", state=None, **kwargs):
    """Helper to insert a tracked object."""
    state = state or {}
    conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, system_id, "
        "last_seen, created_at, destroyed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            object_id,
            obj_type,
            json.dumps(state),
            kwargs.get("system_id", ""),
            kwargs.get("last_seen", int(time.time())),
            kwargs.get("created_at", int(time.time())),
            kwargs.get("destroyed_at"),
        ),
    )
    conn.commit()


def _seed_anomaly(
    conn, anomaly_id, rule_id="C1", object_id="0xabc", status="UNVERIFIED", provenance_json=None
):
    """Insert a test anomaly with optional provenance."""
    conn.execute(
        "INSERT INTO anomalies "
        "(anomaly_id, anomaly_type, severity, category, detector, "
        "rule_id, object_id, system_id, detected_at, evidence_json, "
        "provenance_json, status) "
        "VALUES (?, 'TEST', 'CRITICAL', 'DATA_INTEGRITY', 'test', "
        "?, ?, 'sys-1', ?, '{}', ?, ?)",
        (anomaly_id, rule_id, object_id, int(time.time()), provenance_json, status),
    )
    conn.commit()


# ===========================================================================
# 1. ProvenanceEntry creation and serialization
# ===========================================================================


class TestProvenanceEntryCreation:
    """ProvenanceEntry dataclass and Anomaly.to_dict() provenance output."""

    def test_entry_fields(self):
        """ProvenanceEntry stores all four required fields."""
        ts = int(time.time())
        entry = ProvenanceEntry(
            source_type="chain_event",
            source_id="tx-deadbeef",
            timestamp=ts,
            derivation="C1: orphan detected",
        )
        assert entry.source_type == "chain_event"
        assert entry.source_id == "tx-deadbeef"
        assert entry.timestamp == ts
        assert entry.derivation == "C1: orphan detected"

    def test_anomaly_to_dict_includes_provenance(self):
        """Anomaly.to_dict() serializes provenance as list of dicts."""
        entry = _make_provenance_entry(source_id="tx-001")
        anomaly = Anomaly(
            anomaly_type="ORPHAN_OBJECT",
            rule_id="C1",
            detector="continuity_checker",
            object_id="obj-123",
            provenance=[entry],
        )
        d = anomaly.to_dict()
        assert "provenance" in d
        assert len(d["provenance"]) == 1
        assert d["provenance"][0]["source_type"] == "chain_event"
        assert d["provenance"][0]["source_id"] == "tx-001"

    def test_anomaly_to_dict_empty_provenance(self):
        """Anomaly with no provenance returns empty list in to_dict()."""
        anomaly = Anomaly(
            anomaly_type="TEST",
            rule_id="T1",
            detector="test",
            object_id="obj-1",
        )
        d = anomaly.to_dict()
        assert d["provenance"] == []

    def test_anomaly_to_dict_multiple_entries(self):
        """Anomaly with multiple provenance entries serializes all."""
        entries = [
            _make_provenance_entry(source_id="tx-a", derivation="step 1"),
            _make_provenance_entry(source_id="tx-b", derivation="step 2"),
            _make_provenance_entry(source_id="tx-c", derivation="step 3"),
        ]
        anomaly = Anomaly(
            anomaly_type="TEST",
            rule_id="T1",
            detector="test",
            object_id="obj-1",
            provenance=entries,
        )
        d = anomaly.to_dict()
        assert len(d["provenance"]) == 3
        assert [p["source_id"] for p in d["provenance"]] == ["tx-a", "tx-b", "tx-c"]


# ===========================================================================
# 2. Engine serialization (_serialize_provenance)
# ===========================================================================


class TestEngineSerializeProvenance:
    """Engine helper _serialize_provenance() behavior."""

    def test_returns_none_for_empty(self):
        """Empty provenance returns None (stored as NULL in DB)."""
        anomaly = Anomaly(
            anomaly_type="TEST",
            rule_id="T1",
            detector="test",
            object_id="obj-1",
        )
        assert _serialize_provenance(anomaly) is None

    def test_returns_valid_json(self):
        """Populated provenance returns parseable JSON string."""
        entry = _make_provenance_entry()
        anomaly = Anomaly(
            anomaly_type="TEST",
            rule_id="T1",
            detector="test",
            object_id="obj-1",
            provenance=[entry],
        )
        result = _serialize_provenance(anomaly)
        assert result is not None
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 1

    def test_round_trip_structure(self):
        """Serialize then parse preserves all fields."""
        ts = 1700000000
        entry = ProvenanceEntry(
            source_type="sui_rpc",
            source_id="checkpoint:99999",
            timestamp=ts,
            derivation="Warden verified: C1 on 0xabc",
        )
        anomaly = Anomaly(
            anomaly_type="TEST",
            rule_id="T1",
            detector="test",
            object_id="obj-1",
            provenance=[entry],
        )
        serialized = _serialize_provenance(anomaly)
        parsed = json.loads(serialized)
        p = parsed[0]
        assert p["source_type"] == "sui_rpc"
        assert p["source_id"] == "checkpoint:99999"
        assert p["timestamp"] == ts
        assert p["derivation"] == "Warden verified: C1 on 0xabc"

    def test_multiple_entries_round_trip(self):
        """Multiple provenance entries survive serialize/parse."""
        entries = [
            _make_provenance_entry(source_id=f"src-{i}", derivation=f"step {i}") for i in range(5)
        ]
        anomaly = Anomaly(
            anomaly_type="TEST",
            rule_id="T1",
            detector="test",
            object_id="obj-1",
            provenance=entries,
        )
        parsed = json.loads(_serialize_provenance(anomaly))
        assert len(parsed) == 5
        assert parsed[2]["source_id"] == "src-2"


# ===========================================================================
# 3. DB storage and retrieval
# ===========================================================================


class TestDBStorage:
    """Database schema supports provenance_json column and round-trip."""

    def test_provenance_json_column_exists(self, db_conn):
        """init_db() creates the provenance_json column on anomalies."""
        cursor = db_conn.execute("PRAGMA table_info(anomalies)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "provenance_json" in columns

    def test_store_anomaly_with_provenance(self, db_conn):
        """Engine _store_anomaly persists provenance_json."""
        from backend.detection.engine import DetectionEngine

        engine = DetectionEngine(db_conn)

        entry = _make_provenance_entry(source_id="tx-store-test")
        anomaly = Anomaly(
            anomaly_type="STORE_TEST",
            rule_id="ST1",
            detector="test",
            object_id="obj-store",
            provenance=[entry],
        )
        stored = engine._store_anomaly(anomaly)
        db_conn.commit()
        assert stored is True

        row = db_conn.execute(
            "SELECT provenance_json FROM anomalies WHERE anomaly_id = ?",
            (anomaly.anomaly_id,),
        ).fetchone()
        assert row is not None
        assert row["provenance_json"] is not None
        parsed = json.loads(row["provenance_json"])
        assert len(parsed) == 1
        assert parsed[0]["source_id"] == "tx-store-test"

    def test_store_anomaly_without_provenance(self, db_conn):
        """Engine stores NULL provenance_json when provenance is empty."""
        from backend.detection.engine import DetectionEngine

        engine = DetectionEngine(db_conn)

        anomaly = Anomaly(
            anomaly_type="EMPTY_PROV",
            rule_id="EP1",
            detector="test",
            object_id="obj-empty",
        )
        engine._store_anomaly(anomaly)
        db_conn.commit()

        row = db_conn.execute(
            "SELECT provenance_json FROM anomalies WHERE anomaly_id = ?",
            (anomaly.anomaly_id,),
        ).fetchone()
        assert row["provenance_json"] is None


# ===========================================================================
# 4. API parsing (_row_to_dict)
# ===========================================================================


class TestAPIParsing:
    """API layer _row_to_dict parses provenance_json correctly."""

    def test_parses_provenance_json(self, db_conn):
        """_row_to_dict extracts provenance list from provenance_json."""
        from backend.api.anomalies import _row_to_dict

        prov = json.dumps(
            [
                {
                    "source_type": "chain_event",
                    "source_id": "tx-parse",
                    "timestamp": 1700000000,
                    "derivation": "test derivation",
                }
            ]
        )
        _seed_anomaly(db_conn, "MNLT-PARSE-001", provenance_json=prov)

        row = db_conn.execute(
            "SELECT * FROM anomalies WHERE anomaly_id = 'MNLT-PARSE-001'"
        ).fetchone()
        d = _row_to_dict(row)
        assert "provenance" in d
        assert len(d["provenance"]) == 1
        assert d["provenance"][0]["source_id"] == "tx-parse"

    def test_null_provenance_returns_empty_list(self, db_conn):
        """_row_to_dict returns [] when provenance_json is NULL."""
        from backend.api.anomalies import _row_to_dict

        _seed_anomaly(db_conn, "MNLT-NULL-001", provenance_json=None)

        row = db_conn.execute(
            "SELECT * FROM anomalies WHERE anomaly_id = 'MNLT-NULL-001'"
        ).fetchone()
        d = _row_to_dict(row)
        assert d["provenance"] == []

    def test_empty_string_provenance_returns_empty_list(self, db_conn):
        """_row_to_dict returns [] when provenance_json is empty string."""
        from backend.api.anomalies import _row_to_dict

        _seed_anomaly(db_conn, "MNLT-EMPTY-001", provenance_json="")

        row = db_conn.execute(
            "SELECT * FROM anomalies WHERE anomaly_id = 'MNLT-EMPTY-001'"
        ).fetchone()
        d = _row_to_dict(row)
        assert d["provenance"] == []

    def test_invalid_json_provenance_returns_empty_list(self, db_conn):
        """_row_to_dict returns [] for malformed provenance_json."""
        from backend.api.anomalies import _row_to_dict

        _seed_anomaly(db_conn, "MNLT-BAD-001", provenance_json="{not valid json")

        row = db_conn.execute(
            "SELECT * FROM anomalies WHERE anomaly_id = 'MNLT-BAD-001'"
        ).fetchone()
        d = _row_to_dict(row)
        assert d["provenance"] == []


# ===========================================================================
# 5. Checker provenance population (C1, A2, S4)
# ===========================================================================


class TestCheckerProvenancePopulation:
    """Checkers attach correct provenance entries to detected anomalies."""

    def test_c1_orphan_has_chain_event_provenance(self, db_conn):
        """ContinuityChecker C1 attaches provenance with source_type=chain_event."""
        _insert_chain_event(db_conn, "evt-prov-c1", object_id="orphan-prov-obj")
        checker = ContinuityChecker(db_conn)
        anomalies = checker.check()

        orphans = [a for a in anomalies if a.anomaly_type == "ORPHAN_OBJECT"]
        assert len(orphans) >= 1

        prov = orphans[0].provenance
        assert len(prov) >= 1
        assert prov[0].source_type == "chain_event"
        assert prov[0].source_id == "tx-evt-prov-c1"
        assert "C1" in prov[0].derivation

    def test_a2_free_gate_jump_has_provenance(self, db_conn):
        """AssemblyChecker A2 attaches provenance for JumpEvent without FuelEvent."""
        now = int(time.time())
        gate_id = "gate-prov-001"

        # Insert a JumpEvent with no corresponding FuelEvent
        _insert_chain_event(
            db_conn,
            "evt-jump-prov",
            object_id=gate_id,
            event_type="0x123::gate::JumpEvent",
            ts=now,
            tx_hash="tx-jump-prov",
        )

        checker = AssemblyChecker(db_conn)
        anomalies = checker.check()

        free_jumps = [a for a in anomalies if a.anomaly_type == "FREE_GATE_JUMP"]
        assert len(free_jumps) >= 1

        prov = free_jumps[0].provenance
        assert len(prov) >= 1
        assert prov[0].source_type == "chain_event"
        assert prov[0].source_id == "evt-jump-prov"
        assert "A2" in prov[0].derivation

    def test_s4_block_gap_has_provenance(self, db_conn):
        """SequenceChecker S4 attaches provenance for block processing gap."""
        now = int(time.time())

        # Insert events with a >100 block gap
        _insert_chain_event(
            db_conn,
            "evt-blk-1",
            object_id="obj-blk",
            block_number=1000,
            ts=now - 100,
        )
        _insert_chain_event(
            db_conn,
            "evt-blk-2",
            object_id="obj-blk",
            block_number=1200,
            ts=now,
        )

        checker = SequenceChecker(db_conn)
        anomalies = checker.check()

        gaps = [a for a in anomalies if a.anomaly_type == "BLOCK_PROCESSING_GAP"]
        assert len(gaps) >= 1

        prov = gaps[0].provenance
        assert len(prov) >= 1
        assert prov[0].source_type == "chain_event"
        assert "S4" in prov[0].derivation
        assert "1000" in prov[0].source_id or "1200" in prov[0].source_id

    def test_c1_provenance_timestamp_matches_event(self, db_conn):
        """C1 provenance timestamp matches the chain event timestamp."""
        ts = int(time.time()) - 300
        _insert_chain_event(db_conn, "evt-ts-c1", object_id="orphan-ts-obj", ts=ts)
        checker = ContinuityChecker(db_conn)
        anomalies = checker.check()

        orphans = [a for a in anomalies if a.anomaly_type == "ORPHAN_OBJECT"]
        assert len(orphans) >= 1
        assert orphans[0].provenance[0].timestamp == ts


# ===========================================================================
# 6. Warden _append_provenance
# ===========================================================================


class TestWardenAppendProvenance:
    """Warden._append_provenance() updates provenance_json in DB."""

    def test_append_to_null_provenance(self, db_conn):
        """Appending to anomaly with NULL provenance_json creates new list."""
        _seed_anomaly(db_conn, "MNLT-WARDEN-001", provenance_json=None)

        warden = Warden(db_conn, "https://fake-rpc.example.com")
        warden._append_provenance(
            anomaly_id="MNLT-WARDEN-001",
            source_type="sui_rpc",
            source_id="checkpoint:12345",
            derivation="Warden verified: C1 on 0xabc",
        )

        row = db_conn.execute(
            "SELECT provenance_json FROM anomalies WHERE anomaly_id = 'MNLT-WARDEN-001'"
        ).fetchone()
        parsed = json.loads(row["provenance_json"])
        assert len(parsed) == 1
        assert parsed[0]["source_type"] == "sui_rpc"
        assert parsed[0]["source_id"] == "checkpoint:12345"
        assert parsed[0]["derivation"] == "Warden verified: C1 on 0xabc"

    def test_append_to_existing_provenance(self, db_conn):
        """Appending to anomaly with existing provenance extends the list."""
        existing = json.dumps(
            [
                {
                    "source_type": "chain_event",
                    "source_id": "tx-original",
                    "timestamp": 1700000000,
                    "derivation": "C1: original detection",
                }
            ]
        )
        _seed_anomaly(db_conn, "MNLT-WARDEN-002", provenance_json=existing)

        warden = Warden(db_conn, "https://fake-rpc.example.com")
        warden._append_provenance(
            anomaly_id="MNLT-WARDEN-002",
            source_type="sui_rpc",
            source_id="checkpoint:99999",
            derivation="Warden verified",
        )

        row = db_conn.execute(
            "SELECT provenance_json FROM anomalies WHERE anomaly_id = 'MNLT-WARDEN-002'"
        ).fetchone()
        parsed = json.loads(row["provenance_json"])
        assert len(parsed) == 2
        assert parsed[0]["source_id"] == "tx-original"
        assert parsed[1]["source_type"] == "sui_rpc"

    def test_append_sets_timestamp(self, db_conn):
        """Appended provenance entry gets a current timestamp."""
        _seed_anomaly(db_conn, "MNLT-WARDEN-003", provenance_json=None)

        before = int(time.time())
        warden = Warden(db_conn, "https://fake-rpc.example.com")
        warden._append_provenance(
            anomaly_id="MNLT-WARDEN-003",
            source_type="sui_rpc",
            source_id="checkpoint:55555",
            derivation="Warden dismissed",
        )
        after = int(time.time())

        row = db_conn.execute(
            "SELECT provenance_json FROM anomalies WHERE anomaly_id = 'MNLT-WARDEN-003'"
        ).fetchone()
        parsed = json.loads(row["provenance_json"])
        ts = parsed[0]["timestamp"]
        assert before <= ts <= after

    def test_append_to_nonexistent_anomaly_is_noop(self, db_conn):
        """Appending provenance to missing anomaly does not raise."""
        warden = Warden(db_conn, "https://fake-rpc.example.com")
        # Should not raise
        warden._append_provenance(
            anomaly_id="MNLT-NONEXISTENT",
            source_type="sui_rpc",
            source_id="checkpoint:0",
            derivation="should be ignored",
        )

    def test_append_to_corrupted_json_resets(self, db_conn):
        """Appending to anomaly with corrupt provenance_json starts fresh list."""
        _seed_anomaly(db_conn, "MNLT-WARDEN-004", provenance_json="not valid json")

        warden = Warden(db_conn, "https://fake-rpc.example.com")
        warden._append_provenance(
            anomaly_id="MNLT-WARDEN-004",
            source_type="sui_rpc",
            source_id="checkpoint:77777",
            derivation="Warden recovered",
        )

        row = db_conn.execute(
            "SELECT provenance_json FROM anomalies WHERE anomaly_id = 'MNLT-WARDEN-004'"
        ).fetchone()
        parsed = json.loads(row["provenance_json"])
        assert len(parsed) == 1
        assert parsed[0]["derivation"] == "Warden recovered"

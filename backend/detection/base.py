"""Base classes and types for detection checkers."""

import itertools
import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.detection.anomaly_scorer import classify_anomaly

_anomaly_counter = itertools.count(1)


@dataclass
class ProvenanceEntry:
    """Single link in an anomaly's provenance chain.

    Traces exactly which data source led to this detection and how.
    """

    source_type: str  # chain_event | world_state | state_transition | sui_rpc | detection_rule
    source_id: str  # event_id, snapshot_id, tx_hash, or rule reference
    timestamp: int  # when the source data was produced
    derivation: str  # human-readable explanation of how this source contributed


@dataclass
class Anomaly:
    """Structured anomaly detected by a checker rule."""

    anomaly_type: str
    rule_id: str
    detector: str
    object_id: str
    system_id: str = ""
    evidence: dict = field(default_factory=dict)
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    severity: str = ""
    category: str = ""
    anomaly_id: str = ""
    detected_at: int = 0

    def __post_init__(self):
        if not self.severity or not self.category:
            self.severity, self.category = classify_anomaly(self.rule_id)
        if not self.detected_at:
            self.detected_at = int(time.time())
        if not self.anomaly_id:
            date_str = datetime.now(tz=UTC).strftime("%Y%m%d")
            seq = next(_anomaly_counter)
            self.anomaly_id = f"MNLT-{date_str}-{seq:04d}"

    def to_dict(self) -> dict:
        """Convert to dict for storage."""
        return {
            "anomaly_id": self.anomaly_id,
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "category": self.category,
            "detector": self.detector,
            "rule_id": self.rule_id,
            "object_id": self.object_id,
            "system_id": self.system_id,
            "detected_at": self.detected_at,
            "evidence": self.evidence,
            "provenance": [
                {
                    "source_type": p.source_type,
                    "source_id": p.source_id,
                    "timestamp": p.timestamp,
                    "derivation": p.derivation,
                }
                for p in self.provenance
            ],
        }


class BaseChecker:
    """Base class for detection checkers.

    Subclasses implement check() which returns a list of Anomaly objects.
    Rules are pure functions: (db state) -> anomalies.
    """

    name: str = "base"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def check(self) -> list[Anomaly]:
        """Run all rules. Override in subclasses."""
        raise NotImplementedError

    def _get_recent_events(self, hours: int = 1) -> list[dict]:
        """Get chain events from the last N hours (excludes raw_json for memory)."""
        cutoff = int(time.time()) - (hours * 3600)
        rows = self.conn.execute(
            "SELECT event_id, event_type, object_id, object_type, system_id, "
            "block_number, transaction_hash, timestamp, processed "
            "FROM chain_events WHERE timestamp >= ? ORDER BY timestamp ASC",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _get_object(self, object_id: str) -> dict | None:
        """Get a tracked object by ID."""
        row = self.conn.execute(
            "SELECT * FROM objects WHERE object_id = ?", (object_id,)
        ).fetchone()
        return dict(row) if row else None

    def _get_latest_snapshots(self, object_id: str, count: int = 2) -> list[dict]:
        """Get the N most recent snapshots for an object."""
        rows = self.conn.execute(
            "SELECT * FROM world_states WHERE object_id = ? ORDER BY snapshot_time DESC LIMIT ?",
            (object_id, count),
        ).fetchall()
        return [dict(r) for r in rows]

    def _parse_state(self, snapshot: dict) -> dict:
        """Parse state_data JSON from a snapshot."""
        raw = snapshot.get("state_data", "{}")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
        return raw

    def _get_transitions(self, object_id: str, since: int = 0) -> list[dict]:
        """Get state transitions for an object since a timestamp."""
        rows = self.conn.execute(
            "SELECT * FROM state_transitions WHERE object_id = ? AND timestamp >= ? "
            "ORDER BY timestamp ASC",
            (object_id, since),
        ).fetchall()
        return [dict(r) for r in rows]

    def _events_for_object(self, object_id: str, since: int = 0) -> list[dict]:
        """Get chain events referencing an object since a timestamp (excludes raw_json)."""
        rows = self.conn.execute(
            "SELECT event_id, event_type, object_id, object_type, system_id, "
            "block_number, transaction_hash, timestamp, processed "
            "FROM chain_events WHERE object_id = ? AND timestamp >= ? "
            "ORDER BY timestamp ASC",
            (object_id, since),
        ).fetchall()
        return [dict(r) for r in rows]

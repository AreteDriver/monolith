"""Continuity checker — detects state gaps, orphan objects, and resurrections.

Rules:
  C1 — Orphan object: chain event references object with no creation record
  C2 — Resurrection: destroyed object shows post-destruction activity
  C3 — State gap: object jumped states without intermediate transition
  C4 — Stuck object: pending state unresolved for >10 minutes
"""

import json
import logging
import time

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)

# Valid state transitions for smart assemblies
VALID_TRANSITIONS: dict[str, set[str]] = {
    "unanchored": {"anchored", "online"},
    "anchored": {"online", "offline", "unanchored"},
    "online": {"offline", "anchored", "unanchored"},
    "offline": {"online", "anchored", "unanchored"},
}

# States considered "destroyed" — object should not appear again
DESTROYED_STATES: set[str] = {"destroyed", "deleted"}

# How long before a pending/transitional state is considered stuck (seconds)
STUCK_THRESHOLD = 600  # 10 minutes


class ContinuityChecker(BaseChecker):
    """Checks object lifecycle continuity across chain events and API state."""

    name = "continuity_checker"

    def check(self) -> list[Anomaly]:
        """Run all continuity rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_c1_orphan_events())
        anomalies.extend(self._check_c2_resurrection())
        anomalies.extend(self._check_c3_state_gaps())
        anomalies.extend(self._check_c4_stuck_objects())
        return anomalies

    def _check_c1_orphan_events(self) -> list[Anomaly]:
        """C1: Chain event references an object_id not in the objects table.

        This means the chain has activity for an object we never saw created.
        Could indicate a missed creation event or indexer gap.
        """
        rows = self.conn.execute(
            """SELECT DISTINCT ce.object_id, ce.event_type, ce.transaction_hash,
                      ce.block_number, ce.timestamp, ce.system_id
               FROM chain_events ce
               LEFT JOIN objects o ON ce.object_id = o.object_id
               WHERE o.object_id IS NULL
                 AND ce.object_id != ''
                 AND ce.processed = 0
               LIMIT 100"""
        ).fetchall()

        anomalies = []
        seen: set[str] = set()
        for row in rows:
            obj_id = row["object_id"]
            if obj_id in seen:
                continue
            seen.add(obj_id)

            anomalies.append(
                Anomaly(
                    anomaly_type="ORPHAN_OBJECT",
                    rule_id="C1",
                    detector=self.name,
                    object_id=obj_id,
                    system_id=row["system_id"] or "",
                    evidence={
                        "event_type": row["event_type"],
                        "transaction_hash": row["transaction_hash"],
                        "block_number": row["block_number"],
                        "timestamp": row["timestamp"],
                        "description": (
                            "Ghost signal — chain event references an object "
                            "with no birth record in our ledgers"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="chain_event",
                            source_id=row["transaction_hash"],
                            timestamp=row["timestamp"],
                            derivation=(
                                f"C1: {row['event_type']} refs"
                                f" {obj_id[:16]} not in objects"
                            ),
                        )
                    ],
                )
            )
        return anomalies

    def _check_c2_resurrection(self) -> list[Anomaly]:
        """C2: Object marked destroyed has subsequent activity.

        An object with destroyed_at set should never appear in new events.
        If it does, something is fundamentally wrong with state management.
        """
        rows = self.conn.execute(
            """SELECT o.object_id, o.destroyed_at, o.object_type, o.system_id,
                      ce.event_type, ce.transaction_hash, ce.timestamp as event_time
               FROM objects o
               JOIN chain_events ce ON o.object_id = ce.object_id
               WHERE o.destroyed_at IS NOT NULL
                 AND o.destroyed_at > 0
                 AND ce.timestamp > o.destroyed_at
               LIMIT 50"""
        ).fetchall()

        anomalies = []
        seen: set[str] = set()
        for row in rows:
            obj_id = row["object_id"]
            if obj_id in seen:
                continue
            seen.add(obj_id)

            anomalies.append(
                Anomaly(
                    anomaly_type="RESURRECTION",
                    rule_id="C2",
                    detector=self.name,
                    object_id=obj_id,
                    system_id=row["system_id"] or "",
                    evidence={
                        "destroyed_at": row["destroyed_at"],
                        "post_destruction_event": {
                            "event_type": row["event_type"],
                            "transaction_hash": row["transaction_hash"],
                            "timestamp": row["event_time"],
                        },
                        "description": (
                            f"Wreckage is transmitting — destroyed at "
                            f"{row['destroyed_at']} but chain picked up "
                            f"new activity at {row['event_time']}"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="chain_event",
                            source_id=f"destroyed:{obj_id}",
                            timestamp=row["destroyed_at"],
                            derivation=f"C2: object destroyed at {row['destroyed_at']}",
                        ),
                        ProvenanceEntry(
                            source_type="chain_event",
                            source_id=row["transaction_hash"],
                            timestamp=row["event_time"],
                            derivation=(
                                f"C2: post-destruction"
                                f" {row['event_type']}"
                                f" at {row['event_time']}"
                            ),
                        ),
                    ],
                )
            )
        return anomalies

    def _check_c3_state_gaps(self) -> list[Anomaly]:
        """C3: Object jumped between states without valid transition.

        Compares consecutive snapshots. If state changed and the transition
        is not in VALID_TRANSITIONS, flag it.
        """
        # Get objects with at least 2 snapshots in the last hour
        cutoff = int(time.time()) - 3600
        objects_with_snapshots = self.conn.execute(
            """SELECT DISTINCT object_id FROM world_states
               WHERE snapshot_time >= ? AND object_type = 'smartassemblies'""",
            (cutoff,),
        ).fetchall()

        anomalies = []
        for row in objects_with_snapshots:
            obj_id = row["object_id"]
            snapshots = self._get_latest_snapshots(obj_id, count=2)
            if len(snapshots) < 2:
                continue

            new_state_data = self._parse_state(snapshots[0])
            old_state_data = self._parse_state(snapshots[1])

            new_state = new_state_data.get("state", "")
            old_state = old_state_data.get("state", "")

            if not new_state or not old_state or new_state == old_state:
                continue

            # Check if this is a valid transition
            valid_targets = VALID_TRANSITIONS.get(old_state, set())
            if new_state not in valid_targets and valid_targets:
                system_id = str(
                    new_state_data.get("solarSystem", {}).get("id", "")
                    if isinstance(new_state_data.get("solarSystem"), dict)
                    else ""
                )
                anomalies.append(
                    Anomaly(
                        anomaly_type="STATE_GAP",
                        rule_id="C3",
                        detector=self.name,
                        object_id=obj_id,
                        system_id=system_id,
                        evidence={
                            "from_state": old_state,
                            "to_state": new_state,
                            "valid_transitions": sorted(valid_targets),
                            "snapshot_old_time": snapshots[1]["snapshot_time"],
                            "snapshot_new_time": snapshots[0]["snapshot_time"],
                            "description": (
                                f"Missing trajectory — jumped from "
                                f"'{old_state}' to '{new_state}' with no "
                                f"valid flight path (expected: "
                                f"{sorted(valid_targets)})"
                            ),
                        },
                        provenance=[
                            ProvenanceEntry(
                                source_type="world_state",
                                source_id=f"snapshot:{obj_id}:{snapshots[1]['snapshot_time']}",
                                timestamp=snapshots[1]["snapshot_time"],
                                derivation=f"C3: old snapshot shows state '{old_state}'",
                            ),
                            ProvenanceEntry(
                                source_type="world_state",
                                source_id=f"snapshot:{obj_id}:{snapshots[0]['snapshot_time']}",
                                timestamp=snapshots[0]["snapshot_time"],
                                derivation=(
                                    f"C3: new state '{new_state}'"
                                    ", invalid transition"
                                ),
                            ),
                        ],
                    )
                )
        return anomalies

    def _check_c4_stuck_objects(self) -> list[Anomaly]:
        """C4: Object in transitional state for too long.

        Assembly states like 'anchored' with no follow-up within threshold
        may indicate a stuck transaction or failed state change.
        """
        now = int(time.time())
        threshold_time = now - STUCK_THRESHOLD

        # Find objects whose last snapshot is old and in a transitional state
        rows = self.conn.execute(
            """SELECT o.object_id, o.current_state, o.system_id, o.last_seen
               FROM objects o
               WHERE o.object_type = 'smartassemblies'
                 AND o.last_seen < ?
                 AND o.last_seen > 0""",
            (threshold_time,),
        ).fetchall()

        anomalies = []
        for row in rows:
            state_data = {}
            try:
                state_data = json.loads(row["current_state"] or "{}")
            except json.JSONDecodeError:
                continue

            state = state_data.get("state", "")
            # Only flag assemblies that appear to be mid-transition
            if state not in ("anchored",):
                continue

            # Check if there are recent events that might resolve it
            events = self._events_for_object(row["object_id"], since=threshold_time)
            if events:
                continue  # activity exists, not stuck

            anomalies.append(
                Anomaly(
                    anomaly_type="STUCK_OBJECT",
                    rule_id="C4",
                    detector=self.name,
                    object_id=row["object_id"],
                    system_id=row["system_id"] or "",
                    evidence={
                        "current_state": state,
                        "last_seen": row["last_seen"],
                        "stuck_duration_seconds": now - row["last_seen"],
                        "threshold_seconds": STUCK_THRESHOLD,
                        "description": (
                            f"Dead drift — assembly stuck in '{state}' "
                            f"for {now - row['last_seen']}s, no signs of life"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"object:{row['object_id']}",
                            timestamp=row["last_seen"],
                            derivation=(
                                f"C4: stuck in '{state}'"
                                f" since {row['last_seen']},"
                                f" no events {now - row['last_seen']}s"
                            ),
                        )
                    ],
                )
            )
        return anomalies

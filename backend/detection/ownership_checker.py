"""Ownership checker — detects OwnerCap transfer and delegation patterns.

Rules:
  OC1 — OwnerCap Transfer: OwnerCap object transferred to a new address,
         indicating delegation, corp structure change, or suspicious handoff.
         Note: SSU Owner field is recorded separately — original owner retains
         inventory access even if OwnerCap moves (confirmed by Cantabar).
"""

import contextlib
import json
import logging
import time

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)

# How far back to scan for transfer events (seconds)
LOOKBACK_SECONDS = 24 * 3600

# Event types that indicate OwnerCap movement
OWNERCAP_EVENT_TYPES = frozenset(
    {
        "TransferObject",
        "OwnerCapTransferred",
        "TransferEvent",
    }
)


class OwnershipChecker(BaseChecker):
    """Detects OwnerCap transfers and ownership delegation patterns."""

    name = "ownership_checker"

    def check(self) -> list[Anomaly]:
        """Run all ownership rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_oc1_ownercap_transfer())
        return anomalies

    def _check_oc1_ownercap_transfer(self) -> list[Anomaly]:
        """OC1: Detect OwnerCap object transfers in chain events.

        Scans for events where an OwnerCap-typed object changes hands.
        These are valid actions but unusual — signals delegation, corp
        restructuring, or potential account compromise.
        """
        since = int(time.time()) - LOOKBACK_SECONDS
        anomalies = []

        # Strategy 1: Look for transfer events on OwnerCap objects
        rows = self.conn.execute(
            """SELECT * FROM chain_events
               WHERE timestamp >= ?
               AND (
                   event_type IN ('TransferObject', 'OwnerCapTransferred', 'TransferEvent')
                   OR raw_json LIKE '%OwnerCap%'
                   OR raw_json LIKE '%ownerCap%'
               )
               ORDER BY timestamp ASC""",
            (since,),
        ).fetchall()

        for row in rows:
            event = dict(row)
            raw = event.get("raw_json", "{}")
            parsed = {}
            if isinstance(raw, str):
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(raw)
            elif isinstance(raw, dict):
                parsed = raw

            # Check if this event involves an OwnerCap
            if not self._involves_ownercap(event, parsed):
                continue

            parsed_json = parsed.get("parsedJson", parsed)
            from_addr = self._extract_address(parsed_json, "sender", "from", "owner")
            to_addr = self._extract_address(parsed_json, "recipient", "to", "newOwner")
            object_id = event.get("object_id", parsed_json.get("objectId", "unknown"))

            anomalies.append(
                Anomaly(
                    anomaly_type="OWNERCAP_TRANSFER",
                    rule_id="OC1",
                    detector=self.name,
                    object_id=object_id,
                    evidence={
                        "event_type": event.get("event_type", ""),
                        "from_address": from_addr,
                        "to_address": to_addr,
                        "transaction_hash": event.get("transaction_hash", ""),
                        "timestamp": event.get("timestamp", 0),
                        "description": (
                            f"Title deed transfer — OwnerCap changed hands"
                            f"{' from ' + from_addr[:16] + '...' if from_addr else ''}"
                            f"{' to ' + to_addr[:16] + '...' if to_addr else ''}"
                            f". Delegation or hostile takeover"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="chain_event",
                            source_id=event.get("transaction_hash", ""),
                            timestamp=event.get("timestamp", 0),
                            derivation=(
                                f"OC1: {event.get('event_type', '')} on OwnerCap {object_id[:16]}"
                            ),
                        )
                    ],
                )
            )

        # Strategy 2: Detect ownership divergence between snapshots
        anomalies.extend(self._check_ownership_divergence(since))

        return anomalies

    def _check_ownership_divergence(self, since: int) -> list[Anomaly]:
        """Detect objects where owner changed between consecutive snapshots.

        Complements A5 (unexplained ownership change) by specifically flagging
        ownership changes that DO have transfer events — these are the
        deliberate delegations we want to track.
        """
        anomalies = []

        rows = self.conn.execute(
            """SELECT DISTINCT ws1.object_id, ws1.state_data AS old_state,
                      ws2.state_data AS new_state,
                      ws1.snapshot_time AS old_time,
                      ws2.snapshot_time AS new_time
               FROM world_states ws1
               JOIN world_states ws2
                 ON ws1.object_id = ws2.object_id
                 AND ws2.snapshot_time > ws1.snapshot_time
               WHERE ws2.snapshot_time >= ?
               AND ws1.snapshot_time = (
                   SELECT MAX(snapshot_time) FROM world_states
                   WHERE object_id = ws1.object_id
                   AND snapshot_time < ws2.snapshot_time
               )
               LIMIT 100""",
            (since,),
        ).fetchall()

        for row in rows:
            old_owner = self._extract_owner(row["old_state"])
            new_owner = self._extract_owner(row["new_state"])
            if old_owner and new_owner and old_owner != new_owner:
                # Check if there IS a transfer event (if not, A5 catches it)
                has_transfer = self.conn.execute(
                    """SELECT 1 FROM chain_events
                       WHERE object_id = ?
                       AND timestamp BETWEEN ? AND ?
                       AND (event_type LIKE '%Transfer%'
                            OR raw_json LIKE '%OwnerCap%')
                       LIMIT 1""",
                    (row["object_id"], row["old_time"], row["new_time"]),
                ).fetchone()

                if has_transfer:
                    anomalies.append(
                        Anomaly(
                            anomaly_type="OWNERCAP_DELEGATION",
                            rule_id="OC1",
                            detector=self.name,
                            object_id=row["object_id"],
                            severity="MEDIUM",
                            evidence={
                                "old_owner": old_owner,
                                "new_owner": new_owner,
                                "old_snapshot": row["old_time"],
                                "new_snapshot": row["new_time"],
                                "description": (
                                    f"Ownership delegation — {row['object_id'][:16]}... "
                                    f"handed from {old_owner[:16]}... to "
                                    f"{new_owner[:16]}... with transfer on record. "
                                    f"Deliberate, but worth tracking"
                                ),
                            },
                            provenance=[
                                ProvenanceEntry(
                                    source_type="world_state",
                                    source_id=f"snapshot:{row['object_id']}:{row['old_time']}",
                                    timestamp=row["old_time"],
                                    derivation=f"OC1: old snapshot owner {old_owner[:16]}...",
                                ),
                                ProvenanceEntry(
                                    source_type="world_state",
                                    source_id=f"snapshot:{row['object_id']}:{row['new_time']}",
                                    timestamp=row["new_time"],
                                    derivation=(
                                        f"OC1: new owner {new_owner[:16]}, transfer confirmed"
                                    ),
                                ),
                            ],
                        )
                    )

        return anomalies

    @staticmethod
    def _involves_ownercap(event: dict, parsed: dict) -> bool:
        """Check if an event involves an OwnerCap object."""
        # Check event type
        if event.get("event_type", "") in OWNERCAP_EVENT_TYPES:
            return True
        # Check raw JSON for OwnerCap references
        raw = event.get("raw_json", "")
        if isinstance(raw, str) and ("OwnerCap" in raw or "ownerCap" in raw):
            return True
        # Check parsed type field
        type_repr = parsed.get("type", {})
        if isinstance(type_repr, dict):
            type_repr = type_repr.get("repr", "")
        return isinstance(type_repr, str) and "OwnerCap" in type_repr

    @staticmethod
    def _extract_address(d: dict, *keys: str) -> str:
        """Extract an address from parsed event data, trying multiple keys."""
        for key in keys:
            val = d.get(key)
            if val and isinstance(val, str):
                return val
            if isinstance(val, dict):
                addr = val.get("address", val.get("id", ""))
                if addr:
                    return str(addr)
        return ""

    @staticmethod
    def _extract_owner(state_data: str) -> str:
        """Extract owner address from a snapshot's state_data JSON."""
        if not state_data:
            return ""
        try:
            data = json.loads(state_data) if isinstance(state_data, str) else state_data
        except (json.JSONDecodeError, TypeError):
            return ""
        owner = data.get("owner", {})
        if isinstance(owner, dict):
            return owner.get("address", owner.get("id", ""))
        if isinstance(owner, str):
            return owner
        return ""

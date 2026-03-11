"""Assembly checker — detects smart assembly state anomalies.

Rules:
  A1 — State mismatch: API state diverges from last known transition state
  A2 — Free gate jump: gate jump event without fuel consumption
  A3 — Failed gate transport: fuel consumed but position unchanged
  A4 — Phantom item change: inventory changed without add/remove events
  A5 — Unexplained ownership change: owner changed without transfer event
"""

import json
import logging
import time

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)


class AssemblyChecker(BaseChecker):
    """Checks smart assembly integrity — state consistency, ownership, fuel."""

    name = "assembly_checker"

    def check(self) -> list[Anomaly]:
        """Run all assembly rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_a1_state_mismatch())
        anomalies.extend(self._check_a4_phantom_changes())
        anomalies.extend(self._check_a5_ownership_change())
        # A2 (free gate jump) and A3 (failed transport) require gate-specific
        # event types — will activate once we decode MUD event topics
        return anomalies

    def _check_a1_state_mismatch(self) -> list[Anomaly]:
        """A1: Latest API state doesn't match last recorded transition.

        If state_transitions says object is 'online' but the latest API
        snapshot says 'offline', there was an unrecorded state change.
        """
        # Get objects with both transitions and recent snapshots
        rows = self.conn.execute(
            """SELECT o.object_id, o.system_id,
                      st.to_state as transition_state, st.timestamp as transition_time,
                      ws.state_data, ws.snapshot_time
               FROM objects o
               JOIN state_transitions st ON o.object_id = st.object_id
                 AND st.timestamp = (
                   SELECT MAX(timestamp) FROM state_transitions WHERE object_id = o.object_id
                 )
               JOIN world_states ws ON o.object_id = ws.object_id
                 AND ws.snapshot_time = (
                   SELECT MAX(snapshot_time) FROM world_states WHERE object_id = o.object_id
                 )
               WHERE o.object_type = 'smartassemblies'
                 AND ws.snapshot_time > st.timestamp
               LIMIT 200"""
        ).fetchall()

        anomalies = []
        for row in rows:
            try:
                state_data = json.loads(row["state_data"])
            except json.JSONDecodeError:
                continue

            api_state = state_data.get("state", "")
            transition_state_raw = row["transition_state"]

            # Parse transition state — it's stored as JSON of the full state
            try:
                transition_data = json.loads(transition_state_raw)
                transition_state = transition_data.get("state", transition_state_raw)
            except (json.JSONDecodeError, AttributeError):
                transition_state = transition_state_raw

            if not api_state or not transition_state:
                continue
            if api_state == transition_state:
                continue

            anomalies.append(
                Anomaly(
                    anomaly_type="CONTRACT_STATE_MISMATCH",
                    rule_id="A1",
                    detector=self.name,
                    object_id=row["object_id"],
                    system_id=row["system_id"] or "",
                    evidence={
                        "api_state": api_state,
                        "transition_state": transition_state,
                        "transition_time": row["transition_time"],
                        "snapshot_time": row["snapshot_time"],
                        "description": (
                            f"Last transition recorded state '{transition_state}' "
                            f"but API shows '{api_state}' — unrecorded state change"
                        ),
                    },
                )
            )
        return anomalies

    def _check_a4_phantom_changes(self) -> list[Anomaly]:
        """A4: Object properties changed between snapshots without events.

        Compares consecutive snapshots for significant field changes
        (fuel, energy, state) and checks for corresponding chain events.
        """
        cutoff = int(time.time()) - 3600
        objects = self.conn.execute(
            """SELECT DISTINCT object_id FROM world_states
               WHERE object_type = 'smartassemblies' AND snapshot_time >= ?""",
            (cutoff,),
        ).fetchall()

        anomalies = []
        for row in objects:
            obj_id = row["object_id"]
            snapshots = self._get_latest_snapshots(obj_id, count=2)
            if len(snapshots) < 2:
                continue

            new_data = self._parse_state(snapshots[0])
            old_data = self._parse_state(snapshots[1])

            # Check significant fields that shouldn't change silently
            changes = self._find_significant_changes(old_data, new_data)
            if not changes:
                continue

            # Check if chain events explain the changes
            events = self._events_for_object(obj_id, since=snapshots[1]["snapshot_time"])
            if events:
                continue

            system_id = ""
            solar = new_data.get("solarSystem", {})
            if isinstance(solar, dict):
                system_id = str(solar.get("id", ""))

            anomalies.append(
                Anomaly(
                    anomaly_type="PHANTOM_ITEM_CHANGE",
                    rule_id="A4",
                    detector=self.name,
                    object_id=obj_id,
                    system_id=system_id,
                    evidence={
                        "changes": changes,
                        "old_snapshot_time": snapshots[1]["snapshot_time"],
                        "new_snapshot_time": snapshots[0]["snapshot_time"],
                        "chain_events_in_window": 0,
                        "description": (
                            f"Properties changed between snapshots with no "
                            f"chain events: {list(changes.keys())}"
                        ),
                    },
                )
            )
        return anomalies

    def _check_a5_ownership_change(self) -> list[Anomaly]:
        """A5: Owner changed between snapshots without transfer event.

        Ownership changes must have a corresponding on-chain transfer event.
        """
        cutoff = int(time.time()) - 3600
        objects = self.conn.execute(
            """SELECT DISTINCT object_id FROM world_states
               WHERE object_type = 'smartassemblies' AND snapshot_time >= ?""",
            (cutoff,),
        ).fetchall()

        anomalies = []
        for row in objects:
            obj_id = row["object_id"]
            snapshots = self._get_latest_snapshots(obj_id, count=2)
            if len(snapshots) < 2:
                continue

            new_data = self._parse_state(snapshots[0])
            old_data = self._parse_state(snapshots[1])

            new_owner = self._extract_owner(new_data)
            old_owner = self._extract_owner(old_data)

            if not new_owner or not old_owner or new_owner == old_owner:
                continue
            # Skip null-address owners (default/unowned)
            null_addr = "0x" + "0" * 40
            if old_owner == null_addr or new_owner == null_addr:
                continue

            # Check for transfer events
            events = self._events_for_object(obj_id, since=snapshots[1]["snapshot_time"])
            has_transfer = any(
                "transfer" in (e.get("event_type", "") or "").lower() for e in events
            )
            if has_transfer:
                continue

            system_id = ""
            solar = new_data.get("solarSystem", {})
            if isinstance(solar, dict):
                system_id = str(solar.get("id", ""))

            anomalies.append(
                Anomaly(
                    anomaly_type="UNEXPLAINED_OWNERSHIP_CHANGE",
                    rule_id="A5",
                    detector=self.name,
                    object_id=obj_id,
                    system_id=system_id,
                    evidence={
                        "old_owner": old_owner,
                        "new_owner": new_owner,
                        "old_snapshot_time": snapshots[1]["snapshot_time"],
                        "new_snapshot_time": snapshots[0]["snapshot_time"],
                        "chain_events_in_window": len(events),
                        "description": (
                            f"Owner changed from {old_owner[:10]}... to "
                            f"{new_owner[:10]}... without transfer event"
                        ),
                    },
                )
            )
        return anomalies

    @staticmethod
    def _extract_owner(state: dict) -> str:
        """Extract owner address from state data."""
        owner = state.get("owner", {})
        if isinstance(owner, dict):
            return owner.get("address", "")
        return str(owner)

    @staticmethod
    def _find_significant_changes(old: dict, new: dict) -> dict:
        """Find significant changes between two state snapshots.

        Ignores cosmetic fields. Focuses on fuel, energy, state, owner.
        """
        significant_fields = {"state", "energyUsage", "typeId"}
        changes = {}

        for field in significant_fields:
            old_val = old.get(field)
            new_val = new.get(field)
            if old_val != new_val and old_val is not None and new_val is not None:
                changes[field] = {"old": old_val, "new": new_val}

        # Check nested fuel amount
        old_fuel = old.get("networkNode", {})
        new_fuel = new.get("networkNode", {})
        if isinstance(old_fuel, dict) and isinstance(new_fuel, dict):
            old_amt = old_fuel.get("fuel", {}).get("amount")
            new_amt = new_fuel.get("fuel", {}).get("amount")
            if old_amt is not None and new_amt is not None and old_amt != new_amt:
                changes["fuel.amount"] = {"old": old_amt, "new": new_amt}

        return changes

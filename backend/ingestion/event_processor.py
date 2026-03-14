"""Event processor — transforms raw chain events into object state.

Reads unprocessed chain_events and:
  1. Creates/updates entries in the `objects` table (object registry)
  2. Writes state snapshots to `world_states` for checker consumption
  3. Records state transitions for delta detection

This bridges the gap between raw Sui event ingestion (chain_reader.py)
and the detection engine which queries objects + world_states.
"""

import json
import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

# Maps event type suffix → handler method name
EVENT_HANDLERS: dict[str, str] = {
    "AssemblyCreatedEvent": "_handle_assembly_created",
    "CharacterCreatedEvent": "_handle_character_created",
    "StatusChangedEvent": "_handle_status_changed",
    "KillmailCreatedEvent": "_handle_killmail",
    "OwnerCapTransferred": "_handle_ownership_transfer",
    "ItemMintedEvent": "_handle_item_event",
    "ItemBurnedEvent": "_handle_item_event",
    "ItemDepositedEvent": "_handle_item_event",
    "ItemWithdrawnEvent": "_handle_item_event",
    "ItemDestroyedEvent": "_handle_item_destroyed",
    "FuelEvent": "_handle_fuel_event",
    "JumpEvent": "_handle_jump_event",
    "GateCreatedEvent": "_handle_assembly_created",
    "GateLinkedEvent": "_handle_gate_link",
    "GateUnlinkedEvent": "_handle_gate_link",
}


class EventProcessor:
    """Processes raw chain events into structured object state."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def process_unprocessed(self, batch_size: int = 500) -> int:
        """Process a batch of unprocessed chain events. Returns count processed."""
        rows = self.conn.execute(
            """SELECT id, event_id, event_type, object_id, object_type,
                      system_id, transaction_hash, timestamp, raw_json
               FROM chain_events
               WHERE processed = 0
               ORDER BY timestamp ASC
               LIMIT ?""",
            (batch_size,),
        ).fetchall()

        if not rows:
            return 0

        processed_ids = []
        for row in rows:
            event = dict(row)
            try:
                self._dispatch_event(event)
                processed_ids.append(event["event_id"])
            except Exception:
                logger.exception(
                    "Failed to process event %s (%s)",
                    event["event_id"],
                    event["event_type"],
                )

        # Mark processed
        if processed_ids:
            placeholders = ",".join("?" * len(processed_ids))
            self.conn.execute(
                f"UPDATE chain_events SET processed = 1 WHERE event_id IN ({placeholders})",  # noqa: S608
                processed_ids,
            )
            self.conn.commit()

        if processed_ids:
            logger.info("Processed %d chain events into object state", len(processed_ids))
        return len(processed_ids)

    def _dispatch_event(self, event: dict) -> None:
        """Route an event to its handler based on event type suffix."""
        event_type = event.get("event_type", "")
        # Event type format: {packageId}::module::EventName
        suffix = event_type.rsplit("::", 1)[-1] if "::" in event_type else ""

        handler_name = EVENT_HANDLERS.get(suffix)
        if handler_name:
            handler = getattr(self, handler_name)
            parsed = self._parse_raw(event)
            handler(event, parsed)

    def _parse_raw(self, event: dict) -> dict:
        """Parse the raw_json field to get the Sui event's parsedJson."""
        raw = event.get("raw_json", "{}")
        try:
            sui_event = json.loads(raw) if isinstance(raw, str) else raw
            return sui_event.get("parsedJson", {})
        except json.JSONDecodeError:
            return {}

    # -- Object lifecycle handlers --

    def _handle_assembly_created(self, event: dict, parsed: dict) -> None:
        """AssemblyCreatedEvent / GateCreatedEvent → insert into objects table."""
        object_id = event["object_id"]
        if not object_id:
            return

        # Determine type from event module
        module = event.get("object_type", "")
        object_type = "gate" if module == "gate" else "smartassemblies"

        state = {
            "assembly_id": object_id,
            "type_id": parsed.get("type_id", parsed.get("typeId", "")),
            "state": parsed.get("status", "unanchored"),
            "assembly_key": parsed.get("assembly_key", ""),
        }

        if event["system_id"]:
            state["solarSystem"] = {"id": event["system_id"]}

        self._upsert_object(
            object_id=object_id,
            object_type=object_type,
            state=state,
            owner=parsed.get("owner", ""),
            system_id=event["system_id"],
            timestamp=event["timestamp"],
            event_id=event["event_id"],
        )

    def _handle_character_created(self, event: dict, parsed: dict) -> None:
        """CharacterCreatedEvent → insert into objects table."""
        object_id = event["object_id"]
        if not object_id:
            return

        state = {
            "character_id": object_id,
            "tribe_id": parsed.get("tribe_id", parsed.get("tribeId", "")),
            "character_address": parsed.get(
                "character_address", parsed.get("characterAddress", "")
            ),
        }

        self._upsert_object(
            object_id=object_id,
            object_type="character",
            state=state,
            owner=parsed.get("character_address", ""),
            system_id=event["system_id"],
            timestamp=event["timestamp"],
            event_id=event["event_id"],
        )

    def _handle_status_changed(self, event: dict, parsed: dict) -> None:
        """StatusChangedEvent → update object state + record transition."""
        object_id = event["object_id"]
        if not object_id:
            return

        new_status = parsed.get("status", parsed.get("new_status", ""))
        action = parsed.get("action", "")

        # Get current state for transition recording
        current = self._get_current_state(object_id)
        old_status = current.get("state", "") if current else ""

        # Update state
        state_update = dict(current) if current else {}
        state_update["state"] = new_status
        if action:
            state_update["last_action"] = action

        self._upsert_object(
            object_id=object_id,
            object_type="smartassemblies",
            state=state_update,
            system_id=event["system_id"],
            timestamp=event["timestamp"],
            event_id=event["event_id"],
        )

        # Record state transition
        if old_status and old_status != new_status:
            self._record_transition(
                object_id=object_id,
                from_state=old_status,
                to_state=new_status,
                event_id=event["event_id"],
                tx_hash=event["transaction_hash"],
                timestamp=event["timestamp"],
            )

        # Write snapshot for checker consumption
        self._write_snapshot(object_id, "smartassemblies", state_update, event["timestamp"])

    def _handle_killmail(self, event: dict, parsed: dict) -> None:
        """KillmailCreatedEvent → mark victim as destroyed."""
        victim_id = parsed.get("victim_id", parsed.get("victimId", ""))
        if victim_id:
            self.conn.execute(
                """UPDATE objects SET destroyed_at = ?
                   WHERE object_id = ? AND destroyed_at IS NULL""",
                (event["timestamp"], victim_id),
            )

        # Also track killer activity
        killer_id = parsed.get("killer_id", parsed.get("killerId", ""))
        if killer_id:
            self.conn.execute(
                "UPDATE objects SET last_seen = ? WHERE object_id = ?",
                (event["timestamp"], killer_id),
            )

    def _handle_ownership_transfer(self, event: dict, parsed: dict) -> None:
        """OwnerCapTransferred → update owner on the authorized object."""
        object_id = parsed.get("authorized_object_id", parsed.get("authorizedObjectId", ""))
        new_owner = parsed.get("owner", parsed.get("newOwner", ""))

        if not object_id or not new_owner:
            return

        current = self._get_current_state(object_id)
        state_update = dict(current) if current else {}
        state_update["owner"] = {"address": new_owner}

        old_owner = parsed.get("previous_owner", parsed.get("previousOwner", ""))
        if old_owner:
            state_update["previous_owner"] = old_owner

        self._upsert_object(
            object_id=object_id,
            object_type="smartassemblies",
            state=state_update,
            owner=new_owner,
            system_id=event["system_id"],
            timestamp=event["timestamp"],
            event_id=event["event_id"],
        )

        # Write snapshot for ownership tracking
        self._write_snapshot(object_id, "smartassemblies", state_update, event["timestamp"])

    def _handle_item_event(self, event: dict, parsed: dict) -> None:
        """Item mint/burn/deposit/withdraw → track inventory + update object."""
        object_id = event["object_id"]
        if not object_id:
            return

        # Update last_seen timestamp (existing behavior)
        self.conn.execute(
            """UPDATE objects SET last_seen = ?, last_event_id = ?
               WHERE object_id = ?""",
            (event["timestamp"], event["event_id"], object_id),
        )

        # Extract item details from parsedJson
        quantity = parsed.get("quantity", parsed.get("amount", 0))
        item_type_id = parsed.get(
            "item_type_id",
            parsed.get("itemTypeId", parsed.get("type_id", parsed.get("typeId", ""))),
        )

        # Determine action from event type suffix
        event_type = event.get("event_type", "")
        suffix = event_type.rsplit("::", 1)[-1] if "::" in event_type else ""
        action = suffix.replace("Event", "").replace("Item", "").lower()

        # Record in item ledger
        try:
            self.conn.execute(
                """INSERT INTO item_ledger
                   (assembly_id, item_type_id, event_type, quantity,
                    event_id, transaction_hash, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    object_id,
                    str(item_type_id),
                    action,
                    int(quantity) if quantity else 0,
                    event["event_id"],
                    event.get("transaction_hash", ""),
                    event["timestamp"],
                ),
            )
        except Exception:
            logger.exception(
                "Failed to record item ledger entry for %s", event["event_id"]
            )
            return

        # Build inventory snapshot for checker consumption
        if quantity or item_type_id:
            current = self._get_current_state(object_id)
            state_update = dict(current) if current else {}
            inventory = state_update.setdefault("inventory", {})
            if isinstance(inventory, dict):
                type_key = str(item_type_id) if item_type_id else "unknown"
                balance = inventory.get(type_key, 0)
                if action in ("minted", "deposited"):
                    balance += int(quantity) if quantity else 0
                elif action in ("burned", "withdrawn"):
                    balance -= int(quantity) if quantity else 0
                inventory[type_key] = balance
                state_update["inventory"] = inventory

            self._upsert_object(
                object_id=object_id,
                object_type="smartassemblies",
                state=state_update,
                system_id=event.get("system_id", ""),
                timestamp=event["timestamp"],
                event_id=event["event_id"],
            )
            self._write_snapshot(
                object_id, "smartassemblies", state_update, event["timestamp"]
            )

    def _handle_item_destroyed(self, event: dict, parsed: dict) -> None:
        """ItemDestroyedEvent → mark object destroyed if applicable."""
        object_id = event["object_id"]
        if not object_id:
            return

        # Mark as destroyed
        self.conn.execute(
            """UPDATE objects SET destroyed_at = ?, last_event_id = ?
               WHERE object_id = ? AND destroyed_at IS NULL""",
            (event["timestamp"], event["event_id"], object_id),
        )

    def _handle_fuel_event(self, event: dict, parsed: dict) -> None:
        """FuelEvent → update fuel state on assembly."""
        object_id = event["object_id"]
        if not object_id:
            return

        current = self._get_current_state(object_id)
        state_update = dict(current) if current else {}

        new_qty = parsed.get("new_quantity", parsed.get("newQuantity"))
        old_qty = parsed.get("old_quantity", parsed.get("oldQuantity"))
        action = parsed.get("action", "")

        state_update.setdefault("networkNode", {})
        if isinstance(state_update["networkNode"], dict):
            state_update["networkNode"]["fuel"] = {
                "amount": new_qty,
                "previous_amount": old_qty,
                "last_action": action,
            }

        self._upsert_object(
            object_id=object_id,
            object_type="smartassemblies",
            state=state_update,
            system_id=event["system_id"],
            timestamp=event["timestamp"],
            event_id=event["event_id"],
        )

        # Write snapshot for fuel tracking (E1 checker)
        self._write_snapshot(object_id, "smartassemblies", state_update, event["timestamp"])

    def _handle_jump_event(self, event: dict, parsed: dict) -> None:
        """JumpEvent → track gate activity + character movement."""
        # Update source gate last_seen
        source_gate = parsed.get("source_gate_id", parsed.get("sourceGateId", ""))
        dest_gate = parsed.get("dest_gate_id", parsed.get("destGateId", ""))
        character_id = parsed.get("character_id", parsed.get("characterId", ""))

        for gate_id in (source_gate, dest_gate):
            if gate_id:
                self.conn.execute(
                    "UPDATE objects SET last_seen = ? WHERE object_id = ?",
                    (event["timestamp"], gate_id),
                )

        if character_id:
            self.conn.execute(
                "UPDATE objects SET last_seen = ? WHERE object_id = ?",
                (event["timestamp"], character_id),
            )

    def _handle_gate_link(self, event: dict, parsed: dict) -> None:
        """GateLinkedEvent / GateUnlinkedEvent → update gate topology."""
        source = parsed.get("source_gate_id", parsed.get("sourceGateId", ""))
        dest = parsed.get("dest_gate_id", parsed.get("destGateId", ""))

        for gate_id in (source, dest):
            if gate_id:
                self.conn.execute(
                    "UPDATE objects SET last_seen = ? WHERE object_id = ?",
                    (event["timestamp"], gate_id),
                )

    # -- Helper methods --

    def _get_current_state(self, object_id: str) -> dict:
        """Get current state dict for an object."""
        row = self.conn.execute(
            "SELECT current_state FROM objects WHERE object_id = ?",
            (object_id,),
        ).fetchone()
        if row and row["current_state"]:
            try:
                return json.loads(row["current_state"])
            except json.JSONDecodeError:
                return {}
        return {}

    def _upsert_object(
        self,
        object_id: str,
        object_type: str,
        state: dict,
        owner: str = "",
        system_id: str = "",
        timestamp: int = 0,
        event_id: str = "",
    ) -> None:
        """Insert or update an object in the registry."""
        now = timestamp or int(time.time())
        self.conn.execute(
            """INSERT INTO objects
               (object_id, object_type, current_state, current_owner,
                system_id, last_event_id, last_seen, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(object_id) DO UPDATE SET
                   current_state = excluded.current_state,
                   current_owner = CASE
                       WHEN excluded.current_owner != '' THEN excluded.current_owner
                       ELSE objects.current_owner
                   END,
                   system_id = CASE
                       WHEN excluded.system_id != '' THEN excluded.system_id
                       ELSE objects.system_id
                   END,
                   last_event_id = excluded.last_event_id,
                   last_seen = excluded.last_seen""",
            (object_id, object_type, json.dumps(state), owner, system_id, event_id, now, now),
        )

    def _write_snapshot(
        self,
        object_id: str,
        object_type: str,
        state: dict,
        timestamp: int,
    ) -> None:
        """Write a state snapshot to world_states for checker consumption."""
        self.conn.execute(
            """INSERT INTO world_states
               (object_id, object_type, state_data, snapshot_time, source)
               VALUES (?, ?, ?, ?, 'chain_event')""",
            (object_id, object_type, json.dumps(state), timestamp),
        )

    def _record_transition(
        self,
        object_id: str,
        from_state: str,
        to_state: str,
        event_id: str,
        tx_hash: str,
        timestamp: int,
    ) -> None:
        """Record a state transition."""
        self.conn.execute(
            """INSERT INTO state_transitions
               (object_id, from_state, to_state, event_id,
                transaction_hash, block_number, timestamp, is_valid)
               VALUES (?, ?, ?, ?, ?, 0, ?, 1)""",
            (
                object_id,
                json.dumps({"state": from_state}),
                json.dumps({"state": to_state}),
                event_id,
                tx_hash,
                timestamp,
            ),
        )

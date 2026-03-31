"""Chain reader — reads on-chain events from Sui via suix_queryEvents.

Targets the EVE Frontier world contracts deployed on Sui (Cycle 5+).
Each event type is polled independently with cursor persistence for
resumable ingestion across restarts.
"""

import json
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)

# Sui event query page size (max 50 per Sui RPC spec)
PAGE_SIZE = 50

# Event types to subscribe to, keyed by module::EventName.
# {pkg} is replaced with the live package ID at init time.
EVENT_TYPES = [
    "{pkg}::killmail::KillmailCreatedEvent",
    "{pkg}::gate::JumpEvent",
    "{pkg}::status::StatusChangedEvent",
    "{pkg}::inventory::ItemMintedEvent",
    "{pkg}::inventory::ItemBurnedEvent",
    "{pkg}::inventory::ItemDepositedEvent",
    "{pkg}::inventory::ItemWithdrawnEvent",
    "{pkg}::inventory::ItemDestroyedEvent",
    "{pkg}::fuel::FuelEvent",
    "{pkg}::access_control::OwnerCapTransferred",
    "{pkg}::assembly::AssemblyCreatedEvent",
    "{pkg}::character::CharacterCreatedEvent",
    "{pkg}::location::LocationRevealedEvent",
]

# Maps module name to the field in parsedJson that holds the primary object ID.
# Fallback: use the first field ending in "id" or "_id".
OBJECT_ID_FIELDS: dict[str, str] = {
    "killmail": "victim_id",
    "gate": "source_gate_id",
    "status": "assembly_id",
    "inventory": "assembly_id",
    "fuel": "assembly_id",
    "access_control": "authorized_object_id",
    "assembly": "assembly_id",
    "character": "character_id",
    "network_node": "network_node_id",
    "energy": "energy_source_id",
    "storage_unit": "assembly_id",
    "location": "object_id",
    "turret": "assembly_id",
}


class _StaleCursorError(Exception):
    """Raised when a stored cursor references a pruned Sui transaction."""


class ChainReader:
    """Reads events from Sui RPC and writes to chain_events table."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        rpc_url: str,
        package_id: str,
        timeout: int = 30,
    ):
        self.conn = conn
        self.rpc_url = rpc_url
        self.package_id = package_id
        self.timeout = timeout
        # Resolve event type strings with the live package ID
        self.events = [e.replace("{pkg}", package_id) for e in EVENT_TYPES]

    async def query_events(
        self,
        client: httpx.AsyncClient,
        event_type: str,
        cursor: dict | None = None,
        limit: int = PAGE_SIZE,
    ) -> tuple[list[dict], dict | None, bool]:
        """Query Sui events by type. Returns (events, next_cursor, has_next_page)."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "suix_queryEvents",
            "params": [
                {"MoveEventType": event_type},
                cursor,  # None = start from beginning
                limit,
                False,  # ascending (oldest first)
            ],
        }
        resp = await client.post(self.rpc_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            error = data["error"]
            logger.error("Sui RPC error for %s: %s", event_type, error)
            # If the cursor references a pruned transaction, signal the caller
            # to reset the cursor by raising a specific error
            msg = str(error.get("message", "")) if isinstance(error, dict) else str(error)
            if "Could not find the referenced transaction" in msg:
                raise _StaleCursorError(msg)
            return [], None, False

        result = data.get("result", {})
        events = result.get("data", [])
        next_cursor = result.get("nextCursor")
        has_next = result.get("hasNextPage", False)
        return events, next_cursor, has_next

    def _extract_object_id(self, event: dict) -> str:
        """Extract the primary object ID from a Sui event's parsedJson."""
        module = event.get("transactionModule", "")
        parsed = event.get("parsedJson", {})

        # Try the known field for this module
        field = OBJECT_ID_FIELDS.get(module, "")
        if field and field in parsed:
            return str(parsed[field])

        # Fallback: first field containing "id" (case-insensitive)
        for key, val in parsed.items():
            if "id" in key.lower() and isinstance(val, str):
                return val

        return ""

    def _extract_system_id(self, event: dict) -> str:
        """Extract solar system ID if present in event data."""
        parsed = event.get("parsedJson", {})
        for key in ("solar_system_id", "solarSystemId", "system_id", "systemId"):
            if key in parsed:
                val = parsed[key]
                # Handle dict format: {'item_id': '30013131', 'tenant': 'utopia'}
                if isinstance(val, dict):
                    return str(val.get("item_id", val.get("id", "")))
                return str(val)
        # LocationRevealedEvent carries location as nested object
        location = parsed.get("location", {})
        if isinstance(location, dict):
            for key in ("solar_system_id", "solarSystemId"):
                if key in location:
                    val = location[key]
                    if isinstance(val, dict):
                        return str(val.get("item_id", val.get("id", "")))
                    return str(val)
        return ""

    def store_event(self, event: dict) -> bool:
        """Store a Sui event. Returns True if new, False if duplicate."""
        event_id_obj = event.get("id", {})
        tx_digest = event_id_obj.get("txDigest", "")
        event_seq = event_id_obj.get("eventSeq", "0")
        event_id = f"{tx_digest}:{event_seq}"

        event_type = event.get("type", "")
        object_id = self._extract_object_id(event)
        system_id = self._extract_system_id(event)
        timestamp_ms = event.get("timestampMs", "0")
        timestamp = int(timestamp_ms) // 1000 if timestamp_ms else int(time.time())

        try:
            self.conn.execute(
                """INSERT INTO chain_events
                   (event_id, event_type, object_id, object_type, system_id,
                    block_number, transaction_hash, timestamp, raw_json, processed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    event_id,
                    event_type,
                    object_id,
                    event.get("transactionModule", ""),
                    system_id,
                    0,  # Sui doesn't have block numbers in event responses
                    tx_digest,
                    timestamp,
                    json.dumps(event),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def _load_cursor(self, event_filter: str) -> dict | None:
        """Load persisted cursor for an event type."""
        row = self.conn.execute(
            "SELECT tx_digest, event_seq FROM sui_cursors WHERE event_filter = ?",
            (event_filter,),
        ).fetchone()
        if row:
            return {"txDigest": row["tx_digest"], "eventSeq": row["event_seq"]}
        return None

    def _save_cursor(self, event_filter: str, cursor: dict) -> None:
        """Persist cursor for an event type."""
        self.conn.execute(
            """INSERT INTO sui_cursors (event_filter, tx_digest, event_seq, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(event_filter) DO UPDATE SET
                   tx_digest = excluded.tx_digest,
                   event_seq = excluded.event_seq,
                   updated_at = excluded.updated_at""",
            (
                event_filter,
                cursor["txDigest"],
                cursor["eventSeq"],
                int(time.time()),
            ),
        )
        self.conn.commit()

    def _clear_cursor(self, event_filter: str) -> None:
        """Clear a stale cursor so next poll starts fresh."""
        self.conn.execute(
            "DELETE FROM sui_cursors WHERE event_filter = ?",
            (event_filter,),
        )
        self.conn.commit()

    async def poll(self, client: httpx.AsyncClient) -> int:
        """Poll all event types for new events. Returns total count stored."""
        if not self.package_id:
            logger.warning("No sui_package_id configured — skipping chain poll")
            return 0

        total_stored = 0

        for event_type in self.events:
            cursor = self._load_cursor(event_type)

            # Paginate through new events for this type
            while True:
                try:
                    events, next_cursor, has_next = await self.query_events(
                        client, event_type, cursor
                    )
                except _StaleCursorError:
                    logger.warning(
                        "Stale cursor for %s — clearing and restarting from latest",
                        event_type,
                    )
                    self._clear_cursor(event_type)
                    break
                except (httpx.HTTPError, KeyError, ValueError) as e:
                    logger.error("Sui event poll failed for %s: %s", event_type, e)
                    break

                stored = 0
                for event in events:
                    if self.store_event(event):
                        stored += 1
                total_stored += stored

                # Persist cursor after each page
                if next_cursor:
                    self._save_cursor(event_type, next_cursor)
                    cursor = next_cursor

                if not has_next or not events:
                    break

        if total_stored > 0:
            logger.info("Stored %d Sui events across %d types", total_stored, len(self.events))
            self._enrich_system_ids()
        return total_stored

    def _enrich_system_ids(self) -> None:
        """Backfill objects.system_id from LocationRevealedEvent data."""
        location_type = f"{self.package_id}::location::LocationRevealedEvent"
        rows = self.conn.execute(
            "SELECT object_id, system_id FROM chain_events "
            "WHERE event_type = ? AND system_id != ''",
            (location_type,),
        ).fetchall()
        if not rows:
            return
        updated = 0
        for row in rows:
            result = self.conn.execute(
                "UPDATE objects SET system_id = ? "
                "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                (row["system_id"], row["object_id"]),
            )
            updated += result.rowcount
            # Also backfill anomalies that reference this object
            self.conn.execute(
                "UPDATE anomalies SET system_id = ? "
                "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                (row["system_id"], row["object_id"]),
            )
        if updated > 0:
            self.conn.commit()
            logger.info("Enriched %d objects with system_id from location events", updated)

    def get_last_block(self) -> int:
        """Get the highest block number (checkpoint) we've processed."""
        row = self.conn.execute("SELECT MAX(block_number) FROM chain_events").fetchone()
        return row[0] or 0

    def get_unprocessed_count(self) -> int:
        """Count events not yet processed by detection engine."""
        row = self.conn.execute("SELECT COUNT(*) FROM chain_events WHERE processed = 0").fetchone()
        return row[0]

    def mark_processed(self, event_ids: list[str]) -> None:
        """Mark events as processed by detection engine."""
        if not event_ids:
            return
        placeholders = ",".join("?" * len(event_ids))
        self.conn.execute(
            f"UPDATE chain_events SET processed = 1 WHERE event_id IN ({placeholders})",  # noqa: S608
            event_ids,
        )
        self.conn.commit()

    async def get_chain_info(self, client: httpx.AsyncClient) -> dict:
        """Get chain info for health check."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sui_getLatestCheckpointSequenceNumber",
                "params": [],
            }
            resp = await client.post(self.rpc_url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            checkpoint = resp.json().get("result", "0")
            return {
                "chain": "sui",
                "latest_checkpoint": int(checkpoint),
                "last_processed": self.get_last_block(),
                "package_id": self.package_id[:20] + "..." if self.package_id else "",
                "connected": True,
                "checked_at": int(time.time()),
            }
        except (httpx.HTTPError, ValueError) as e:
            logger.error("Sui health check failed: %s", e)
            return {
                "connected": False,
                "error": str(e),
                "checked_at": int(time.time()),
            }

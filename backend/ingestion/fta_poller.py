"""FTA poller — ingests Frontier Transit Authority state changes.

The FTA (Internet Spaceship Enterprises) is a community-managed gate network
on EVE Frontier. Its shared object doesn't emit custom Move events — state
changes are detected by polling transactions that affect the FTA shared object
via Sui GraphQL `affectedObject` filter.

Each transaction is inspected for:
  - JumpPermitIssuedEvent with FTA extension → FTA_JUMP
  - Object creations/deletions → gate reg/dereg, bounty creation
  - FTA object version changes → snapshot diff for blacklist/fee/registry changes

Data flow:
  GraphQL(affectedObject=FTA_OBJECT_ID, afterCheckpoint)
    → transaction digests
    → per-tx: events + object changes
    → synthesized chain_events (FTA_* types)
    → normal EventProcessor pipeline

See: https://github.com/Internet-Spaceship-Enterprises/frontier-transit-authority
"""

import json
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)

# FTA deployed addresses (Stillness testnet)
FTA_PACKAGE_ID = (
    "0x4d22d8e0cdc3fe27249f1f7ffb8a0b721ea32c80d33817e9fe394de07c771965"
)
FTA_OBJECT_ID = (
    "0x9f68faee73d9817cbf96ea86a0674465731e79da647466a5fe38242816225fc4"
)

# FTA sub-table IDs for targeted polling
FTA_GATE_REGISTRY_TABLE = (
    "0xda486d92d86793b2987a5edeef2f137cba7ca5f3cef207ec9b49826daa8af8fe"
)
FTA_BLACKLIST_TABLE = (
    "0x7ac35342d6d6dfec9e4da0dc64cbdfef78ee5fb6b58c4785f5839ed20d415651"
)
FTA_BOUNTY_CHARACTER_TABLE = (
    "0x2c5e9c125d7f67b28850b89026a12968f7d562a58bb9a7ecc1d29bbabfa1efbd"
)
FTA_JUMP_HISTORY_TABLE = (
    "0x8137286a1bd2b7f1507b1369e1c31ca05835ce99a7e2f055659f08b598a17d94"
)

SUI_GRAPHQL_URL = "https://graphql.testnet.sui.io/graphql"

# GraphQL query: transactions affecting FTA object, with events and object changes
FTA_TRANSACTIONS_QUERY = (
    """
query FTATransactions($afterCheckpoint: UInt53, $first: Int) {
  transactions(
    first: $first,
    filter: { affectedObject: \""""
    + FTA_OBJECT_ID
    + """\", afterCheckpoint: $afterCheckpoint }
  ) {
    nodes {
      digest
      sender { address }
      effects {
        timestamp
        status
        objectChanges {
          nodes {
            address
            idCreated
            idDeleted
          }
        }
        events {
          nodes {
            contents {
              type { repr }
              json
            }
            timestamp
          }
        }
        checkpoint { sequenceNumber }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""
)

# Query to get current FTA object version (for snapshot diffing)
FTA_OBJECT_QUERY = (
    """
query FTAObject {
  object(address: \""""
    + FTA_OBJECT_ID
    + """\") {
    version
    asMoveObject {
      contents { json }
    }
  }
}
"""
)

# FTA extension type identifier in JumpPermitIssuedEvent
FTA_JUMP_AUTH_TYPE = f"{FTA_PACKAGE_ID}::jump_auth::JumpAuth"


class FTAPoller:
    """Polls FTA transactions and synthesizes chain events."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        graphql_url: str = SUI_GRAPHQL_URL,
        timeout: int = 15,
    ):
        self.conn = conn
        self.graphql_url = graphql_url
        self.timeout = timeout
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create FTA tracking tables if they don't exist."""
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS fta_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at INTEGER
            )"""
        )
        self.conn.commit()

    def _get_state(self, key: str, default: str = "") -> str:
        """Get persisted FTA poller state."""
        row = self.conn.execute(
            "SELECT value FROM fta_state WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return row[0] if isinstance(row, tuple) else row["value"]
        return default

    def _set_state(self, key: str, value: str) -> None:
        """Persist FTA poller state."""
        self.conn.execute(
            """INSERT INTO fta_state (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
            (key, value, int(time.time()), value, int(time.time())),
        )
        self.conn.commit()

    async def poll(self, client: httpx.AsyncClient) -> int:
        """Poll FTA transactions since last checkpoint. Returns event count."""
        last_checkpoint = self._get_state("last_checkpoint", "0")

        try:
            resp = await client.post(
                self.graphql_url,
                json={
                    "query": FTA_TRANSACTIONS_QUERY,
                    "variables": {
                        "afterCheckpoint": int(last_checkpoint) if last_checkpoint != "0" else None,
                        "first": 50,
                    },
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("FTA GraphQL query failed: %s", e)
            return 0

        if "errors" in data:
            logger.error("FTA GraphQL errors: %s", data["errors"])
            return 0

        txs = data.get("data", {}).get("transactions", {})
        nodes = txs.get("nodes", [])
        if not nodes:
            return 0

        event_count = 0
        max_checkpoint = int(last_checkpoint)

        for tx in nodes:
            digest = tx.get("digest", "")
            sender = tx.get("sender", {}).get("address", "")
            effects = tx.get("effects", {})
            timestamp_str = effects.get("timestamp", "")
            timestamp = self._parse_timestamp(timestamp_str)
            checkpoint_node = effects.get("checkpoint")
            if checkpoint_node:
                seq = int(checkpoint_node.get("sequenceNumber", 0))
                if seq > max_checkpoint:
                    max_checkpoint = seq

            # Process events (JumpPermitIssuedEvent with FTA extension)
            events = effects.get("events", {}).get("nodes", [])
            for evt in events:
                contents = evt.get("contents", {})
                evt_type = contents.get("type", {}).get("repr", "")
                evt_json = contents.get("json", {})

                if "JumpPermitIssuedEvent" in evt_type:
                    ext_type = evt_json.get("extension_type", {}).get("name", "")
                    if FTA_JUMP_AUTH_TYPE in ext_type:
                        event_count += self._store_fta_event(
                            event_type="FTA_JumpPermit",
                            object_id=evt_json.get("source_gate_id", ""),
                            tx_digest=digest,
                            timestamp=timestamp,
                            sender=sender,
                            raw_data={
                                "source_gate_id": evt_json.get("source_gate_id", ""),
                                "destination_gate_id": evt_json.get("destination_gate_id", ""),
                                "character_id": evt_json.get("character_id", ""),
                                "jump_permit_id": evt_json.get("jump_permit_id", ""),
                                "source_gate_key": evt_json.get("source_gate_key", {}),
                                "destination_gate_key": evt_json.get("destination_gate_key", {}),
                                "character_key": evt_json.get("character_key", {}),
                                "expires_at": evt_json.get("expires_at_timestamp_ms", ""),
                            },
                        )

            # Process object changes (gate reg/dereg, bounty, blacklist)
            obj_changes = effects.get("objectChanges", {}).get("nodes", [])
            created_ids = [
                o["address"] for o in obj_changes
                if o.get("idCreated")
            ]
            deleted_ids = [
                o["address"] for o in obj_changes
                if o.get("idDeleted")
            ]

            # FTA object was mutated — record version change
            fta_mutated = any(
                o["address"] == FTA_OBJECT_ID for o in obj_changes
            )
            if fta_mutated and (created_ids or deleted_ids):
                event_count += self._store_fta_event(
                    event_type="FTA_StateMutation",
                    object_id=FTA_OBJECT_ID,
                    tx_digest=digest,
                    timestamp=timestamp,
                    sender=sender,
                    raw_data={
                        "created_objects": created_ids,
                        "deleted_objects": deleted_ids,
                        "object_change_count": len(obj_changes),
                    },
                )

        if max_checkpoint > int(last_checkpoint):
            self._set_state("last_checkpoint", str(max_checkpoint))

        if event_count:
            logger.info(
                "FTA poller: %d events from %d transactions (checkpoint %s→%s)",
                event_count, len(nodes), last_checkpoint, max_checkpoint,
            )

        return event_count

    async def snapshot_fta_object(self, client: httpx.AsyncClient) -> bool:
        """Take a snapshot of FTA object state for diff detection.

        Stores current gate count, blacklist count, bounty count, etc.
        Returns True if state changed since last snapshot.
        """
        try:
            resp = await client.post(
                self.graphql_url,
                json={"query": FTA_OBJECT_QUERY},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("FTA snapshot query failed: %s", e)
            return False

        obj = data.get("data", {}).get("object", {})
        version = str(obj.get("version", ""))
        last_version = self._get_state("last_version", "")

        if version == last_version:
            return False  # No change

        # Extract key metrics from object contents
        contents = (
            obj.get("asMoveObject", {}).get("contents", {}).get("json", {})
        )
        snapshot = {
            "version": version,
            "developer_balance": contents.get("developer_balance", "0"),
            "upgrade_cap_exchanged": contents.get("upgrade_cap_exchanged", False),
            "timestamp": int(time.time()),
        }

        self._set_state("last_version", version)
        self._set_state("last_snapshot", json.dumps(snapshot))

        logger.info(
            "FTA snapshot: version %s → %s, dev_balance=%s",
            last_version, version, snapshot["developer_balance"],
        )
        return True

    def _store_fta_event(
        self,
        event_type: str,
        object_id: str,
        tx_digest: str,
        timestamp: int,
        sender: str,
        raw_data: dict,
    ) -> int:
        """Store a synthesized FTA event in chain_events. Returns 1 if new, 0 if dup."""
        event_id = f"fta:{tx_digest}:{event_type}"
        raw_data["sender"] = sender
        raw_data["fta_package_id"] = FTA_PACKAGE_ID

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
                    "fta",
                    "",  # system_id resolved later via gate → system mapping
                    0,
                    tx_digest,
                    timestamp,
                    json.dumps(raw_data),
                ),
            )
            self.conn.commit()
            return 1
        except sqlite3.IntegrityError:
            return 0  # Duplicate

    @staticmethod
    def _parse_timestamp(ts_str: str) -> int:
        """Parse ISO 8601 timestamp to unix seconds."""
        if not ts_str:
            return int(time.time())
        try:
            from datetime import UTC, datetime

            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return int(dt.replace(tzinfo=UTC).timestamp())
        except (ValueError, AttributeError):
            return int(time.time())

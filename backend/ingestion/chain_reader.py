"""Sui RPC client for reading on-chain events from EVE Frontier contracts."""

import json
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)


class ChainReader:
    """Reads events from Sui RPC and writes to chain_events table."""

    def __init__(self, conn: sqlite3.Connection, rpc_url: str, timeout: int = 30):
        self.conn = conn
        self.rpc_url = rpc_url
        self.timeout = timeout
        self._last_cursor: str | None = None

    async def query_events(
        self, client: httpx.AsyncClient, cursor: str | None = None, limit: int = 50
    ) -> dict:
        """Query Sui RPC for events using sui_queryEvents."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "suix_queryEvents",
            "params": [
                {"All": []},
                cursor,
                limit,
                False,  # descending
            ],
        }
        resp = await client.post(self.rpc_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    async def get_object(self, client: httpx.AsyncClient, object_id: str) -> dict:
        """Fetch a single object from Sui by ID."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sui_getObject",
            "params": [
                object_id,
                {"showContent": True, "showOwner": True, "showType": True},
            ],
        }
        resp = await client.post(self.rpc_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def store_event(self, event: dict) -> bool:
        """Store a normalized chain event. Returns True if new, False if duplicate."""
        event_id = (
            event.get("id", {}).get("txDigest", "")
            + ":"
            + str(event.get("id", {}).get("eventSeq", 0))
        )
        try:
            self.conn.execute(
                """INSERT INTO chain_events
                   (event_id, event_type, object_id, object_type, system_id,
                    block_number, transaction_hash, timestamp, raw_json, processed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    event_id,
                    event.get("type", ""),
                    event.get("parsedJson", {}).get("object_id", ""),
                    event.get("parsedJson", {}).get("object_type", ""),
                    event.get("parsedJson", {}).get("system_id", ""),
                    event.get("timestampMs", 0) // 1000,
                    event.get("id", {}).get("txDigest", ""),
                    event.get("timestampMs", 0) // 1000,
                    json.dumps(event),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    async def poll(self, client: httpx.AsyncClient) -> int:
        """Poll for new events since last cursor. Returns count of new events stored."""
        try:
            result = await self.query_events(client, cursor=self._last_cursor)
            data = result.get("result", {})
            events = data.get("data", [])
            next_cursor = data.get("nextCursor")

            stored = 0
            for event in events:
                if self.store_event(event):
                    stored += 1

            if next_cursor:
                self._last_cursor = next_cursor

            if stored > 0:
                logger.info("Stored %d new chain events", stored)
            return stored

        except (httpx.HTTPError, KeyError) as e:
            logger.error("Chain poll failed: %s", e)
            return 0

    def get_last_block(self) -> int:
        """Get the highest block number we've processed."""
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

    async def get_startup_info(self, client: httpx.AsyncClient) -> dict:
        """Get chain info for health check — latest checkpoint."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sui_getLatestCheckpointSequenceNumber",
            }
            resp = await client.post(self.rpc_url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return {
                "latest_checkpoint": data.get("result"),
                "connected": True,
                "checked_at": int(time.time()),
            }
        except (httpx.HTTPError, KeyError) as e:
            logger.error("Sui RPC health check failed: %s", e)
            return {"connected": False, "error": str(e), "checked_at": int(time.time())}

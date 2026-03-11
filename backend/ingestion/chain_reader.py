"""Chain reader — reads on-chain logs from OP Sepolia via eth_getLogs.

Currently targets the MUD world contract on OP Sepolia (chain ID 11155420).
Architecture supports swapping to Sui RPC when migration happens.
"""

import json
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)

# How many blocks to scan per poll cycle (avoid huge RPC responses)
BLOCK_RANGE = 1000


class ChainReader:
    """Reads events from OP Sepolia RPC and writes to chain_events table."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        rpc_url: str,
        world_contract: str,
        timeout: int = 30,
    ):
        self.conn = conn
        self.rpc_url = rpc_url
        self.world_contract = world_contract
        self.timeout = timeout
        self._last_block: int | None = None

    async def get_block_number(self, client: httpx.AsyncClient) -> int:
        """Get the latest block number from the chain."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_blockNumber",
            "params": [],
        }
        resp = await client.post(self.rpc_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        result = resp.json().get("result", "0x0")
        return int(result, 16)

    async def get_logs(
        self,
        client: httpx.AsyncClient,
        from_block: int,
        to_block: int,
    ) -> list[dict]:
        """Fetch logs from the world contract in the given block range."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getLogs",
            "params": [
                {
                    "address": self.world_contract,
                    "fromBlock": hex(from_block),
                    "toBlock": hex(to_block),
                }
            ],
        }
        resp = await client.post(self.rpc_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            logger.error("RPC error: %s", data["error"])
            return []
        return data.get("result", [])

    def store_log(self, log: dict) -> bool:
        """Store a chain log entry. Returns True if new, False if duplicate."""
        tx_hash = log.get("transactionHash", "")
        log_index = log.get("logIndex", "0x0")
        event_id = f"{tx_hash}:{log_index}"

        block_hex = log.get("blockNumber", "0x0")
        block_number = int(block_hex, 16) if isinstance(block_hex, str) else block_hex

        # First topic is the event signature
        topics = log.get("topics", [])
        event_type = topics[0] if topics else ""

        # Extract object references from remaining topics
        object_id = topics[1] if len(topics) > 1 else ""

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
                    "",  # object_type resolved during detection
                    "",  # system_id resolved during detection
                    block_number,
                    tx_hash,
                    int(time.time()),  # chain timestamp resolved from block later
                    json.dumps(log),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    async def poll(self, client: httpx.AsyncClient) -> int:
        """Poll for new logs since last processed block. Returns count stored."""
        try:
            latest_block = await self.get_block_number(client)

            if self._last_block is None:
                # On first run, check DB for last processed block
                self._last_block = self.get_last_block()
                if self._last_block == 0:
                    # Start from recent blocks, not genesis
                    self._last_block = max(0, latest_block - BLOCK_RANGE)

            from_block = self._last_block + 1
            to_block = min(from_block + BLOCK_RANGE - 1, latest_block)

            if from_block > latest_block:
                return 0  # caught up

            logs = await self.get_logs(client, from_block, to_block)
            stored = 0
            for log in logs:
                if self.store_log(log):
                    stored += 1

            self._last_block = to_block

            if stored > 0:
                logger.info("Stored %d chain logs (blocks %d-%d)", stored, from_block, to_block)
            return stored

        except (httpx.HTTPError, KeyError, ValueError) as e:
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

    async def get_chain_info(self, client: httpx.AsyncClient) -> dict:
        """Get chain info for health check."""
        try:
            block = await self.get_block_number(client)
            return {
                "chain_id": 11155420,
                "latest_block": block,
                "last_processed": self._last_block or self.get_last_block(),
                "connected": True,
                "checked_at": int(time.time()),
            }
        except (httpx.HTTPError, ValueError) as e:
            logger.error("Chain health check failed: %s", e)
            return {
                "connected": False,
                "error": str(e),
                "checked_at": int(time.time()),
            }

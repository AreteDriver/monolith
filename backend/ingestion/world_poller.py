"""EVE Frontier World API poller — DISABLED (Cycle 5 Sui migration).

The World API domain (blockchain-gateway-stillness.live.tech.evefrontier.com)
was removed with the Sui migration on March 11, 2026. This module is stubbed
to prevent errors. Object tracking now happens via Sui events in chain_reader.py.

The snapshot storage and object upsert methods remain functional for use by
other components (demo seeding, detection engine).
"""

import json
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)


class WorldPoller:
    """Stubbed World API poller — polls disabled, storage methods preserved."""

    def __init__(self, conn: sqlite3.Connection, base_url: str = "", timeout: int = 30):
        self.conn = conn
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.timeout = timeout

    def store_snapshot(self, object_id: str, object_type: str, state_data: dict) -> None:
        """Store a world state snapshot."""
        now = int(time.time())
        self.conn.execute(
            """INSERT INTO world_states
               (object_id, object_type, state_data, snapshot_time, source)
               VALUES (?, ?, ?, ?, 'world_api')""",
            (object_id, object_type, json.dumps(state_data), now),
        )

    def _extract_owner(self, state_data: dict) -> str:
        """Extract owner from state data — handles nested owner objects."""
        owner = state_data.get("owner", "")
        if isinstance(owner, dict):
            return owner.get("address", owner.get("name", ""))
        return str(state_data.get("ownerId", owner))

    def _extract_system_id(self, state_data: dict) -> str:
        """Extract solar system ID — handles nested solarSystem objects."""
        solar = state_data.get("solarSystem", "")
        if isinstance(solar, dict):
            return str(solar.get("id", ""))
        return str(state_data.get("solarSystemId", state_data.get("systemId", "")))

    def upsert_object(self, object_id: str, object_type: str, state_data: dict) -> None:
        """Upsert tracked object with current state."""
        now = int(time.time())
        owner = self._extract_owner(state_data)
        system_id = self._extract_system_id(state_data)
        self.conn.execute(
            """INSERT INTO objects
               (object_id, object_type, current_state, current_owner,
                system_id, last_seen, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(object_id) DO UPDATE SET
                   current_state = excluded.current_state,
                   current_owner = excluded.current_owner,
                   system_id = excluded.system_id,
                   last_seen = excluded.last_seen""",
            (object_id, object_type, json.dumps(state_data), owner, system_id, now, now),
        )

    def _extract_id(self, item: dict) -> str:
        """Extract the primary ID from an API item."""
        return str(item.get("id", item.get("address", item.get("smartAssemblyId", ""))))

    async def poll_all(self, client: httpx.AsyncClient) -> dict[str, int]:
        """No-op — World API domain is offline since Sui migration."""
        return {}

    async def fetch_object_history(
        self,
        client: httpx.AsyncClient,
        object_id: str,
        object_type: str = "smartassemblies",
    ) -> dict | None:
        """Disabled — World API offline."""
        return None

    def get_snapshots(
        self,
        object_id: str,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict]:
        """Get stored snapshots for an object within a time window."""
        query = "SELECT * FROM world_states WHERE object_id = ?"
        params: list = [object_id]
        if start_time:
            query += " AND snapshot_time >= ?"
            params.append(start_time)
        if end_time:
            query += " AND snapshot_time <= ?"
            params.append(end_time)
        query += " ORDER BY snapshot_time ASC"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

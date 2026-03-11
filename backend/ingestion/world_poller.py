"""EVE Frontier World API poller — snapshots game state to world_states table."""

import json
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)

# World API endpoints to poll
ENDPOINTS = {
    "smartassemblies": "/smartassemblies",
    "characters": "/characters",
    "solarsystems": "/solarsystems",
    "types": "/types",
    "killmails": "/killmails",
}


class WorldPoller:
    """Polls EVE Frontier World API and stores snapshots."""

    def __init__(self, conn: sqlite3.Connection, base_url: str, timeout: int = 30):
        self.conn = conn
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def fetch_endpoint(self, client: httpx.AsyncClient, endpoint: str) -> list[dict]:
        """Fetch a single World API endpoint. Handles pagination wrapper."""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = await client.get(url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            # World API wraps lists in {"data": [...], "metadata": {...}}
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            if isinstance(data, list):
                return data
            return [data]
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            logger.error("World API fetch failed for %s: %s", endpoint, e)
            return []

    def store_snapshot(self, object_id: str, object_type: str, state_data: dict) -> None:
        """Store a world state snapshot."""
        now = int(time.time())
        self.conn.execute(
            """INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source)
               VALUES (?, ?, ?, ?, 'world_api')""",
            (object_id, object_type, json.dumps(state_data), now),
        )

    def upsert_object(self, object_id: str, object_type: str, state_data: dict) -> None:
        """Upsert tracked object with current state."""
        now = int(time.time())
        owner = state_data.get("ownerId", state_data.get("owner", ""))
        system_id = state_data.get("solarSystemId", state_data.get("systemId", ""))
        self.conn.execute(
            """INSERT INTO objects (object_id, object_type, current_state, current_owner,
                                    system_id, last_seen, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(object_id) DO UPDATE SET
                   current_state = excluded.current_state,
                   current_owner = excluded.current_owner,
                   system_id = excluded.system_id,
                   last_seen = excluded.last_seen""",
            (
                object_id,
                object_type,
                json.dumps(state_data),
                str(owner),
                str(system_id),
                now,
                now,
            ),
        )

    async def poll_all(self, client: httpx.AsyncClient) -> dict[str, int]:
        """Poll all endpoints and store snapshots. Returns counts per type."""
        counts: dict[str, int] = {}
        for obj_type, endpoint in ENDPOINTS.items():
            items = await self.fetch_endpoint(client, endpoint)
            count = 0
            for item in items:
                obj_id = str(
                    item.get("id", item.get("smartAssemblyId", item.get("characterId", "")))
                )
                if not obj_id:
                    continue
                self.store_snapshot(obj_id, obj_type, item)
                self.upsert_object(obj_id, obj_type, item)
                count += 1
            counts[obj_type] = count
        self.conn.commit()
        if any(counts.values()):
            logger.info("World poll complete: %s", counts)
        return counts

    async def fetch_object_history(
        self, client: httpx.AsyncClient, object_id: str, object_type: str = "smartassemblies"
    ) -> dict | None:
        """Fetch a single object's current state from World API."""
        url = f"{self.base_url}/{object_type}/{object_id}"
        try:
            resp = await client.get(url, timeout=self.timeout)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("World API object fetch failed for %s: %s", object_id, e)
            return None

    def get_snapshots(
        self, object_id: str, start_time: int | None = None, end_time: int | None = None
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

"""World API poller — fetches static reference data from EVE Frontier World API.

Post Sui migration (Cycle 5), dynamic data comes from chain events.
This module handles static/reference data only:
  - /v2/solarsystems — system names and coordinates
  - /v2/types — typeID → name mapping
  - /v2/tribes — tribe list and details
  - /health — API availability check

Snapshot storage and object upsert methods are preserved for use by
other components (demo seeding, detection engine, event processor).
"""

import json
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)

# World API v2 endpoints for static reference data
STATIC_ENDPOINTS: dict[str, str] = {
    "solarsystems": "/v2/solarsystems",
    "types": "/v2/types",
    "tribes": "/v2/tribes",
}

# Max items per page (World API pagination)
PAGE_LIMIT = 1000


class WorldPoller:
    """Fetches static reference data from the World API."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        base_url: str = "",
        timeout: int = 30,
    ):
        self.conn = conn
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.timeout = timeout

    # -- Static data polling --

    async def poll_static_data(self, client: httpx.AsyncClient) -> dict[str, int]:
        """Fetch all static reference data. Returns counts per type."""
        if not self.base_url:
            return {}

        counts: dict[str, int] = {}
        for data_type, endpoint in STATIC_ENDPOINTS.items():
            try:
                count = await self._fetch_paginated(client, data_type, endpoint)
                counts[data_type] = count
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("Failed to fetch %s: %s", data_type, e)
                counts[data_type] = 0

        total = sum(counts.values())
        if total > 0:
            logger.info("Fetched reference data: %s", counts)
        return counts

    async def _fetch_paginated(
        self,
        client: httpx.AsyncClient,
        data_type: str,
        endpoint: str,
    ) -> int:
        """Fetch a paginated World API endpoint and store results."""
        count = 0
        offset = 0

        while True:
            url = f"{self.base_url}{endpoint}"
            params = {"limit": PAGE_LIMIT, "offset": offset}
            resp = await client.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            body = resp.json()

            # World API wraps list data in {"data": [...], "metadata": {...}}
            items = body.get("data", body) if isinstance(body, dict) else body
            if not isinstance(items, list):
                items = [body]

            for item in items:
                self._store_reference(data_type, item)
                count += 1

            self.conn.commit()

            # Check pagination
            metadata = body.get("metadata", {}) if isinstance(body, dict) else {}
            total = metadata.get("total", 0)
            if not total or offset + PAGE_LIMIT >= total:
                break
            offset += PAGE_LIMIT

        return count

    def _store_reference(self, data_type: str, item: dict) -> None:
        """Store a reference data item."""
        data_id = str(item.get("id", item.get("solarSystemId", item.get("typeId", ""))))
        name = item.get("name", item.get("solarSystemName", ""))
        now = int(time.time())

        self.conn.execute(
            """INSERT INTO reference_data (data_type, data_id, name, data_json, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(data_type, data_id) DO UPDATE SET
                   name = excluded.name,
                   data_json = excluded.data_json,
                   updated_at = excluded.updated_at""",
            (data_type, data_id, name, json.dumps(item), now),
        )

    # -- Name resolution --

    def resolve_name(self, data_type: str, data_id: str) -> str:
        """Look up a name from reference data. Returns empty string if not found."""
        row = self.conn.execute(
            "SELECT name FROM reference_data WHERE data_type = ? AND data_id = ?",
            (data_type, data_id),
        ).fetchone()
        return row["name"] if row else ""

    def resolve_system_name(self, system_id: str) -> str:
        """Resolve a solar system ID to its name."""
        return self.resolve_name("solarsystems", system_id)

    def resolve_type_name(self, type_id: str) -> str:
        """Resolve a type ID to its name."""
        return self.resolve_name("types", type_id)

    # -- Health check --

    async def check_health(self, client: httpx.AsyncClient) -> dict:
        """Check World API availability."""
        if not self.base_url:
            return {"available": False, "reason": "no base_url configured"}
        try:
            resp = await client.get(
                f"{self.base_url}/health",
                timeout=5,
            )
            return {
                "available": resp.status_code == 200,
                "status_code": resp.status_code,
            }
        except httpx.HTTPError as e:
            return {"available": False, "error": str(e)}

    # -- Snapshot storage (preserved for event processor + detection engine) --

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

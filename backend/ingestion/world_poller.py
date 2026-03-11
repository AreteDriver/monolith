"""EVE Frontier World API poller — snapshots game state to world_states table."""

import json
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)

# World API v2 endpoints (stillness environment)
# (endpoint_path, page_size) — larger page size for smaller datasets
ENDPOINTS: dict[str, tuple[str, int]] = {
    "smartassemblies": ("/v2/smartassemblies", 100),
    "smartcharacters": ("/v2/smartcharacters", 100),
    "solarsystems": ("/v2/solarsystems", 500),
    "types": ("/v2/types", 500),
    "killmails": ("/v2/killmails", 100),
    "tribes": ("/v2/tribes", 100),
    "fuels": ("/v2/fuels", 100),
}

# Max pages to paginate (safety limit to avoid infinite loops)
MAX_PAGES = 500


class WorldPoller:
    """Polls EVE Frontier World API and stores snapshots."""

    def __init__(self, conn: sqlite3.Connection, base_url: str, timeout: int = 30):
        self.conn = conn
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def fetch_page(
        self, client: httpx.AsyncClient, endpoint: str, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        """Fetch a single page. Returns (items, total)."""
        url = f"{self.base_url}{endpoint}"
        params = {"limit": limit, "offset": offset}
        try:
            resp = await client.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "data" in data:
                total = data.get("metadata", {}).get("total", 0)
                return data["data"], total
            if isinstance(data, list):
                return data, len(data)
            return [data], 1
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            logger.error("World API fetch failed for %s (offset=%d): %s", endpoint, offset, e)
            return [], 0

    async def fetch_all_pages(
        self, client: httpx.AsyncClient, endpoint: str, page_size: int
    ) -> list[dict]:
        """Fetch all pages of an endpoint. Respects API pagination."""
        all_items: list[dict] = []
        offset = 0

        for _ in range(MAX_PAGES):
            items, total = await self.fetch_page(client, endpoint, page_size, offset)
            all_items.extend(items)
            offset += len(items)
            if not items or offset >= total:
                break

        return all_items

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
        """Poll all endpoints with full pagination. Returns counts per type."""
        counts: dict[str, int] = {}
        for obj_type, (endpoint, page_size) in ENDPOINTS.items():
            items = await self.fetch_all_pages(client, endpoint, page_size)
            count = 0
            for item in items:
                obj_id = self._extract_id(item)
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
        self,
        client: httpx.AsyncClient,
        object_id: str,
        object_type: str = "smartassemblies",
    ) -> dict | None:
        """Fetch a single object's current state from World API."""
        url = f"{self.base_url}/v2/{object_type}/{object_id}"
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

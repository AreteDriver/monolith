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
    "ships": "/v2/ships",
    "constellations": "/v2/constellations",
}

# Max items per page — keep low to limit per-request memory spike
PAGE_LIMIT = 200


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
        """Fetch all static reference data sequentially with pauses to limit memory."""
        import asyncio
        import gc

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
            # Release memory between endpoints
            gc.collect()
            await asyncio.sleep(2)

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

    def resolve_ship_name(self, ship_id: str) -> str:
        """Resolve a ship ID to its name."""
        return self.resolve_name("ships", ship_id)

    def get_ship_stats(self, ship_id: str) -> dict | None:
        """Get full ship stats from reference data. Returns None if not found."""
        row = self.conn.execute(
            "SELECT data_json FROM reference_data WHERE data_type = 'ships' AND data_id = ?",
            (ship_id,),
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["data_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    def resolve_constellation_name(self, constellation_id: str) -> str:
        """Resolve a constellation ID to its name."""
        return self.resolve_name("constellations", constellation_id)

    # -- Tribe cache --

    def store_tribe(self, tribe_data: dict) -> None:
        """Upsert tribe into tribe_cache with staleness tracking."""
        tribe_id = str(tribe_data.get("id", tribe_data.get("tribeId", "")))
        if not tribe_id:
            return

        name = tribe_data.get("name", "")
        name_short = tribe_data.get("nameShort", tribe_data.get("name_short", ""))
        member_count = tribe_data.get("memberCount", tribe_data.get("member_count", 0))
        tax_rate = tribe_data.get("taxRate", tribe_data.get("tax_rate", 0.0))
        now = int(time.time())

        # Check if tribe exists and if fields changed
        existing = self.conn.execute(
            "SELECT name, name_short, member_count, tax_rate FROM tribe_cache WHERE tribe_id = ?",
            (tribe_id,),
        ).fetchone()

        if existing:
            changed = (
                existing["name"] != name
                or existing["name_short"] != name_short
                or existing["member_count"] != member_count
                or existing["tax_rate"] != tax_rate
            )
            self.conn.execute(
                """UPDATE tribe_cache SET
                       name = ?, name_short = ?, member_count = ?, tax_rate = ?,
                       data_json = ?, last_confirmed_at = ?,
                       last_changed_at = CASE WHEN ? THEN ? ELSE last_changed_at END,
                       is_stale = 0
                   WHERE tribe_id = ?""",
                (
                    name,
                    name_short,
                    member_count,
                    tax_rate,
                    json.dumps(tribe_data),
                    now,
                    1 if changed else 0,
                    now,
                    tribe_id,
                ),
            )
        else:
            self.conn.execute(
                """INSERT INTO tribe_cache
                   (tribe_id, name, name_short, member_count, tax_rate,
                    data_json, first_seen_at, last_confirmed_at, is_stale)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    tribe_id,
                    name,
                    name_short,
                    member_count,
                    tax_rate,
                    json.dumps(tribe_data),
                    now,
                    now,
                ),
            )

    async def poll_tribes(self, client: httpx.AsyncClient) -> int:
        """Fetch /v2/tribes with pagination, store each, mark stale. Returns count."""
        if not self.base_url:
            return 0

        count = 0
        offset = 0
        seen_ids: set[str] = set()

        while True:
            url = f"{self.base_url}/v2/tribes"
            params = {"limit": PAGE_LIMIT, "offset": offset}
            resp = await client.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            body = resp.json()

            items = body.get("data", body) if isinstance(body, dict) else body
            if not isinstance(items, list):
                items = [body]

            for item in items:
                self.store_tribe(item)
                tribe_id = str(item.get("id", item.get("tribeId", "")))
                if tribe_id:
                    seen_ids.add(tribe_id)
                count += 1

            self.conn.commit()

            metadata = body.get("metadata", {}) if isinstance(body, dict) else {}
            total = metadata.get("total", 0)
            if not total or offset + PAGE_LIMIT >= total:
                break
            offset += PAGE_LIMIT

        # Mark tribes not seen in this fetch as stale if last_confirmed_at > 1 hour ago
        if seen_ids:
            stale_threshold = int(time.time()) - 3600
            placeholders = ",".join("?" * len(seen_ids))
            self.conn.execute(
                f"UPDATE tribe_cache SET is_stale = 1 "  # noqa: S608
                f"WHERE tribe_id NOT IN ({placeholders}) "
                f"AND last_confirmed_at < ?",
                [*seen_ids, stale_threshold],
            )
            self.conn.commit()

        return count

    def resolve_tribe(self, tribe_id: str) -> dict | None:
        """Return tribe from cache with staleness info."""
        row = self.conn.execute(
            """SELECT tribe_id, name, name_short, member_count, is_stale,
                      last_confirmed_at
               FROM tribe_cache WHERE tribe_id = ?""",
            (tribe_id,),
        ).fetchone()
        if not row:
            return None
        now = int(time.time())
        return {
            "name": row["name"],
            "name_short": row["name_short"],
            "member_count": row["member_count"],
            "is_stale": bool(row["is_stale"]),
            "last_confirmed_at": row["last_confirmed_at"],
            "staleness_seconds": now - row["last_confirmed_at"],
        }

    def get_stale_tribes(self) -> list[dict]:
        """Return all tribes marked stale."""
        rows = self.conn.execute(
            """SELECT tribe_id, name, name_short, member_count,
                      last_confirmed_at, last_changed_at
               FROM tribe_cache WHERE is_stale = 1
               ORDER BY last_confirmed_at ASC"""
        ).fetchall()
        return [dict(row) for row in rows]

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

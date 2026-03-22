"""Entity name resolver — replaces NEXUS dependency for name enrichment.

Provides a multi-tier resolution strategy:
  1. Local cache (entity_names table) — fast, no network
  2. Sui GraphQL bulk fetch — queries Character objects on-chain
  3. Truncated hex fallback — deterministic, never fails

Usage:
    resolver = NameResolver(conn, package_id)
    name = await resolver.resolve("0xabc123...")
    names = await resolver.resolve_batch(["0xabc1", "0xabc2", ...])
"""

import logging
import sqlite3
import time

import httpx

from backend.ingestion.graphql_queries import GET_CHARACTER_OBJECTS

logger = logging.getLogger(__name__)

# Sui GraphQL endpoint (Stillness = testnet)
SUI_GRAPHQL_URL = "https://graphql.testnet.sui.io/graphql"

# Cache entries older than this are considered stale and re-fetched
CACHE_TTL_SECONDS = 86400  # 24 hours


def truncate_hex(entity_id: str, length: int = 8) -> str:
    """Produce a human-readable truncation of a hex address.

    '0xabcdef1234567890' -> '0xabcd...7890'
    """
    if not entity_id or len(entity_id) <= length + 6:
        return entity_id
    prefix = entity_id[: length // 2 + 2]  # '0x' + half
    suffix = entity_id[-(length // 2) :]
    return f"{prefix}...{suffix}"


class NameResolver:
    """Resolves Sui addresses to human-readable names.

    Uses a tiered strategy: local DB cache -> Sui GraphQL -> hex truncation.
    Thread-safe via SQLite's WAL mode (reads don't block writes).
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        package_id: str,
        graphql_url: str = SUI_GRAPHQL_URL,
        timeout: int = 15,
        cache_ttl: int = CACHE_TTL_SECONDS,
    ):
        self.conn = conn
        self.package_id = package_id
        self.graphql_url = graphql_url
        self.timeout = timeout
        self.cache_ttl = cache_ttl

    # -- Public API --

    def resolve_cached(self, entity_id: str) -> str | None:
        """Check entity_names table for a cached name. Returns None on miss."""
        if not entity_id:
            return None
        row = self.conn.execute(
            "SELECT display_name, updated_at FROM entity_names WHERE entity_id = ?",
            (entity_id,),
        ).fetchone()
        if not row:
            return None
        return row["display_name"]

    def resolve_cached_batch(self, entity_ids: list[str]) -> dict[str, str]:
        """Batch lookup from entity_names table.

        Returns {entity_id: display_name} for all cache hits.
        """
        if not entity_ids:
            return {}
        results: dict[str, str] = {}
        # SQLite has a max variable limit (~999), chunk if needed
        chunk_size = 900
        for i in range(0, len(entity_ids), chunk_size):
            chunk = entity_ids[i : i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            rows = self.conn.execute(
                f"SELECT entity_id, display_name FROM entity_names "  # noqa: S608
                f"WHERE entity_id IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                results[row["entity_id"]] = row["display_name"]
        return results

    async def resolve(self, entity_id: str) -> str:
        """Resolve a single entity ID to a display name.

        Strategy: cache -> GraphQL single lookup -> truncated hex.
        """
        if not entity_id:
            return ""

        # Tier 1: cache
        cached = self.resolve_cached(entity_id)
        if cached is not None:
            return cached

        # Tier 2: GraphQL (fetch all characters, which populates cache)
        try:
            async with httpx.AsyncClient() as client:
                await self._fetch_characters(client)
        except Exception:
            logger.debug("GraphQL name fetch failed for %s", entity_id[:20])

        # Re-check cache after fetch
        cached = self.resolve_cached(entity_id)
        if cached is not None:
            return cached

        # Tier 3: truncated hex
        return truncate_hex(entity_id)

    async def resolve_batch(self, entity_ids: list[str]) -> dict[str, str]:
        """Resolve multiple entity IDs to display names.

        Checks cache first, fetches from GraphQL for misses, falls back
        to truncated hex for anything still unresolved.

        Returns {entity_id: display_name} for every input ID.
        """
        if not entity_ids:
            return {}

        # De-duplicate while preserving input
        unique_ids = list({eid for eid in entity_ids if eid})
        if not unique_ids:
            return {}

        # Tier 1: batch cache lookup
        results = self.resolve_cached_batch(unique_ids)
        missing = [eid for eid in unique_ids if eid not in results]

        if not missing:
            return results

        # Tier 2: GraphQL bulk fetch (populates cache for all characters)
        try:
            async with httpx.AsyncClient() as client:
                await self._fetch_characters(client)
        except Exception:
            logger.debug(
                "GraphQL batch name fetch failed, %d IDs unresolved",
                len(missing),
            )

        # Re-check cache for previously missing IDs
        newly_resolved = self.resolve_cached_batch(missing)
        results.update(newly_resolved)
        still_missing = [eid for eid in missing if eid not in newly_resolved]

        # Tier 3: truncated hex for anything still unresolved
        for eid in still_missing:
            results[eid] = truncate_hex(eid)

        return results

    def cache_name(
        self,
        entity_id: str,
        display_name: str,
        entity_type: str = "character",
        tribe_id: str = "",
    ) -> None:
        """Manually cache a name (e.g., from NEXUS or other sources)."""
        if not entity_id or not display_name:
            return
        self.conn.execute(
            """INSERT INTO entity_names (entity_id, display_name, entity_type,
                   tribe_id, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(entity_id) DO UPDATE SET
                   display_name = excluded.display_name,
                   entity_type = excluded.entity_type,
                   tribe_id = excluded.tribe_id,
                   updated_at = excluded.updated_at""",
            (entity_id, display_name, entity_type, tribe_id, int(time.time())),
        )
        self.conn.commit()

    def get_stale_ids(self) -> list[str]:
        """Return entity IDs with stale cache entries (older than TTL)."""
        cutoff = int(time.time()) - self.cache_ttl
        rows = self.conn.execute(
            "SELECT entity_id FROM entity_names WHERE updated_at < ?",
            (cutoff,),
        ).fetchall()
        return [row["entity_id"] for row in rows]

    def cache_stats(self) -> dict[str, int]:
        """Return cache statistics for monitoring."""
        total = self.conn.execute("SELECT COUNT(*) FROM entity_names").fetchone()[0]
        cutoff = int(time.time()) - self.cache_ttl
        stale = self.conn.execute(
            "SELECT COUNT(*) FROM entity_names WHERE updated_at < ?",
            (cutoff,),
        ).fetchone()[0]
        return {"total": total, "stale": stale, "fresh": total - stale}

    # -- Internal methods --

    async def _fetch_characters(
        self,
        client: httpx.AsyncClient,
        max_pages: int = 30,
    ) -> int:
        """Bulk fetch Character objects from Sui GraphQL and cache names.

        Queries all on-chain Character Move objects. Each character has
        a metadata.name field containing the player-chosen display name.

        Returns count of names stored/updated.
        """
        character_type = f"{self.package_id}::character::Character"
        cursor = None
        total_stored = 0

        for page in range(max_pages):
            try:
                data = await self._graphql_query(
                    client,
                    GET_CHARACTER_OBJECTS,
                    {"type": character_type, "first": 50, "after": cursor},
                )
            except (httpx.HTTPError, ValueError, KeyError) as e:
                logger.warning("Character name fetch failed (page %d): %s", page, e)
                break

            objects = data.get("objects", {})
            nodes = objects.get("nodes", [])

            for node in nodes:
                contents = node.get("asMoveObject", {}).get("contents", {}).get("json", {})
                if not isinstance(contents, dict):
                    continue

                character_address = contents.get("character_address", "")
                metadata = contents.get("metadata", {})
                name = ""
                if isinstance(metadata, dict):
                    name = metadata.get("name", "")

                if not character_address or not name:
                    continue

                tribe_id = str(contents.get("tribe_id", ""))

                self.conn.execute(
                    """INSERT INTO entity_names
                       (entity_id, display_name, entity_type, tribe_id, updated_at)
                       VALUES (?, ?, 'character', ?, ?)
                       ON CONFLICT(entity_id) DO UPDATE SET
                           display_name = excluded.display_name,
                           tribe_id = excluded.tribe_id,
                           updated_at = excluded.updated_at""",
                    (character_address, name, tribe_id, int(time.time())),
                )
                total_stored += 1

            page_info = objects.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        if total_stored > 0:
            self.conn.commit()
            logger.info("NameResolver: cached %d character names from Sui", total_stored)

        return total_stored

    async def _graphql_query(
        self,
        client: httpx.AsyncClient,
        query: str,
        variables: dict | None = None,
    ) -> dict:
        """Execute a GraphQL query against Sui."""
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = await client.post(
            self.graphql_url,
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get("errors"):
            errors = result["errors"]
            raise ValueError(f"GraphQL query failed: {errors[0].get('message', 'unknown')}")

        return result.get("data", {})

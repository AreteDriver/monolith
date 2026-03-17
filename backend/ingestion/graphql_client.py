"""Sui GraphQL client for enriched on-chain queries.

Supplements the RPC-based ChainReader with GraphQL queries for:
- Location Registry dynamic fields (object → system mapping)
- Killmail objects with solar_system_id
- Event queries by module

Uses patterns from Econmartin's jotunn.lol API reference (2026-03-15).
"""

import json
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)

# Sui GraphQL endpoint (Stillness = testnet)
SUI_GRAPHQL_URL = "https://graphql.testnet.sui.io/graphql"

# Stillness registry addresses (confirmed via Econmartin + memory)
LOCATION_REGISTRY = "0xc87dca9c6b2c95e4a0cbe1f8f9eeff50171123f176fbfdc7b49eef4824fc596b"
KILLMAIL_REGISTRY = "0x7fd9a32d0bbe7b1cfbb7140b1dd4312f54897de946c399edb21c3a12e52ce283"

# ── GraphQL Queries ──────────────────────────────────────────────────────────

GET_OBJECT_WITH_DYNFIELDS = """
query GetObject($address: SuiAddress!) {
  object(address: $address) {
    address
    version
    asMoveObject {
      contents {
        type { repr }
        json
      }
      dynamicFields {
        nodes {
          name { json type { repr } }
          value {
            ... on MoveValue {
              json
            }
          }
        }
      }
    }
  }
}
"""

GET_EVENTS_BY_MODULE = """
query GetEvents($module: String!, $first: Int, $after: String) {
  events(filter: { module: $module }, first: $first, after: $after) {
    nodes {
      contents {
        json
        type { repr }
      }
      timestamp
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

GET_CHARACTER_OBJECTS = """
query GetCharacters($type: String!, $first: Int, $after: String) {
  objects(
    first: $first,
    after: $after,
    filter: { type: $type }
  ) {
    nodes {
      asMoveObject {
        contents { json }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

GET_OBJECT_VERSIONS = """
query GetObjectVersions($address: SuiAddress!, $first: Int) {
  objectVersions(address: $address, first: $first) {
    nodes {
      version
      digest
      asMoveObject {
        contents { json }
      }
    }
    pageInfo { hasNextPage }
  }
}
"""

GET_OWNED_OBJECTS = """
query GetOwnedObjects($owner: SuiAddress!, $first: Int, $after: String) {
  objects(filter: { owner: $owner }, first: $first, after: $after) {
    nodes {
      address
      version
      asMoveObject {
        contents {
          json
          type { repr }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

GET_TRANSACTIONS = """
query GetTransactions($address: SuiAddress!, $first: Int, $after: String) {
  transactions(filter: { affectedAddress: $address }, first: $first, after: $after) {
    nodes {
      digest
      effects {
        status
        timestamp
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

GET_KILLMAIL_OBJECTS = """
query GetKillmailObjects($type: String!, $first: Int, $after: String) {
  objects(
    first: $first,
    after: $after,
    filter: { type: $type }
  ) {
    nodes {
      address
      version
      asMoveObject {
        contents { json }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


class SuiGraphQLClient:
    """Async client for Sui GraphQL API queries."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        package_id: str,
        graphql_url: str = SUI_GRAPHQL_URL,
        timeout: int = 15,
    ):
        self.conn = conn
        self.package_id = package_id
        self.graphql_url = graphql_url
        self.timeout = timeout

    async def _query(
        self,
        client: httpx.AsyncClient,
        query: str,
        variables: dict | None = None,
    ) -> dict:
        """Execute a GraphQL query and return the data dict."""
        payload = {"query": query}
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
            logger.error("GraphQL errors: %s", json.dumps(errors)[:200])
            raise ValueError(f"GraphQL query failed: {errors[0].get('message', 'unknown')}")

        return result.get("data", {})

    async def query_location_registry(self, client: httpx.AsyncClient) -> dict[str, str]:
        """Query Location Registry for object_id → solar_system_id mappings.

        Returns a dict of {object_id: system_id} from the registry's
        dynamic fields. The registry is a Move Table with ~12-19 entries
        (only objects whose owners have actively revealed location).
        """
        mappings: dict[str, str] = {}

        try:
            data = await self._query(
                client, GET_OBJECT_WITH_DYNFIELDS, {"address": LOCATION_REGISTRY}
            )
        except Exception as e:
            logger.warning("Location Registry query failed: %s", e)
            return mappings

        obj = data.get("object")
        if not obj:
            logger.warning("Location Registry object not found (may be pruned)")
            return mappings

        move_obj = obj.get("asMoveObject", {})
        dyn_fields = move_obj.get("dynamicFields", {}).get("nodes", [])

        for field in dyn_fields:
            try:
                name_json = field.get("name", {}).get("json")
                value_json = field.get("value", {}).get("json")
                if not name_json or not value_json:
                    continue

                # Dynamic field name is the object_id (or contains it)
                object_id = name_json if isinstance(name_json, str) else str(name_json)

                # Value contains location data with solar_system_id
                if isinstance(value_json, dict):
                    system_id = (
                        value_json.get("solar_system_id") or value_json.get("solarSystemId") or ""
                    )
                    if system_id:
                        mappings[object_id] = str(system_id)
                elif isinstance(value_json, str):
                    # May be a simple system_id string
                    mappings[object_id] = value_json
            except (KeyError, TypeError):
                continue

        if mappings:
            logger.info("Location Registry: resolved %d object→system mappings", len(mappings))
        return mappings

    async def query_killmail_locations(
        self,
        client: httpx.AsyncClient,
        max_pages: int = 10,
    ) -> dict[str, str]:
        """Query on-chain Killmail objects for solar_system_id data.

        Each Killmail object has killer_id, victim_id, and solar_system_id.
        Returns {object_id: system_id} for both victims and killers.
        """
        killmail_type = f"{self.package_id}::killmail::Killmail"
        mappings: dict[str, str] = {}
        cursor = None

        for _ in range(max_pages):
            try:
                data = await self._query(
                    client,
                    GET_KILLMAIL_OBJECTS,
                    {"type": killmail_type, "first": 50, "after": cursor},
                )
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("Killmail objects query failed: %s", e)
                break

            objects = data.get("objects", {})
            nodes = objects.get("nodes", [])

            for node in nodes:
                contents = node.get("asMoveObject", {}).get("contents", {}).get("json", {})
                if not isinstance(contents, dict):
                    continue

                system_id = str(
                    contents.get("solar_system_id") or contents.get("solarSystemId") or ""
                )
                if not system_id:
                    continue

                # Map both killer and victim to this system
                for field in ("victim_id", "killer_id"):
                    obj_id = contents.get(field)
                    if obj_id:
                        mappings[str(obj_id)] = system_id

            page_info = objects.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        if mappings:
            logger.info("Killmail objects: resolved %d object→system mappings", len(mappings))
        return mappings

    async def query_location_events(
        self,
        client: httpx.AsyncClient,
        max_pages: int = 5,
    ) -> dict[str, str]:
        """Query LocationRevealedEvent via GraphQL events API.

        Supplements the RPC-based event polling by querying the location
        module events directly via GraphQL.
        """
        module = f"{self.package_id}::location"
        mappings: dict[str, str] = {}
        cursor = None

        for _ in range(max_pages):
            try:
                data = await self._query(
                    client,
                    GET_EVENTS_BY_MODULE,
                    {"module": module, "first": 50, "after": cursor},
                )
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("Location events query failed: %s", e)
                break

            events_data = data.get("events", {})
            nodes = events_data.get("nodes", [])

            for node in nodes:
                contents = node.get("contents", {}).get("json", {})
                if not isinstance(contents, dict):
                    continue

                object_id = str(contents.get("object_id", ""))
                system_id = str(
                    contents.get("solar_system_id") or contents.get("solarSystemId") or ""
                )
                if object_id and system_id:
                    mappings[object_id] = system_id

            page_info = events_data.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        if mappings:
            logger.info("Location events: resolved %d object→system mappings", len(mappings))
        return mappings

    async def fetch_character_names(
        self,
        client: httpx.AsyncClient,
        max_pages: int = 30,
    ) -> int:
        """Bulk fetch all Character objects from Sui for name resolution.

        Queries on-chain Character Move objects and extracts metadata.name.
        Stores results in entity_names table. ~1,300 characters, ~27 pages.

        This replaces the NEXUS dependency for entity name enrichment.
        """
        character_type = f"{self.package_id}::character::Character"
        cursor = None
        total_stored = 0

        for page in range(max_pages):
            try:
                data = await self._query(
                    client,
                    GET_CHARACTER_OBJECTS,
                    {"type": character_type, "first": 50, "after": cursor},
                )
            except Exception as e:
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
                    """INSERT INTO entity_names (entity_id, display_name, entity_type,
                           tribe_id, updated_at)
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
            logger.info("Character names: stored %d names from Sui objects", total_stored)

        return total_stored

    async def audit_object_versions(self, client: httpx.AsyncClient, max_objects: int = 50) -> int:
        """Fetch version history for tracked objects and store for auditing.

        Queries objectVersions for objects in the objects table that have
        recent activity. Stores each version snapshot for state diff analysis.
        Returns count of new versions stored.
        """
        # Get objects with recent events (last 24h)
        cutoff = int(time.time()) - 86400
        rows = self.conn.execute(
            "SELECT object_id FROM objects WHERE last_seen >= ? LIMIT ?",
            (cutoff, max_objects),
        ).fetchall()

        total_stored = 0
        for row in rows:
            object_id = row["object_id"]
            # Skip non-Sui addresses
            if not object_id.startswith("0x"):
                continue
            try:
                data = await self._query(
                    client,
                    GET_OBJECT_VERSIONS,
                    {"address": object_id, "first": 10},
                )
            except Exception as e:
                logger.debug("Object version fetch failed for %s: %s", object_id[:16], e)
                continue

            versions = data.get("objectVersions", {}).get("nodes", [])
            for v in versions:
                version_num = v.get("version", 0)
                digest = v.get("digest", "")
                state = v.get("asMoveObject", {}).get("contents", {}).get("json", {})

                try:
                    self.conn.execute(
                        """INSERT OR IGNORE INTO object_versions
                           (object_id, version, digest, state_json, fetched_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            object_id,
                            version_num,
                            digest,
                            json.dumps(state) if state else "",
                            int(time.time()),
                        ),
                    )
                    total_stored += 1
                except Exception:
                    logger.debug("Failed to store version for %s", object_id[:16])

        if total_stored > 0:
            self.conn.commit()
            logger.info("Object versions: stored %d version snapshots", total_stored)
        return total_stored

    async def poll_config_singletons(self, client: httpx.AsyncClient) -> int:
        """Poll config singleton objects for version changes.

        Tracks Energy, Fuel, and Gate config objects. Version bumps without
        announced patches indicate potential exploits or bugs.
        """
        configs = {
            "energy": "0xd77693d0df5656d68b1b833e2a23cc81eb3875d8d767e7bd249adde82bdbc952",
            "fuel": "0x4fcf28a9be750d242bc5d2f324429e31176faecb5b84f0af7dff3a2a6e243550",
            "gate": "0xd6d9230faec0230c839a534843396e97f5f79bdbd884d6d5103d0125dc135827",
        }
        stored = 0
        for config_type, address in configs.items():
            try:
                data = await self._query(client, GET_OBJECT_WITH_DYNFIELDS, {"address": address})
            except Exception as e:
                logger.debug("Config poll failed for %s: %s", config_type, e)
                continue

            obj = data.get("object")
            if not obj:
                continue

            version = obj.get("version", 0)
            state = obj.get("asMoveObject", {}).get("contents", {}).get("json", {})

            try:
                self.conn.execute(
                    """INSERT OR IGNORE INTO config_snapshots
                       (config_type, config_address, version, state_json, fetched_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        config_type,
                        address,
                        version,
                        json.dumps(state) if state else "",
                        int(time.time()),
                    ),
                )
                stored += 1
            except Exception:
                logger.debug("Failed to store config snapshot for %s", config_type)

        if stored > 0:
            self.conn.commit()
            logger.info("Config snapshots: stored %d new versions", stored)
        return stored

    async def profile_wallet_activity(
        self, client: httpx.AsyncClient, max_wallets: int = 30
    ) -> int:
        """Build activity profiles for wallets seen in recent events.

        Queries transaction history per wallet and computes interval statistics
        for bot detection. Regular intervals (low stddev) = likely bot.
        """
        import statistics

        # Get distinct senders from recent chain events
        cutoff = int(time.time()) - 86400
        rows = self.conn.execute(
            """SELECT DISTINCT json_extract(raw_json, '$.sender') as sender
               FROM chain_events
               WHERE timestamp >= ? AND raw_json LIKE '%"sender"%'
               LIMIT ?""",
            (cutoff, max_wallets),
        ).fetchall()

        updated = 0
        for row in rows:
            wallet = row["sender"]
            if not wallet or not wallet.startswith("0x"):
                continue

            try:
                data = await self._query(
                    client,
                    GET_TRANSACTIONS,
                    {"address": wallet, "first": 50},
                )
            except Exception:
                logger.debug("Transaction query failed for %s", wallet[:16])
                continue

            txs = data.get("transactions", {}).get("nodes", [])
            if len(txs) < 3:
                continue

            # Extract timestamps and compute intervals
            timestamps = []
            for tx in txs:
                ts_str = tx.get("effects", {}).get("timestamp")
                if ts_str:
                    # Sui timestamps are epoch milliseconds as string
                    try:
                        timestamps.append(
                            int(ts_str) // 1000 if int(ts_str) > 1e12 else int(ts_str)
                        )
                    except (ValueError, TypeError):
                        continue

            timestamps.sort()
            if len(timestamps) < 3:
                continue

            intervals = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
            avg_interval = statistics.mean(intervals)
            stddev = statistics.stdev(intervals) if len(intervals) > 1 else 0.0

            self.conn.execute(
                """INSERT INTO wallet_activity
                   (wallet_address, tx_count, avg_interval_seconds, interval_stddev,
                    first_tx, last_tx, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(wallet_address) DO UPDATE SET
                       tx_count = excluded.tx_count,
                       avg_interval_seconds = excluded.avg_interval_seconds,
                       interval_stddev = excluded.interval_stddev,
                       last_tx = excluded.last_tx,
                       updated_at = excluded.updated_at""",
                (
                    wallet,
                    len(timestamps),
                    avg_interval,
                    stddev,
                    timestamps[0],
                    timestamps[-1],
                    int(time.time()),
                ),
            )
            updated += 1

        if updated > 0:
            self.conn.commit()
            logger.info("Wallet profiles: updated %d activity profiles", updated)
        return updated

    async def scan_owned_objects(
        self, client: httpx.AsyncClient, max_wallets: int = 20
    ) -> dict[str, int]:
        """Scan object ownership for concentration analysis.

        Returns {wallet: object_count} for wallets with recent activity.
        Stores results in wallet_activity.tx_count for concentration checks.
        """
        cutoff = int(time.time()) - 86400
        rows = self.conn.execute(
            """SELECT DISTINCT json_extract(raw_json, '$.sender') as sender
               FROM chain_events
               WHERE timestamp >= ? AND raw_json LIKE '%"sender"%'
               LIMIT ?""",
            (cutoff, max_wallets),
        ).fetchall()

        ownership: dict[str, int] = {}
        for row in rows:
            wallet = row["sender"]
            if not wallet or not wallet.startswith("0x"):
                continue

            try:
                data = await self._query(
                    client,
                    GET_OWNED_OBJECTS,
                    {"owner": wallet, "first": 50},
                )
            except Exception:
                logger.debug("Owned objects query failed for %s", wallet[:16])
                continue

            count = len(data.get("objects", {}).get("nodes", []))
            if count > 0:
                ownership[wallet] = count

        if ownership:
            logger.info(
                "Ownership scan: %d wallets, max %d objects",
                len(ownership),
                max(ownership.values()),
            )
        return ownership

    async def enrich_locations(self, client: httpx.AsyncClient) -> int:
        """Run all location enrichment sources and update the database.

        Queries three sources in order of reliability:
        1. Location Registry (direct on-chain state)
        2. LocationRevealedEvent (historical events via GraphQL)
        3. Killmail objects (system_id from kill data)

        Returns the number of objects updated.
        """
        all_mappings: dict[str, str] = {}

        # Source 1: Location Registry (most authoritative)
        registry_mappings = await self.query_location_registry(client)
        all_mappings.update(registry_mappings)

        # Source 2: Location events via GraphQL
        event_mappings = await self.query_location_events(client)
        # Don't overwrite registry data
        for k, v in event_mappings.items():
            if k not in all_mappings:
                all_mappings[k] = v

        # Source 3: Killmail objects
        killmail_mappings = await self.query_killmail_locations(client)
        for k, v in killmail_mappings.items():
            if k not in all_mappings:
                all_mappings[k] = v

        if not all_mappings:
            logger.debug("GraphQL enrichment: no new location mappings found")
            return 0

        # Apply to objects table
        updated = 0
        for object_id, system_id in all_mappings.items():
            result = self.conn.execute(
                "UPDATE objects SET system_id = ? "
                "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                (system_id, object_id),
            )
            updated += result.rowcount

            # Also update anomalies referencing this object
            self.conn.execute(
                "UPDATE anomalies SET system_id = ? "
                "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                (system_id, object_id),
            )

        if updated > 0:
            self.conn.commit()
            logger.info(
                "GraphQL enrichment: updated %d objects from %d total mappings "
                "(registry=%d, events=%d, killmails=%d)",
                updated,
                len(all_mappings),
                len(registry_mappings),
                len(event_mappings),
                len(killmail_mappings),
            )

        return updated

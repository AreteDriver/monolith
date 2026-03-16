"""Backfill system_id for objects by querying Sui Location Registry.

The Location Registry (0xc87d...) holds a Move Table mapping object IDs
to solar system locations. Individual objects do NOT self-report their
location — it lives exclusively in this registry.

Strategy:
1. Query Location Registry to get the locations Table object ID
2. Query that Table's dynamic fields — each is keyed by an object address
   and contains the solar_system_id
3. Match against our objects/anomalies missing system_id

Usage:
    python scripts/backfill_locations.py [--db /data/monolith.db]
"""

import asyncio
import json
import logging
import sqlite3
import sys

import httpx

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

SUI_GRAPHQL_URL = "https://graphql.testnet.sui.io/graphql"

LOCATION_REGISTRY = "0xc87dca9c6b2c95e4a0cbe1f8f9eeff50171123f176fbfdc7b49eef4824fc596b"

# Step 1: Get the Location Registry object to find the locations Table ID
GET_REGISTRY_QUERY = """
query GetRegistry($address: SuiAddress!) {
  object(address: $address) {
    address
    asMoveObject {
      contents {
        type { repr }
        json
      }
      dynamicFields(first: 50) {
        nodes {
          name { json type { repr } }
          value {
            ... on MoveValue { json }
            ... on MoveObject {
              address
              contents { json type { repr } }
            }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

# Step 2: Query a Table's dynamic fields (paginated) to get object→location mappings
GET_TABLE_ENTRIES_QUERY = """
query GetTableEntries($address: SuiAddress!, $first: Int!, $after: String) {
  object(address: $address) {
    dynamicFields(first: $first, after: $after) {
      nodes {
        name { json type { repr } }
        value {
          ... on MoveValue { json }
          ... on MoveObject {
            address
            contents { json type { repr } }
          }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

# Step 3: Fallback — query individual object for location in its own fields
GET_OBJECT_QUERY = """
query GetObject($address: SuiAddress!) {
  object(address: $address) {
    address
    asMoveObject {
      contents {
        type { repr }
        json
      }
      dynamicFields(first: 10) {
        nodes {
          name { json type { repr } }
          value {
            ... on MoveValue { json }
          }
        }
      }
    }
  }
}
"""


async def graphql(client: httpx.AsyncClient, query: str, variables: dict) -> dict:
    resp = await client.post(
        SUI_GRAPHQL_URL,
        json={"query": query, "variables": variables},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        logger.warning("GraphQL errors: %s", data["errors"][:1])
    return data.get("data", {})


def extract_system_id(val_json: dict | str | None) -> str | None:
    """Extract solar_system_id from a dynamic field value."""
    if val_json is None:
        return None
    if isinstance(val_json, str):
        try:
            val_json = json.loads(val_json)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(val_json, dict):
        return None

    # Direct fields
    for key in ("solar_system_id", "solarSystemId", "system_id", "systemId"):
        if key in val_json:
            v = str(val_json[key])
            if v and v != "0":
                return v

    # Nested location object
    location = val_json.get("location", {})
    if isinstance(location, dict):
        for key in ("solar_system_id", "solarSystemId"):
            if key in location:
                v = str(location[key])
                if v and v != "0":
                    return v

    return None


async def fetch_location_registry(client: httpx.AsyncClient) -> dict[str, str]:
    """Fetch all object→system_id mappings from the Location Registry."""
    logger.info("Querying Location Registry %s...", LOCATION_REGISTRY[:16])

    data = await graphql(client, GET_REGISTRY_QUERY, {"address": LOCATION_REGISTRY})
    obj = data.get("object", {})
    move = obj.get("asMoveObject", {})
    contents = move.get("contents", {})
    registry_json = contents.get("json", {})

    logger.info("Registry contents keys: %s", list(registry_json.keys()) if registry_json else "empty")

    # The registry has a `locations` field which is a Move Table { id, size }
    locations_table = registry_json.get("locations", {})
    table_id = None
    if isinstance(locations_table, dict):
        table_id = locations_table.get("id")
        table_size = locations_table.get("size", "?")
        logger.info("Locations table ID: %s, size: %s", table_id, table_size)

    # Also check dynamic fields on the registry itself
    mappings: dict[str, str] = {}
    dfs = move.get("dynamicFields", {}).get("nodes", [])
    for df in dfs:
        name_json = df.get("name", {}).get("json")
        val = df.get("value", {})
        val_json = val.get("json") if isinstance(val, dict) else None
        # If value is a MoveObject, check its contents
        if val_json is None and isinstance(val, dict):
            val_json = val.get("contents", {}).get("json")

        if isinstance(name_json, str) and name_json.startswith("0x"):
            sid = extract_system_id(val_json)
            if sid:
                mappings[name_json] = sid

    logger.info("Found %d mappings from registry dynamic fields", len(mappings))

    # If we found a table ID, paginate through its entries
    if table_id:
        cursor = None
        page = 0
        while True:
            page += 1
            table_data = await graphql(client, GET_TABLE_ENTRIES_QUERY, {
                "address": table_id,
                "first": 50,
                "after": cursor,
            })
            table_obj = table_data.get("object", {})
            if not table_obj:
                logger.warning("Table object %s not found", table_id)
                break

            entries = table_obj.get("dynamicFields", {})
            nodes = entries.get("nodes", [])
            page_info = entries.get("pageInfo", {})

            for node in nodes:
                name_json = node.get("name", {}).get("json")
                val = node.get("value", {})
                val_json = val.get("json") if isinstance(val, dict) else None
                if val_json is None and isinstance(val, dict):
                    val_json = val.get("contents", {}).get("json")

                # Name could be the object address directly or wrapped
                obj_addr = None
                if isinstance(name_json, str) and name_json.startswith("0x"):
                    obj_addr = name_json
                elif isinstance(name_json, dict):
                    # Could be { "addr": "0x..." } or similar
                    for v in name_json.values():
                        if isinstance(v, str) and v.startswith("0x"):
                            obj_addr = v
                            break

                if obj_addr:
                    sid = extract_system_id(val_json)
                    if sid:
                        mappings[obj_addr] = sid

            logger.info("  Table page %d: %d entries, total mappings: %d", page, len(nodes), len(mappings))

            if not page_info.get("hasNextPage") or not nodes:
                break
            cursor = page_info.get("endCursor")
            await asyncio.sleep(0.2)

    return mappings


async def main():
    db_path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--db" else "data/monolith.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get unique object_ids from anomalies missing system_id (only 0x addresses)
    rows = conn.execute(
        "SELECT DISTINCT object_id FROM anomalies "
        "WHERE (system_id IS NULL OR system_id = '') "
        "AND object_id LIKE '0x%'"
    ).fetchall()
    needed = {r["object_id"] for r in rows}
    logger.info("Found %d unique 0x objects needing system_id", len(needed))

    if not needed:
        logger.info("Nothing to backfill")
        return

    async with httpx.AsyncClient() as client:
        # Try Location Registry first (bulk approach)
        mappings = await fetch_location_registry(client)
        logger.info("Location Registry returned %d total mappings", len(mappings))

        # Match against our needed objects
        matched = 0
        for oid in needed:
            sid = mappings.get(oid)
            if sid:
                conn.execute(
                    "UPDATE objects SET system_id = ? "
                    "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                    (sid, oid),
                )
                cur = conn.execute(
                    "UPDATE anomalies SET system_id = ? "
                    "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                    (sid, oid),
                )
                matched += cur.rowcount
                logger.info("  %s... → system %s", oid[:16], sid)

        logger.info("Matched %d anomalies from registry", matched)

        # Fallback: try individual object queries for unresolved
        unresolved = needed - set(mappings.keys())
        if unresolved:
            logger.info("Trying individual queries for %d unresolved objects...", len(unresolved))
            fallback_resolved = 0
            for i, oid in enumerate(sorted(unresolved)):
                try:
                    data = await graphql(client, GET_OBJECT_QUERY, {"address": oid})
                    obj = data.get("object")
                    if not obj:
                        continue
                    move = obj.get("asMoveObject", {})
                    obj_json = move.get("contents", {}).get("json", {})
                    sid = extract_system_id(obj_json)
                    if not sid:
                        # Check dynamic fields
                        for df in move.get("dynamicFields", {}).get("nodes", []):
                            sid = extract_system_id(df.get("value", {}).get("json"))
                            if sid:
                                break
                    if sid:
                        conn.execute(
                            "UPDATE objects SET system_id = ? "
                            "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                            (sid, oid),
                        )
                        conn.execute(
                            "UPDATE anomalies SET system_id = ? "
                            "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                            (sid, oid),
                        )
                        fallback_resolved += 1
                        logger.info("  [fallback %d] %s... → system %s", i + 1, oid[:16], sid)
                except Exception as e:
                    logger.warning("  [fallback %d] %s... failed: %s", i + 1, oid[:16], e)

                if (i + 1) % 20 == 0:
                    await asyncio.sleep(0.5)

            logger.info("Fallback resolved %d additional objects", fallback_resolved)
            matched += fallback_resolved

    conn.commit()
    conn.close()
    logger.info("Total: resolved %d anomalies with real system_id from chain", matched)


if __name__ == "__main__":
    asyncio.run(main())

"""Backfill system_id for objects by querying Sui Location Registry.

Finds objects/anomalies missing system_id, queries the Sui testnet
GraphQL endpoint for their location data, and updates the DB.

Usage:
    python scripts/backfill_locations.py [--db data/monolith.db]
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

# Query object to get its location from dynamic fields
GET_OBJECT_QUERY = """
query GetObject($address: SuiAddress!) {
  object(address: $address) {
    address
    asMoveObject {
      contents {
        type { repr }
        json
      }
      dynamicFields {
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


async def resolve_location(client: httpx.AsyncClient, object_id: str) -> str | None:
    """Query Sui GraphQL for an object's solar_system_id."""
    try:
        resp = await client.post(
            SUI_GRAPHQL_URL,
            json={"query": GET_OBJECT_QUERY, "variables": {"address": object_id}},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        obj = data.get("data", {}).get("object")
        if not obj:
            return None

        move = obj.get("asMoveObject", {})
        contents = move.get("contents", {})
        obj_json = contents.get("json", {})

        # Check direct fields
        for key in ("solar_system_id", "solarSystemId", "system_id", "systemId"):
            if key in obj_json:
                return str(obj_json[key])

        # Check location nested object
        location = obj_json.get("location", {})
        if isinstance(location, dict):
            for key in ("solar_system_id", "solarSystemId"):
                if key in location:
                    return str(location[key])

        # Check dynamic fields for location data
        for df in move.get("dynamicFields", {}).get("nodes", []):
            val = df.get("value", {})
            if isinstance(val, dict) and "json" in val:
                vj = val["json"]
                if isinstance(vj, dict):
                    for key in ("solar_system_id", "solarSystemId"):
                        if key in vj:
                            return str(vj[key])

        return None
    except Exception as e:
        logger.warning("  Failed to resolve %s: %s", object_id[:16], e)
        return None


async def main():
    db_path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--db" else "data/monolith.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get unique object_ids from anomalies missing system_id
    rows = conn.execute(
        "SELECT DISTINCT object_id FROM anomalies "
        "WHERE (system_id IS NULL OR system_id = '') AND object_id != ''"
    ).fetchall()

    object_ids = [r["object_id"] for r in rows]
    logger.info("Found %d unique objects missing system_id", len(object_ids))

    if not object_ids:
        logger.info("Nothing to backfill")
        return

    resolved = 0
    async with httpx.AsyncClient() as client:
        for i, oid in enumerate(object_ids):
            system_id = await resolve_location(client, oid)
            if system_id:
                # Update objects table
                conn.execute(
                    "UPDATE objects SET system_id = ? "
                    "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                    (system_id, oid),
                )
                # Update anomalies table
                cur = conn.execute(
                    "UPDATE anomalies SET system_id = ? "
                    "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                    (system_id, oid),
                )
                resolved += cur.rowcount
                logger.info("  [%d/%d] %s... → system %s (%d anomalies)", i + 1, len(object_ids), oid[:16], system_id, cur.rowcount)
            else:
                logger.info("  [%d/%d] %s... → no location found", i + 1, len(object_ids), oid[:16])

            # Rate limit: don't hammer Sui
            if (i + 1) % 10 == 0:
                await asyncio.sleep(0.5)

    conn.commit()
    conn.close()
    logger.info("Resolved %d anomalies across %d objects", resolved, len(object_ids))


if __name__ == "__main__":
    asyncio.run(main())

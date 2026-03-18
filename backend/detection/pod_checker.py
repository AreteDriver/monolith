"""POD checker — verifies local state against on-chain object state via GraphQL.

Rules:
  P1 — Chain State Mismatch: local snapshot diverges from on-chain object data

History:
  Pre-2026-03-18: Verified against World API /v2/smartassemblies/{id} with POD signatures.
  CCP deprecated /v2/smartassemblies (dynamic data removed, chain-only now).
  Refactored to compare local snapshots against Sui GraphQL object queries.
"""

import json
import logging
import sqlite3
import time

import httpx

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)

# Max objects to check per cycle
CHAIN_CHECK_LIMIT = 5

GET_OBJECT_STATE = """
query GetObject($address: SuiAddress!) {
  object(address: $address) {
    address
    version
    owner {
      ... on AddressOwner { owner { address } }
      ... on Shared { initialSharedVersion }
    }
    asMoveObject {
      contents {
        type { repr }
        json
      }
    }
  }
}
"""


class PodChecker(BaseChecker):
    """Checks local state against on-chain Sui object state via GraphQL.

    This checker is async — call run_async() from an async context.
    """

    name = "pod_checker"

    def __init__(
        self,
        conn: sqlite3.Connection,
        graphql_url: str = "https://graphql.testnet.sui.io/graphql",
    ):
        super().__init__(conn)
        self.graphql_url = graphql_url

    def check(self) -> list[Anomaly]:
        """Sync check() — not supported for PodChecker."""
        raise NotImplementedError("PodChecker requires async execution. Use run_async() instead.")

    async def run_async(self, client: httpx.AsyncClient | None = None) -> list[Anomaly]:
        """Run all chain state verification rules asynchronously."""
        if client is None:
            async with httpx.AsyncClient() as c:
                return await self._check_p1_chain_state(c)
        return await self._check_p1_chain_state(client)

    async def _check_p1_chain_state(self, client: httpx.AsyncClient) -> list[Anomaly]:
        """P1: Local state snapshot diverges from on-chain object data.

        Fetches current object state from Sui GraphQL and compares key fields
        (owner, version, contents) against local snapshots.
        """
        rows = self.conn.execute(
            """SELECT o.object_id, o.object_type, o.system_id,
                      ws.state_data, ws.snapshot_time
               FROM objects o
               JOIN world_states ws ON o.object_id = ws.object_id
                 AND ws.snapshot_time = (
                   SELECT MAX(snapshot_time) FROM world_states
                   WHERE object_id = o.object_id
                 )
               WHERE o.object_type = 'smartassemblies'
               ORDER BY ws.snapshot_time DESC
               LIMIT ?""",
            (CHAIN_CHECK_LIMIT,),
        ).fetchall()

        anomalies = []
        for row in rows:
            obj_id = row["object_id"]
            system_id = row["system_id"] or ""
            local_state = self._parse_state(dict(row))

            chain_obj = await self._fetch_chain_object(client, obj_id)
            if chain_obj is None:
                continue

            mismatches = self._compare_with_chain(local_state, chain_obj)
            if mismatches:
                anomalies.append(
                    Anomaly(
                        anomaly_type="CHAIN_STATE_MISMATCH",
                        rule_id="P1",
                        detector=self.name,
                        object_id=obj_id,
                        system_id=system_id,
                        severity="CRITICAL",
                        category="EXPLOIT_VECTOR",
                        evidence={
                            "mismatches": mismatches,
                            "snapshot_time": row["snapshot_time"],
                            "chain_version": chain_obj.get("version"),
                            "check_time": int(time.time()),
                            "description": (
                                f"Chain divergence — our records for "
                                f"{obj_id[:16]}... don't match on-chain "
                                f"truth: {', '.join(mismatches.keys())}"
                            ),
                        },
                    )
                )

        return anomalies

    async def _fetch_chain_object(self, client: httpx.AsyncClient, object_id: str) -> dict | None:
        """Fetch an object's current state from Sui GraphQL."""
        try:
            resp = await client.post(
                self.graphql_url,
                json={"query": GET_OBJECT_STATE, "variables": {"address": object_id}},
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json()

            if result.get("errors"):
                logger.warning(
                    "GraphQL error for %s: %s",
                    object_id[:16],
                    result["errors"][0].get("message", ""),
                )
                return None

            obj = result.get("data", {}).get("object")
            if not obj:
                logger.debug("Object %s not found on chain", object_id[:16])
                return None

            return obj

        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Chain object fetch failed for %s: %s", object_id[:16], e)
            return None

    @staticmethod
    def _compare_with_chain(local: dict, chain_obj: dict) -> dict:
        """Compare local snapshot against on-chain object state.

        Returns dict of mismatched fields: {field: {local: X, chain: Y}}.
        """
        mismatches = {}

        # Compare owner if available
        local_owner = ""
        l_owner = local.get("owner", {})
        if isinstance(l_owner, dict):
            local_owner = l_owner.get("address", "")
        elif isinstance(l_owner, str):
            local_owner = l_owner

        chain_owner_data = chain_obj.get("owner", {})
        chain_owner = ""
        if isinstance(chain_owner_data, dict):
            # AddressOwner has nested owner.address
            inner = chain_owner_data.get("owner", {})
            if isinstance(inner, dict):
                chain_owner = inner.get("address", "")

        if local_owner and chain_owner and local_owner != chain_owner:
            mismatches["owner"] = {"local": local_owner, "chain": chain_owner}

        # Compare state from contents JSON
        contents = chain_obj.get("asMoveObject", {}).get("contents", {})
        chain_json_str = contents.get("json", "")
        if chain_json_str:
            try:
                chain_data = (
                    json.loads(chain_json_str)
                    if isinstance(chain_json_str, str)
                    else chain_json_str
                )
            except (json.JSONDecodeError, TypeError):
                chain_data = {}

            local_state = local.get("state", "")
            chain_state = chain_data.get("state", "")
            if local_state and chain_state and local_state != chain_state:
                mismatches["state"] = {"local": local_state, "chain": chain_state}

            # Compare fuel if present
            local_fuel = _nested_get(local, "networkNode", "fuel", "amount")
            chain_fuel = _nested_get(chain_data, "networkNode", "fuel", "amount")
            if local_fuel is not None and chain_fuel is not None and local_fuel != chain_fuel:
                mismatches["fuel"] = {"local": local_fuel, "chain": chain_fuel}

        return mismatches


def _nested_get(d: dict, *keys) -> object:
    """Safely traverse nested dict keys. Returns None if any key missing."""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current

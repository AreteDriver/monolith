"""POD checker — verifies local state against CCP's cryptographically signed POD data.

Rules:
  P1 — POD Verification Failure: local snapshot diverges from POD-signed authority data
"""

import logging
import sqlite3
import time

import httpx

from backend.detection.base import Anomaly, BaseChecker
from backend.ingestion.pod_verifier import PodVerifier

logger = logging.getLogger(__name__)

# Max objects to check per cycle to avoid hammering the World API
POD_CHECK_LIMIT = 5


class PodChecker(BaseChecker):
    """Checks local state against CCP's POD-signed data for integrity verification.

    This checker is async — it cannot be registered in the sync DetectionEngine.run_cycle().
    Call run_async() from an async context instead.
    """

    name = "pod_checker"

    def __init__(
        self,
        conn: sqlite3.Connection,
        pod_verifier: PodVerifier,
        client: httpx.AsyncClient,
    ):
        super().__init__(conn)
        self.pod_verifier = pod_verifier
        self.client = client

    def check(self) -> list[Anomaly]:
        """Sync check() — not supported for PodChecker.

        PodChecker requires async HTTP calls. Use run_async() instead.
        """
        raise NotImplementedError("PodChecker requires async execution. Use run_async() instead.")

    async def run_async(self) -> list[Anomaly]:
        """Run all POD verification rules asynchronously."""
        anomalies: list[Anomaly] = []
        anomalies.extend(await self._check_p1_pod_verification())
        return anomalies

    async def _check_p1_pod_verification(self) -> list[Anomaly]:
        """P1: Local state snapshot diverges from POD-signed World API data.

        Fetches POD-signed data for recent objects and compares key fields
        (state, owner, fuel) against local snapshots. Mismatches indicate
        either local data corruption or a chain integrity issue.
        """
        if not self.pod_verifier.base_url:
            return []

        # Get recent objects with snapshots, rate-limited to POD_CHECK_LIMIT
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
            (POD_CHECK_LIMIT,),
        ).fetchall()

        anomalies = []
        for row in rows:
            obj_id = row["object_id"]
            system_id = row["system_id"] or ""

            # Parse local state
            local_state = self._parse_state(dict(row))

            # Fetch POD-signed data from World API
            pod_envelope = await self.pod_verifier.fetch_pod(
                f"/v2/smartassemblies/{obj_id}",
                self.client,
            )
            if pod_envelope is None:
                # API unavailable or object not found — skip, don't flag
                continue

            # Verify the POD signature
            verification = await self.pod_verifier.verify(pod_envelope, self.client)
            if not verification.get("valid"):
                anomalies.append(
                    Anomaly(
                        anomaly_type="POD_SIGNATURE_INVALID",
                        rule_id="P1",
                        detector=self.name,
                        object_id=obj_id,
                        system_id=system_id,
                        severity="CRITICAL",
                        category="EXPLOIT_VECTOR",
                        evidence={
                            "verification_error": verification.get("error", "unknown"),
                            "snapshot_time": row["snapshot_time"],
                            "description": (
                                f"POD signature verification failed for "
                                f"{obj_id[:16]}... — data authenticity cannot "
                                f"be confirmed"
                            ),
                        },
                    )
                )
                continue

            # Extract POD data for field comparison
            pod_data = self._extract_pod_data(pod_envelope)
            if not pod_data:
                continue

            # Compare key fields between local snapshot and POD-signed data
            mismatches = self._compare_fields(local_state, pod_data)
            if mismatches:
                anomalies.append(
                    Anomaly(
                        anomaly_type="POD_STATE_MISMATCH",
                        rule_id="P1",
                        detector=self.name,
                        object_id=obj_id,
                        system_id=system_id,
                        severity="CRITICAL",
                        category="EXPLOIT_VECTOR",
                        evidence={
                            "mismatches": mismatches,
                            "snapshot_time": row["snapshot_time"],
                            "pod_fetch_time": int(time.time()),
                            "description": (
                                f"Local state diverges from POD-signed data "
                                f"for {obj_id[:16]}...: "
                                f"{', '.join(mismatches.keys())}"
                            ),
                        },
                    )
                )

        return anomalies

    @staticmethod
    def _extract_pod_data(pod_envelope: dict) -> dict:
        """Extract the actual data payload from a POD envelope.

        POD envelopes wrap data in various formats depending on the endpoint.
        Attempts to extract the inner data dict.
        """
        # Try common POD envelope structures
        if "data" in pod_envelope:
            data = pod_envelope["data"]
            if isinstance(data, dict):
                return data
            if isinstance(data, list) and len(data) == 1:
                return data[0] if isinstance(data[0], dict) else {}
        # Fallback: envelope itself may be the data
        return pod_envelope

    @staticmethod
    def _compare_fields(local: dict, pod: dict) -> dict:
        """Compare key fields between local snapshot and POD-signed data.

        Returns dict of mismatched fields: {field: {local: X, pod: Y}}.
        """
        mismatches = {}

        # Compare state
        local_state = local.get("state", "")
        pod_state = pod.get("state", "")
        if local_state and pod_state and local_state != pod_state:
            mismatches["state"] = {"local": local_state, "pod": pod_state}

        # Compare owner
        local_owner = ""
        pod_owner = ""
        l_owner = local.get("owner", {})
        p_owner = pod.get("owner", {})
        if isinstance(l_owner, dict):
            local_owner = l_owner.get("address", "")
        elif isinstance(l_owner, str):
            local_owner = l_owner
        if isinstance(p_owner, dict):
            pod_owner = p_owner.get("address", "")
        elif isinstance(p_owner, str):
            pod_owner = p_owner
        if local_owner and pod_owner and local_owner != pod_owner:
            mismatches["owner"] = {"local": local_owner, "pod": pod_owner}

        # Compare fuel amount
        local_fuel = _nested_get(local, "networkNode", "fuel", "amount")
        pod_fuel = _nested_get(pod, "networkNode", "fuel", "amount")
        if local_fuel is not None and pod_fuel is not None and local_fuel != pod_fuel:
            mismatches["fuel"] = {"local": local_fuel, "pod": pod_fuel}

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

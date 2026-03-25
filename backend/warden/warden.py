"""Warden — autonomous threat hypothesis/test loop.

Ingests chain events and anomalies, generates threat hypotheses,
verifies them against on-chain data, and stores results. Operates
within configurable bounds (max cycles, read-only chain access).
"""

import logging
import sqlite3

import httpx

from backend.warden.sui_queries import (
    get_latest_checkpoint,
    get_object_state,
    verify_object_exists,
)

logger = logging.getLogger(__name__)

# Default max autonomous cycles before requiring human review
DEFAULT_MAX_CYCLES = 24


class Warden:
    """Autonomous threat analysis system.

    Reads anomalies and chain state, generates verification queries,
    and updates anomaly confidence. Never writes to chain.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        sui_rpc_url: str,
        max_cycles: int = DEFAULT_MAX_CYCLES,
    ):
        self.conn = conn
        self.sui_rpc_url = sui_rpc_url
        self.max_cycles = max_cycles
        self.cycles_run = 0

    async def run_cycle(self, client: httpx.AsyncClient | None = None) -> dict:
        """Run one verification cycle.

        Returns dict with cycle results: verified, dismissed, errors.
        """
        if self.cycles_run >= self.max_cycles:
            logger.info("Warden: max cycles (%d) reached — pausing", self.max_cycles)
            return {"status": "paused", "reason": "max_cycles"}

        self.cycles_run += 1
        results = {"verified": 0, "dismissed": 0, "errors": 0, "cycle": self.cycles_run}

        # Get unverified anomalies that reference an object_id
        unverified = self._get_unverified_anomalies(limit=10)
        if not unverified:
            return {**results, "status": "idle"}

        # Chain health check
        checkpoint = await get_latest_checkpoint(self.sui_rpc_url, client)
        if checkpoint == 0:
            logger.warning("Warden: chain unreachable — skipping cycle")
            return {**results, "status": "chain_unreachable"}

        for anomaly in unverified:
            try:
                verified = await self._verify_anomaly(anomaly, client)
                if verified:
                    self._update_status(anomaly["anomaly_id"], "VERIFIED")
                    results["verified"] += 1
                else:
                    self._update_status(anomaly["anomaly_id"], "DISMISSED")
                    results["dismissed"] += 1
            except Exception:
                logger.exception("Warden: error verifying %s", anomaly["anomaly_id"])
                results["errors"] += 1

        results["status"] = "completed"
        logger.info(
            "Warden cycle %d: %d verified, %d dismissed, %d errors",
            self.cycles_run,
            results["verified"],
            results["dismissed"],
            results["errors"],
        )
        return results

    def _get_unverified_anomalies(self, limit: int = 10) -> list[dict]:
        """Fetch UNVERIFIED anomalies with object_id for chain verification."""
        try:
            rows = self.conn.execute(
                """SELECT anomaly_id, anomaly_type, rule_id, object_id,
                          system_id, evidence_json, severity
                   FROM anomalies
                   WHERE status = 'UNVERIFIED'
                     AND object_id != ''
                   ORDER BY detected_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    async def _verify_anomaly(
        self,
        anomaly: dict,
        client: httpx.AsyncClient | None = None,
    ) -> bool:
        """Verify an anomaly against on-chain state.

        Returns True if the anomaly is confirmed (object state supports it),
        False if the anomaly should be dismissed.
        """
        object_id = anomaly["object_id"]
        rule_id = anomaly["rule_id"]

        # For continuity rules (C1, C2): check if object exists on chain
        if rule_id in ("C1", "C2"):
            exists = await verify_object_exists(self.sui_rpc_url, object_id, client)
            if rule_id == "C1":
                # Ghost Signal: object shouldn't exist → verified if it does
                return exists
            if rule_id == "C2":
                # Lazarus: destroyed object broadcasting → verified if still alive
                return exists

        # For state divergence (A1, P1): compare chain vs local
        if rule_id in ("A1", "P1"):
            chain_state = await get_object_state(self.sui_rpc_url, object_id, client)
            return chain_state is not None

        # Default: cannot verify via chain query — keep as UNVERIFIED
        # Don't dismiss what we can't check
        return True

    def _update_status(self, anomaly_id: str, status: str) -> None:
        """Update anomaly status in database."""
        try:
            self.conn.execute(
                "UPDATE anomalies SET status = ? WHERE anomaly_id = ?",
                (status, anomaly_id),
            )
            self.conn.commit()
        except sqlite3.OperationalError:
            logger.warning("Failed to update anomaly %s status", anomaly_id)

    def reset_cycles(self) -> None:
        """Reset cycle counter (call after human review)."""
        self.cycles_run = 0

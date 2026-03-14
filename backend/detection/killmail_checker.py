"""Killmail reconciliation checker — cross-references World API kills against chain records.

Rules:
  K1 — Missing Chain Kill: Kill exists in World API but not in chain_events
  K2 — Chain-Only Kill: Kill in chain but missing from World API (possible API lag)
"""

import json
import logging
import sqlite3
import time

import httpx

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)

# Time window for matching kills between sources (seconds)
MATCH_WINDOW_SECONDS = 60

# How far back to look for chain kills (seconds)
LOOKBACK_SECONDS = 24 * 3600


class KillmailChecker(BaseChecker):
    """Cross-references World API killmails against on-chain KillmailCreatedEvent records.

    This checker is async — it cannot be registered in the sync DetectionEngine.run_cycle().
    Call run_async() from an async context instead.
    """

    name = "killmail_checker"

    def __init__(
        self,
        conn: sqlite3.Connection,
        client: httpx.AsyncClient,
        world_api_url: str,
    ):
        super().__init__(conn)
        self.client = client
        self.world_api_url = world_api_url.rstrip("/")

    def check(self) -> list[Anomaly]:
        """Sync check() — not supported for KillmailChecker.

        KillmailChecker requires async HTTP calls. Use run_async() instead.
        """
        raise NotImplementedError(
            "KillmailChecker requires async execution. Use run_async() instead."
        )

    async def run_async(self) -> list[Anomaly]:
        """Run all killmail reconciliation rules asynchronously."""
        anomalies: list[Anomaly] = []
        try:
            world_kills = await self._fetch_recent_kills()
        except Exception:
            logger.exception("Failed to fetch killmails from World API")
            return anomalies

        since_timestamp = int(time.time()) - LOOKBACK_SECONDS
        chain_kills = self._get_chain_kills(since_timestamp)

        anomalies.extend(self._check_k1_missing_chain_kill(world_kills, chain_kills))
        anomalies.extend(self._check_k2_chain_only_kill(world_kills, chain_kills))
        return anomalies

    async def _fetch_recent_kills(self) -> list[dict]:
        """Fetch recent killmails from the World API.

        Returns:
            List of killmail dicts from the World API.
        """
        url = f"{self.world_api_url}/v2/killmails?limit=100"
        resp = await self.client.get(url, timeout=10.0)
        resp.raise_for_status()
        body = resp.json()

        # Standard EVE Frontier wrapper: {"data": [...], "metadata": {...}}
        if isinstance(body, dict) and "data" in body:
            return body["data"] if isinstance(body["data"], list) else []
        if isinstance(body, list):
            return body
        return []

    def _get_chain_kills(self, since_timestamp: int) -> list[dict]:
        """Get KillmailCreatedEvent chain events since a given timestamp.

        Returns:
            List of chain event dicts with parsed raw_json.
        """
        rows = self.conn.execute(
            "SELECT * FROM chain_events "
            "WHERE event_type = 'KillmailCreatedEvent' AND timestamp >= ? "
            "ORDER BY timestamp ASC",
            (since_timestamp,),
        ).fetchall()

        results = []
        for row in rows:
            event = dict(row)
            raw = event.get("raw_json", "{}")
            if isinstance(raw, str):
                try:
                    event["parsed"] = json.loads(raw)
                except json.JSONDecodeError:
                    event["parsed"] = {}
            else:
                event["parsed"] = raw if isinstance(raw, dict) else {}
            results.append(event)
        return results

    def _check_k1_missing_chain_kill(
        self,
        world_kills: list[dict],
        chain_kills: list[dict],
    ) -> list[Anomaly]:
        """K1: Kill exists in World API but has no matching chain event.

        Indicates a silent gap — "Report Kill To Chain" may have failed in-game.
        """
        anomalies = []
        for wk in world_kills:
            if self._find_chain_match(wk, chain_kills):
                continue

            killmail_id = self._extract_world_kill_id(wk)
            victim_id = self._extract_victim_id_from_world(wk)
            anomalies.append(
                Anomaly(
                    anomaly_type="MISSING_CHAIN_KILL",
                    rule_id="K1",
                    detector=self.name,
                    object_id=killmail_id or victim_id or "unknown",
                    evidence={
                        "world_api_killmail": wk,
                        "expected": "Chain KillmailCreatedEvent",
                        "actual": "No matching chain event found",
                        "description": (
                            f"Killmail {killmail_id or victim_id or 'unknown'} "
                            f"exists in World API but has no corresponding "
                            f"on-chain KillmailCreatedEvent — possible silent "
                            f"chain reporting failure"
                        ),
                    },
                )
            )
        return anomalies

    def _check_k2_chain_only_kill(
        self,
        world_kills: list[dict],
        chain_kills: list[dict],
    ) -> list[Anomaly]:
        """K2: Kill in chain but missing from World API (possible API lag)."""
        anomalies = []
        for ck in chain_kills:
            if self._find_world_match(ck, world_kills):
                continue

            event_id = ck.get("event_id", "unknown")
            tx_hash = ck.get("transaction_hash", "")
            anomalies.append(
                Anomaly(
                    anomaly_type="CHAIN_ONLY_KILL",
                    rule_id="K2",
                    detector=self.name,
                    object_id=event_id,
                    evidence={
                        "chain_event_id": event_id,
                        "transaction_hash": tx_hash,
                        "chain_timestamp": ck.get("timestamp", 0),
                        "expected": "Killmail in World API",
                        "actual": "No matching World API killmail found",
                        "description": (
                            f"Chain KillmailCreatedEvent {event_id} has no "
                            f"matching World API killmail — may be API lag "
                            f"or World API data loss"
                        ),
                    },
                )
            )
        return anomalies

    def _find_chain_match(self, world_kill: dict, chain_kills: list[dict]) -> bool:
        """Check if a World API killmail has a matching chain event.

        Matches on killmail_id if available, otherwise falls back to
        victim_id + approximate timestamp (within MATCH_WINDOW_SECONDS).
        """
        wk_id = self._extract_world_kill_id(world_kill)
        wk_victim = self._extract_victim_id_from_world(world_kill)
        wk_ts = self._extract_timestamp_from_world(world_kill)

        for ck in chain_kills:
            # Match by killmail_id if both sides have it
            ck_parsed = ck.get("parsed", {})
            parsed_json = ck_parsed.get("parsedJson", ck_parsed)
            ck_killmail_id = str(parsed_json.get("killmail_id", parsed_json.get("killmailId", "")))

            if wk_id and ck_killmail_id and wk_id == ck_killmail_id:
                return True

            # Fallback: victim_id + timestamp proximity
            ck_victim = str(parsed_json.get("victim_id", parsed_json.get("victimId", "")))
            ck_ts = ck.get("timestamp", 0)

            if (
                wk_victim
                and ck_victim
                and wk_victim == ck_victim
                and wk_ts
                and ck_ts
                and abs(wk_ts - ck_ts) <= MATCH_WINDOW_SECONDS
            ):
                return True

        return False

    def _find_world_match(self, chain_kill: dict, world_kills: list[dict]) -> bool:
        """Check if a chain kill event has a matching World API killmail.

        Mirror logic of _find_chain_match but from chain→world direction.
        """
        ck_parsed = chain_kill.get("parsed", {})
        parsed_json = ck_parsed.get("parsedJson", ck_parsed)
        ck_killmail_id = str(parsed_json.get("killmail_id", parsed_json.get("killmailId", "")))
        ck_victim = str(parsed_json.get("victim_id", parsed_json.get("victimId", "")))
        ck_ts = chain_kill.get("timestamp", 0)

        for wk in world_kills:
            wk_id = self._extract_world_kill_id(wk)
            if ck_killmail_id and wk_id and ck_killmail_id == wk_id:
                return True

            wk_victim = self._extract_victim_id_from_world(wk)
            wk_ts = self._extract_timestamp_from_world(wk)
            if (
                ck_victim
                and wk_victim
                and ck_victim == wk_victim
                and ck_ts
                and wk_ts
                and abs(ck_ts - wk_ts) <= MATCH_WINDOW_SECONDS
            ):
                return True

        return False

    @staticmethod
    def _extract_world_kill_id(wk: dict) -> str:
        """Extract killmail identifier from a World API killmail dict."""
        for key in ("killmail_id", "killmailId", "id"):
            val = wk.get(key)
            if val:
                return str(val)
        return ""

    @staticmethod
    def _extract_victim_id_from_world(wk: dict) -> str:
        """Extract victim identifier from a World API killmail dict.

        World API killmails have nested killer/victim objects.
        """
        victim = wk.get("victim", {})
        if isinstance(victim, dict):
            for key in ("id", "address", "victim_id"):
                val = victim.get(key)
                if val:
                    return str(val)
        # Flat structure fallback
        for key in ("victim_id", "victimId"):
            val = wk.get(key)
            if val:
                return str(val)
        return ""

    @staticmethod
    def _extract_timestamp_from_world(wk: dict) -> int:
        """Extract timestamp from a World API killmail dict."""
        for key in ("timestamp", "kill_time", "killTime"):
            val = wk.get(key)
            if val:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    continue
        return 0

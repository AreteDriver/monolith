"""Killmail reconciliation checker — chain-internal killmail consistency checks.

Rules:
  K1 — Duplicate Killmail: Same victim killed multiple times within a short window
  K2 — Unreported Kill: KillmailCreatedEvent with mismatched reporter (reported_by != killer)

History:
  Pre-2026-03-18: K1/K2 cross-referenced World API /v2/killmails against chain events.
  CCP deprecated /v2/killmails (dynamic data removed, chain-only now).
  Refactored to chain-internal consistency checks using KillmailCreatedEvent records only.
"""

import json
import logging
import sqlite3

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)

# Time window for detecting duplicate kills on the same victim (seconds)
DUPLICATE_WINDOW_SECONDS = 120

# How far back to look for chain kills (seconds)
LOOKBACK_SECONDS = 24 * 3600


class KillmailChecker(BaseChecker):
    """Chain-internal killmail consistency checker.

    Operates entirely on local chain_events table — no external API calls.
    Can be called from sync DetectionEngine.run_cycle().
    """

    name = "killmail_checker"

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)

    def check(self) -> list[Anomaly]:
        """Run all killmail reconciliation rules."""
        import time

        since_timestamp = int(time.time()) - LOOKBACK_SECONDS
        chain_kills = self._get_chain_kills(since_timestamp)

        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_k1_duplicate_kills(chain_kills))
        anomalies.extend(self._check_k2_unreported_kill(chain_kills))
        return anomalies

    def _get_chain_kills(self, since_timestamp: int) -> list[dict]:
        """Get KillmailCreatedEvent chain events since a given timestamp."""
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

    def _check_k1_duplicate_kills(self, chain_kills: list[dict]) -> list[Anomaly]:
        """K1: Same victim killed multiple times within a short window.

        Indicates either a duplicate event emission or a genuine double-kill
        exploit where a destroyed entity produces multiple killmails.
        """
        anomalies = []
        # Group by victim_id
        victim_kills: dict[str, list[dict]] = {}
        for ck in chain_kills:
            victim_id = self._extract_field(ck, "victim_id", "victimId")
            if victim_id:
                victim_kills.setdefault(victim_id, []).append(ck)

        for victim_id, kills in victim_kills.items():
            if len(kills) < 2:
                continue
            # Check for kills within the duplicate window
            kills_sorted = sorted(kills, key=lambda k: k.get("timestamp", 0))
            for i in range(1, len(kills_sorted)):
                t1 = kills_sorted[i - 1].get("timestamp", 0)
                t2 = kills_sorted[i].get("timestamp", 0)
                if t2 - t1 <= DUPLICATE_WINDOW_SECONDS:
                    event_id = kills_sorted[i].get("event_id", "unknown")
                    anomalies.append(
                        Anomaly(
                            anomaly_type="DUPLICATE_KILLMAIL",
                            rule_id="K1",
                            detector=self.name,
                            object_id=victim_id,
                            evidence={
                                "victim_id": victim_id,
                                "kill_count": len(kills),
                                "time_delta_seconds": t2 - t1,
                                "event_ids": [
                                    kills_sorted[i - 1].get("event_id", ""),
                                    event_id,
                                ],
                                "description": (
                                    f"Double tap — {victim_id[:16]}... killed "
                                    f"{len(kills)} times in {DUPLICATE_WINDOW_SECONDS}s. "
                                    f"Chain stuttered or someone shot a corpse"
                                ),
                            },
                        )
                    )
        return anomalies

    def _check_k2_unreported_kill(self, chain_kills: list[dict]) -> list[Anomaly]:
        """K2: Killmail where reporter differs from killer.

        When reported_by_character_id != killer_id, a third party reported the kill.
        Not necessarily an anomaly, but unusual and worth flagging for pattern analysis.
        """
        anomalies = []
        for ck in chain_kills:
            killer_id = self._extract_field(ck, "killer_id", "killerId")
            reporter_id = self._extract_field(
                ck, "reported_by_character_id", "reportedByCharacterId"
            )
            if not killer_id or not reporter_id:
                continue
            if killer_id != reporter_id:
                event_id = ck.get("event_id", "unknown")
                anomalies.append(
                    Anomaly(
                        anomaly_type="THIRD_PARTY_KILL_REPORT",
                        rule_id="K2",
                        detector=self.name,
                        object_id=event_id,
                        severity="LOW",
                        evidence={
                            "killer_id": killer_id,
                            "reporter_id": reporter_id,
                            "transaction_hash": ck.get("transaction_hash", ""),
                            "timestamp": ck.get("timestamp", 0),
                            "description": (
                                f"Witness report — kill logged by "
                                f"{reporter_id[:16]}..., not the shooter "
                                f"({killer_id[:16]}...). Someone's watching"
                            ),
                        },
                    )
                )
        return anomalies

    @staticmethod
    def _extract_field(event: dict, *field_names: str) -> str:
        """Extract a field from parsed event data, trying multiple key names."""
        parsed = event.get("parsed", {})
        parsed_json = parsed.get("parsedJson", parsed)
        for name in field_names:
            val = parsed_json.get(name)
            if val:
                return str(val)
        return ""

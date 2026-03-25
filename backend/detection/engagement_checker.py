"""Engagement session checker — reconstructs multi-event combat sessions.

Rules:
  ES1 — Orphaned killmail: killmail event with no preceding gate_jump or fuel
         event for the killer within 5 minutes. Suggests spoofed kill or
         event ordering bug.
  ES2 — Ghost engagement: gate_jump followed by killmail within 60s but the
         victim has no preceding events at all. Suggests the victim was
         spawned or teleported (impossible in normal gameplay).
"""

import contextlib
import json
import logging

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)

# Killer must have an event within this window before a killmail
KILLER_WINDOW_SECONDS = 300  # 5 minutes


class EngagementChecker(BaseChecker):
    """Reconstructs engagement sessions from correlated chain events."""

    name = "engagement_checker"

    def check(self) -> list[Anomaly]:
        """Run engagement session detection rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_es1_orphaned_killmail())
        anomalies.extend(self._check_es2_ghost_engagement())
        return anomalies

    def _get_killmail_events(self) -> list[dict]:
        """Get all killmail-type chain events."""
        rows = self.conn.execute(
            """SELECT * FROM chain_events
               WHERE event_type LIKE '%KillmailCreated%'
               ORDER BY timestamp ASC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def _extract_address(self, raw_json_str: str, field: str) -> str:
        """Extract an address field from raw_json.

        Handles both flat string values and nested dicts (e.g.
        ``{"victim_id": {"item_id": "211...", "tenant": "utopia"}}``).
        For nested dicts, extracts ``address``, ``id``, or ``item_id``.
        """
        raw = {}
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            raw = json.loads(raw_json_str or "{}")

        # Try flat fields first
        value = raw.get(field, "")
        if value:
            value = self._unwrap_address(value)
            if value:
                return value

        # Try nested parsedJson
        parsed = raw.get("parsedJson", {})
        if isinstance(parsed, dict):
            value = parsed.get(field, "")
            if value:
                value = self._unwrap_address(value)
                if value:
                    return value

        return ""

    @staticmethod
    def _unwrap_address(value: object) -> str:
        """Unwrap an address value that may be a string or nested dict.

        EVE Frontier killmails can embed victim/killer as dicts like
        ``{"item_id": "2112000187", "tenant": "utopia"}``.
        Extract the actual ID string.
        """
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            # Prefer well-known ID keys
            for key in ("address", "id", "item_id"):
                if key in value and isinstance(value[key], str):
                    return value[key]
        return ""

    def _check_es1_orphaned_killmail(self) -> list[Anomaly]:
        """ES1: Killmail with no preceding killer events within 5 minutes."""
        killmails = self._get_killmail_events()
        anomalies = []

        for km in killmails:
            killer_id = self._extract_address(km.get("raw_json", ""), "killer_id")
            if not killer_id:
                continue

            km_ts = km["timestamp"]
            cutoff = km_ts - KILLER_WINDOW_SECONDS

            # Check for ANY chain event from this sender within 5 min before
            row = self.conn.execute(
                """SELECT 1 FROM chain_events
                   WHERE timestamp >= ? AND timestamp < ?
                     AND (
                       json_extract(raw_json, '$.sender') = ?
                       OR object_id = ?
                     )
                   LIMIT 1""",
                (cutoff, km_ts, killer_id, killer_id),
            ).fetchone()

            if row is None:
                anomalies.append(
                    Anomaly(
                        anomaly_type="ORPHANED_KILLMAIL",
                        rule_id="ES1",
                        detector=self.name,
                        object_id=km.get("event_id", killer_id),
                        system_id=km.get("system_id", ""),
                        evidence={
                            "description": (
                                f"Orphaned kill — killmail {km.get('event_id', '')[:16]} "
                                f"but killer {killer_id[:16]}... had no chain "
                                f"activity in the prior {KILLER_WINDOW_SECONDS}s. "
                                f"Came from nowhere"
                            ),
                            "killer_id": killer_id,
                            "killmail_event_id": km.get("event_id", ""),
                            "killmail_timestamp": km_ts,
                            "window_seconds": KILLER_WINDOW_SECONDS,
                        },
                    )
                )
        return anomalies

    def _check_es2_ghost_engagement(self) -> list[Anomaly]:
        """ES2: Victim in killmail has zero prior chain events ever."""
        killmails = self._get_killmail_events()
        anomalies = []

        for km in killmails:
            victim_id = self._extract_address(km.get("raw_json", ""), "victim_id")
            if not victim_id:
                continue

            km_ts = km["timestamp"]

            # Check if victim has ANY event before this killmail
            row = self.conn.execute(
                """SELECT 1 FROM chain_events
                   WHERE timestamp < ?
                     AND (
                       json_extract(raw_json, '$.sender') = ?
                       OR object_id = ?
                     )
                   LIMIT 1""",
                (km_ts, victim_id, victim_id),
            ).fetchone()

            if row is None:
                anomalies.append(
                    Anomaly(
                        anomaly_type="GHOST_ENGAGEMENT",
                        rule_id="ES2",
                        detector=self.name,
                        object_id=km.get("event_id", victim_id),
                        system_id=km.get("system_id", ""),
                        evidence={
                            "description": (
                                f"Phantom kill — victim {victim_id[:16]}... "
                                f"in killmail {km.get('event_id', '')[:16]} "
                                f"had zero chain history. Materialized to die"
                            ),
                            "victim_id": victim_id,
                            "killmail_event_id": km.get("event_id", ""),
                            "killmail_timestamp": km_ts,
                        },
                    )
                )
        return anomalies

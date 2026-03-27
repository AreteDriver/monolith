"""Feral AI checker — detects swarm surges and zone silence.

Rules:
  FA1 — Hive Surge: feral AI event count in a zone spikes (5+ events in 30min).
  FA2 — Silent Zone: previously active feral AI zone has no events in 2+ hours.
"""

import logging
import time

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)

# FA1: minimum events in window to trigger surge
SURGE_THRESHOLD = 5
SURGE_WINDOW = 1800  # 30 minutes

# FA2: silence threshold for previously active zone
SILENCE_THRESHOLD = 7200  # 2 hours
# Minimum historical events to consider a zone "previously active"
MIN_HISTORY = 3


class FeralAIChecker(BaseChecker):
    """Detects feral AI activity surges and zone silence."""

    name = "feral_ai_checker"

    def check(self) -> list[Anomaly]:
        """Run feral AI detection rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_fa1_hive_surge())
        anomalies.extend(self._check_fa2_silent_zone())
        return anomalies

    def _check_fa1_hive_surge(self) -> list[Anomaly]:
        """FA1: Spike in feral AI events within a zone."""
        now = int(time.time())
        cutoff = now - SURGE_WINDOW

        try:
            rows = self.conn.execute(
                """SELECT zone_id, system_id, COUNT(*) as event_count
                   FROM feral_ai_events
                   WHERE detected_at >= ?
                   GROUP BY zone_id
                   HAVING event_count >= ?""",
                (cutoff, SURGE_THRESHOLD),
            ).fetchall()
        except Exception:
            return []

        anomalies = []
        for row in rows:
            zone_id = row["zone_id"] or "unknown"
            anomalies.append(
                Anomaly(
                    anomaly_type="HIVE_SURGE",
                    rule_id="FA1",
                    detector=self.name,
                    object_id=zone_id,
                    system_id=row["system_id"] or "",
                    evidence={
                        "event_count": row["event_count"],
                        "window_minutes": SURGE_WINDOW // 60,
                        "description": (
                            f"Feral AI surge in zone {zone_id} — "
                            f"{row['event_count']} events in {SURGE_WINDOW // 60}min"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"feral_ai:{zone_id}",
                            timestamp=0,
                            derivation=(
                                f"FA1: {row['event_count']} events in {SURGE_WINDOW // 60}min"
                            ),
                        )
                    ],
                )
            )
        return anomalies

    def _check_fa2_silent_zone(self) -> list[Anomaly]:
        """FA2: Previously active feral AI zone went silent."""
        now = int(time.time())
        silence_cutoff = now - SILENCE_THRESHOLD

        try:
            # Zones with historical activity but nothing recent
            rows = self.conn.execute(
                """SELECT zone_id, system_id,
                          COUNT(*) as total_events,
                          MAX(detected_at) as last_event
                   FROM feral_ai_events
                   GROUP BY zone_id
                   HAVING total_events >= ? AND last_event < ?""",
                (MIN_HISTORY, silence_cutoff),
            ).fetchall()
        except Exception:
            return []

        anomalies = []
        for row in rows:
            zone_id = row["zone_id"] or "unknown"
            silent_minutes = (now - row["last_event"]) // 60

            anomalies.append(
                Anomaly(
                    anomaly_type="SILENT_ZONE",
                    rule_id="FA2",
                    detector=self.name,
                    object_id=zone_id,
                    system_id=row["system_id"] or "",
                    evidence={
                        "total_events": row["total_events"],
                        "silent_minutes": silent_minutes,
                        "last_event": row["last_event"],
                        "description": (
                            f"Feral AI zone {zone_id} went dark — "
                            f"{silent_minutes}min silence after "
                            f"{row['total_events']} historical events"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"feral_ai:{zone_id}",
                            timestamp=row["last_event"],
                            derivation=(
                                f"FA2: {silent_minutes}min silence"
                                f" ({row['total_events']} historical)"
                            ),
                        )
                    ],
                )
            )
        return anomalies

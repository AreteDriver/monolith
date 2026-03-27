"""Orbital zone checker — monitors zone coverage and feral AI escalation.

Rules:
  OZ1 — Blind Spot: an orbital zone hasn't been polled/scanned in over 20 minutes.
  OZ2 — Tier Escalation: feral AI threat tier increased since last check.
"""

import logging
import time

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)

# Zone is "dark" if not polled in this many seconds
BLIND_SPOT_THRESHOLD = 1200  # 20 minutes


class OrbitalZoneChecker(BaseChecker):
    """Detects orbital zone coverage gaps and feral AI threat changes."""

    name = "orbital_zone_checker"

    def check(self) -> list[Anomaly]:
        """Run orbital zone detection rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_oz1_blind_spot())
        anomalies.extend(self._check_oz2_tier_escalation())
        return anomalies

    def _check_oz1_blind_spot(self) -> list[Anomaly]:
        """OZ1: Orbital zone not polled within threshold."""
        now = int(time.time())
        cutoff = now - BLIND_SPOT_THRESHOLD

        try:
            rows = self.conn.execute(
                """SELECT zone_id, zone_name, system_id, last_polled
                   FROM orbital_zones
                   WHERE last_polled < ? OR last_polled IS NULL""",
                (cutoff,),
            ).fetchall()
        except Exception:
            return []

        anomalies = []
        for row in rows:
            zone_id = row["zone_id"]
            last_polled = row["last_polled"] or 0
            dark_minutes = (now - last_polled) // 60 if last_polled else 999

            anomalies.append(
                Anomaly(
                    anomaly_type="BLIND_SPOT",
                    rule_id="OZ1",
                    detector=self.name,
                    object_id=zone_id,
                    system_id=row["system_id"] or "",
                    evidence={
                        "zone_name": row["zone_name"] or zone_id,
                        "dark_minutes": dark_minutes,
                        "last_polled": last_polled,
                        "description": (
                            f"Zone {row['zone_name'] or zone_id} dark for "
                            f"{dark_minutes}min — blind spot in coverage"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"zone:{zone_id}",
                            timestamp=last_polled,
                            derivation=(
                                f"OZ1: dark {dark_minutes}min"
                                f" (threshold {BLIND_SPOT_THRESHOLD // 60}min)"
                            ),
                        )
                    ],
                )
            )
        return anomalies

    def _check_oz2_tier_escalation(self) -> list[Anomaly]:
        """OZ2: Feral AI tier increased in a zone (detected via recent events)."""
        now = int(time.time())
        one_hour_ago = now - 3600

        try:
            rows = self.conn.execute(
                """SELECT oz.zone_id, oz.zone_name, oz.system_id,
                          oz.feral_ai_tier, COUNT(fa.id) as recent_events
                   FROM orbital_zones oz
                   LEFT JOIN feral_ai_events fa
                     ON fa.zone_id = oz.zone_id AND fa.detected_at >= ?
                   WHERE oz.feral_ai_tier > 0
                   GROUP BY oz.zone_id
                   HAVING recent_events >= 3""",
                (one_hour_ago,),
            ).fetchall()
        except Exception:
            return []

        anomalies = []
        for row in rows:
            anomalies.append(
                Anomaly(
                    anomaly_type="TIER_ESCALATION",
                    rule_id="OZ2",
                    detector=self.name,
                    object_id=row["zone_id"],
                    system_id=row["system_id"] or "",
                    evidence={
                        "zone_name": row["zone_name"] or row["zone_id"],
                        "current_tier": row["feral_ai_tier"],
                        "recent_events": row["recent_events"],
                        "description": (
                            f"Zone {row['zone_name'] or row['zone_id']} — "
                            f"tier {row['feral_ai_tier']} feral AI with "
                            f"{row['recent_events']} events in last hour"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"zone:{row['zone_id']}",
                            timestamp=0,
                            derivation=(
                                f"OZ2: tier {row['feral_ai_tier']} {row['recent_events']} events/hr"
                            ),
                        )
                    ],
                )
            )
        return anomalies

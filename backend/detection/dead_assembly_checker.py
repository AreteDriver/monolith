"""Dead assembly checker — detects abandoned infrastructure.

Rules:
  DA1 — Dead assembly: smart assembly (gate, storage, turret) with no events
         in 7+ days despite having fuel events earlier. Last fuel event was
         a burn or consumption, suggesting fuel ran out and nobody refueled.
"""

import logging
import time

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)

# Assemblies silent for this many seconds are considered dead
DEAD_THRESHOLD_SECONDS = 7 * 86400  # 7 days

# Object types that represent smart assemblies
ASSEMBLY_TYPES = ("gate", "status", "assembly", "fuel", "storage_unit", "turret")


class DeadAssemblyChecker(BaseChecker):
    """Detects smart assemblies that have gone silent with expired fuel."""

    name = "dead_assembly_checker"

    def check(self) -> list[Anomaly]:
        """Run dead assembly detection rules."""
        return self._check_da1_dead_assembly()

    def _check_da1_dead_assembly(self) -> list[Anomaly]:
        """DA1: Assembly with no events in 7+ days that previously had fuel."""
        now = int(time.time())
        cutoff = now - DEAD_THRESHOLD_SECONDS

        # Find assemblies that haven't been seen in 7+ days
        placeholders = ",".join("?" for _ in ASSEMBLY_TYPES)
        rows = self.conn.execute(
            f"""SELECT object_id, object_type, last_seen, system_id
                FROM objects
                WHERE object_type IN ({placeholders})
                  AND last_seen < ?""",  # noqa: S608
            (*ASSEMBLY_TYPES, cutoff),
        ).fetchall()

        anomalies = []
        for row in rows:
            obj = dict(row)
            object_id = obj["object_id"]

            # Check if this assembly ever had fuel events
            fuel_row = self.conn.execute(
                """SELECT timestamp FROM chain_events
                   WHERE object_id = ?
                     AND event_type LIKE '%FuelEvent%'
                   ORDER BY timestamp DESC
                   LIMIT 1""",
                (object_id,),
            ).fetchone()

            if fuel_row is None:
                # No fuel events ever — not a fueled assembly, skip
                continue

            last_fuel_ts = fuel_row[0]
            if last_fuel_ts >= cutoff:
                # Fuel event is recent enough, skip
                continue

            last_seen = obj["last_seen"]
            days_silent = (now - last_seen) / 86400

            anomalies.append(
                Anomaly(
                    anomaly_type="DEAD_ASSEMBLY",
                    rule_id="DA1",
                    detector=self.name,
                    object_id=object_id,
                    system_id=obj.get("system_id", ""),
                    evidence={
                        "description": (
                            f"Derelict — {obj['object_type']} {object_id[:16]}... "
                            f"dark for {days_silent:.1f} days. Last fuel burn "
                            f"{(now - last_fuel_ts) / 86400:.1f} days ago. "
                            f"Presumed abandoned"
                        ),
                        "object_type": obj["object_type"],
                        "last_seen": last_seen,
                        "last_fuel_timestamp": last_fuel_ts,
                        "days_silent": round(days_silent, 1),
                    },
                )
            )
        return anomalies

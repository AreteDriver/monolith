"""Economic velocity checker — detects sudden changes in item flow rates.

Rules:
  EV1 — Velocity spike: item flow rate for an assembly increased >3x compared
         to its 7-day average in the last hour. Suggests unusual activity
         (rush to evacuate, sudden influx, or exploit).
  EV2 — Velocity drop: assembly that was active (5+ events/day average) went
         to zero events in the last 24 hours. Suggests disruption or bug.
"""

import logging
import time

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)

# Spike detection: last hour vs 7-day average
SPIKE_MULTIPLIER = 3
SEVEN_DAYS_SECONDS = 7 * 86400

# Drop detection: minimum daily average to be considered "active"
MIN_DAILY_EVENTS = 5


class VelocityChecker(BaseChecker):
    """Detects sudden changes in economic item flow rates."""

    name = "velocity_checker"

    def check(self) -> list[Anomaly]:
        """Run economic velocity detection rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_ev1_velocity_spike())
        anomalies.extend(self._check_ev2_velocity_drop())
        return anomalies

    def _check_ev1_velocity_spike(self) -> list[Anomaly]:
        """EV1: Item flow rate >3x the 7-day hourly average in the last hour."""
        now = int(time.time())
        one_hour_ago = now - 3600
        seven_days_ago = now - SEVEN_DAYS_SECONDS

        # Get distinct assemblies with activity in the last hour
        active_rows = self.conn.execute(
            """SELECT DISTINCT assembly_id FROM item_ledger
               WHERE timestamp >= ?""",
            (one_hour_ago,),
        ).fetchall()

        anomalies = []
        for row in active_rows:
            assembly_id = row[0]

            # Count events in last hour
            last_hour_row = self.conn.execute(
                """SELECT COUNT(*) FROM item_ledger
                   WHERE assembly_id = ? AND timestamp >= ?""",
                (assembly_id, one_hour_ago),
            ).fetchone()
            last_hour_count = last_hour_row[0]

            # Count events in last 7 days (for hourly average)
            seven_day_row = self.conn.execute(
                """SELECT COUNT(*) FROM item_ledger
                   WHERE assembly_id = ? AND timestamp >= ?""",
                (assembly_id, seven_days_ago),
            ).fetchone()
            seven_day_count = seven_day_row[0]

            # Compute average hourly rate over 7 days
            hours_in_window = SEVEN_DAYS_SECONDS / 3600  # 168 hours
            avg_hourly = seven_day_count / hours_in_window

            if avg_hourly <= 0:
                continue

            if last_hour_count > SPIKE_MULTIPLIER * avg_hourly:
                anomalies.append(
                    Anomaly(
                        anomaly_type="VELOCITY_SPIKE",
                        rule_id="EV1",
                        detector=self.name,
                        object_id=assembly_id,
                        evidence={
                            "description": (
                                f"Gold rush — {assembly_id[:16]}... surging at "
                                f"{last_hour_count} events/hr "
                                f"({last_hour_count / avg_hourly:.1f}x the "
                                f"7-day baseline of {avg_hourly:.2f}/hr). "
                                f"Something's happening here"
                            ),
                            "last_hour_count": last_hour_count,
                            "avg_hourly_7d": round(avg_hourly, 2),
                            "spike_multiplier": round(last_hour_count / avg_hourly, 2),
                            "seven_day_total": seven_day_count,
                        },
                    )
                )
        return anomalies

    def _check_ev2_velocity_drop(self) -> list[Anomaly]:
        """EV2: Active assembly (5+ events/day avg) with 0 events in last 24h."""
        now = int(time.time())
        one_day_ago = now - 86400
        seven_days_ago = now - SEVEN_DAYS_SECONDS

        # Get assemblies with 7-day activity
        assembly_rows = self.conn.execute(
            """SELECT assembly_id, COUNT(*) as total
               FROM item_ledger
               WHERE timestamp >= ?
               GROUP BY assembly_id""",
            (seven_days_ago,),
        ).fetchall()

        anomalies = []
        for row in assembly_rows:
            assembly_id = row[0]
            total_7d = row[1]

            # Average daily rate over 7 days
            avg_daily = total_7d / 7.0
            if avg_daily < MIN_DAILY_EVENTS:
                continue

            # Check if any events in last 24h
            recent_row = self.conn.execute(
                """SELECT COUNT(*) FROM item_ledger
                   WHERE assembly_id = ? AND timestamp >= ?""",
                (assembly_id, one_day_ago),
            ).fetchone()

            if recent_row[0] == 0:
                anomalies.append(
                    Anomaly(
                        anomaly_type="VELOCITY_DROP",
                        rule_id="EV2",
                        detector=self.name,
                        object_id=assembly_id,
                        evidence={
                            "description": (
                                f"Market silence — {assembly_id[:16]}... went dark. "
                                f"Zero activity in 24h, was running "
                                f"{avg_daily:.1f}/day. Region going cold"
                            ),
                            "avg_daily_7d": round(avg_daily, 1),
                            "seven_day_total": total_7d,
                            "last_24h_count": 0,
                        },
                    )
                )
        return anomalies

"""Config change checker — detects game configuration modifications.

Rules:
  CC1 — Config singleton version change: Energy, Fuel, or Gate config object
         version increased, indicating a game parameter change.
"""

import logging

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)


class ConfigChangeChecker(BaseChecker):
    """Checks for game config singleton version changes."""

    name = "config_change_checker"

    def check(self) -> list[Anomaly]:
        """Run config change rules."""
        return self._check_cc1_config_version_change()

    def _check_cc1_config_version_change(self) -> list[Anomaly]:
        """CC1: Config singleton has 2+ distinct versions — parameter change detected."""
        rows = self.conn.execute(
            """SELECT config_type,
                      COUNT(DISTINCT version) AS ver_count,
                      MIN(version) AS min_ver,
                      MAX(version) AS max_ver
               FROM config_snapshots
               GROUP BY config_type
               HAVING ver_count >= 2"""
        ).fetchall()

        anomalies = []
        for row in rows:
            config_type = row["config_type"]
            min_ver = row["min_ver"]
            max_ver = row["max_ver"]

            # Fetch old and new state for evidence
            old_snap = self.conn.execute(
                """SELECT state_json, config_address, fetched_at
                   FROM config_snapshots
                   WHERE config_type = ? AND version = ?""",
                (config_type, min_ver),
            ).fetchone()

            new_snap = self.conn.execute(
                """SELECT state_json, config_address, fetched_at
                   FROM config_snapshots
                   WHERE config_type = ? AND version = ?""",
                (config_type, max_ver),
            ).fetchone()

            address = ""
            evidence: dict = {
                "config_type": config_type,
                "old_version": min_ver,
                "new_version": max_ver,
                "version_count": row["ver_count"],
            }

            if old_snap:
                evidence["old_state"] = old_snap["state_json"]
                evidence["old_fetched_at"] = old_snap["fetched_at"]
                address = old_snap["config_address"]
            if new_snap:
                evidence["new_state"] = new_snap["state_json"]
                evidence["new_fetched_at"] = new_snap["fetched_at"]
                address = new_snap["config_address"]

            evidence["description"] = (
                f"{config_type} config version changed from "
                f"{min_ver} to {max_ver} — game parameter modification"
            )

            anomalies.append(
                Anomaly(
                    anomaly_type="CONFIG_VERSION_CHANGE",
                    rule_id="CC1",
                    detector=self.name,
                    object_id=address or config_type,
                    evidence=evidence,
                )
            )
        return anomalies

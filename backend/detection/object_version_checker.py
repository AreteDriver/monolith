"""Object version checker — detects state rollbacks and unauthorized modifications.

Rules:
  OV1 — State rollback: object version decreased between snapshots (should never happen on Sui)
  OV2 — State modification without event: version bumped but no matching chain_event
"""

import logging
import time

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)


class ObjectVersionChecker(BaseChecker):
    """Checks object version integrity on Sui — rollbacks and untracked mutations."""

    name = "object_version_checker"

    def check(self) -> list[Anomaly]:
        """Run all object version rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_ov1_rollback())
        anomalies.extend(self._check_ov2_untracked_mutation())
        return anomalies

    def _check_ov1_rollback(self) -> list[Anomaly]:
        """OV1: Detect version decreases — Sui versions are monotonically increasing."""
        rows = self.conn.execute(
            """SELECT ov1.object_id,
                      ov1.version AS older_version,
                      ov2.version AS newer_version,
                      ov1.fetched_at AS older_fetched,
                      ov2.fetched_at AS newer_fetched
               FROM object_versions ov1
               JOIN object_versions ov2
                 ON ov1.object_id = ov2.object_id
                AND ov2.fetched_at > ov1.fetched_at
                AND ov2.version < ov1.version
               LIMIT 200"""
        ).fetchall()

        anomalies = []
        seen = set()
        for row in rows:
            obj_id = row["object_id"]
            if obj_id in seen:
                continue
            seen.add(obj_id)

            anomalies.append(
                Anomaly(
                    anomaly_type="STATE_ROLLBACK",
                    rule_id="OV1",
                    detector=self.name,
                    object_id=obj_id,
                    evidence={
                        "older_version": row["older_version"],
                        "newer_version": row["newer_version"],
                        "older_fetched_at": row["older_fetched"],
                        "newer_fetched_at": row["newer_fetched"],
                        "description": (
                            f"State rollback — {obj_id[:16]}... version went "
                            f"backward from {row['older_version']} to "
                            f"{row['newer_version']}. History was rewritten"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"version:{obj_id}:{row['older_version']}",
                            timestamp=row["older_fetched"],
                            derivation=(f"OV1: v{row['older_version']} at {row['older_fetched']}"),
                        ),
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"version:{obj_id}:{row['newer_version']}",
                            timestamp=row["newer_fetched"],
                            derivation=(
                                f"OV1: regressed to"
                                f" v{row['newer_version']}"
                                f" at {row['newer_fetched']}"
                            ),
                        ),
                    ],
                )
            )
        return anomalies

    def _check_ov2_untracked_mutation(self) -> list[Anomaly]:
        """OV2: Version bumped in last 24h but no chain_event for the object."""
        cutoff = int(time.time()) - 86400

        # Objects with 2+ versions fetched in the last 24h
        rows = self.conn.execute(
            """SELECT object_id,
                      MIN(version) AS min_ver,
                      MAX(version) AS max_ver,
                      MIN(fetched_at) AS first_fetch,
                      MAX(fetched_at) AS last_fetch
               FROM object_versions
               WHERE fetched_at >= ?
               GROUP BY object_id
               HAVING COUNT(*) >= 2 AND max_ver > min_ver
               LIMIT 500""",
            (cutoff,),
        ).fetchall()

        anomalies = []
        for row in rows:
            obj_id = row["object_id"]
            # Check for any chain event for this object in the window
            event_row = self.conn.execute(
                """SELECT 1 FROM chain_events
                   WHERE object_id = ? AND timestamp >= ? AND timestamp <= ?
                   LIMIT 1""",
                (obj_id, row["first_fetch"], row["last_fetch"]),
            ).fetchone()

            if event_row is not None:
                continue  # event exists — mutation is explained

            anomalies.append(
                Anomaly(
                    anomaly_type="UNAUTHORIZED_STATE_MODIFICATION",
                    rule_id="OV2",
                    detector=self.name,
                    object_id=obj_id,
                    evidence={
                        "min_version": row["min_ver"],
                        "max_version": row["max_ver"],
                        "version_delta": row["max_ver"] - row["min_ver"],
                        "window_start": row["first_fetch"],
                        "window_end": row["last_fetch"],
                        "description": (
                            f"Unauthorized mod — {obj_id[:16]}... mutated "
                            f"from v{row['min_ver']} to v{row['max_ver']} "
                            f"with no chain event to explain it"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"versions:{obj_id}:{row['min_ver']}-{row['max_ver']}",
                            timestamp=row["last_fetch"],
                            derivation=(
                                f"OV2: v{row['min_ver']}→v{row['max_ver']} no chain events"
                            ),
                        )
                    ],
                )
            )
        return anomalies

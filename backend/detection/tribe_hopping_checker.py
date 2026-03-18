"""Tribe-hopping checker — detects rapid corporation changes.

Rules:
  TH1 — Rapid tribe changes: character object shows 3+ different tribe_id
         values in version history within 30 days. Suggests spy activity
         or asset shuffling across corps.
"""

import json
import logging
import time

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)

MIN_TRIBE_COUNT = 3
WINDOW_SECONDS = 30 * 86400  # 30 days


class TribeHoppingChecker(BaseChecker):
    """Checks for characters rapidly switching tribes/corps."""

    name = "tribe_hopping_checker"

    def check(self) -> list[Anomaly]:
        """Run tribe hopping rules."""
        return self._check_th1_rapid_changes()

    def _check_th1_rapid_changes(self) -> list[Anomaly]:
        """TH1: 3+ distinct tribe_ids in version history = rapid hopping."""
        cutoff = int(time.time()) - WINDOW_SECONDS

        # Get character object IDs from entity_names
        char_rows = self.conn.execute(
            """SELECT entity_id FROM entity_names
               WHERE entity_type = 'character'
               LIMIT 5000"""
        ).fetchall()

        char_ids = {row["entity_id"] for row in char_rows}
        if not char_ids:
            return []

        # Get all object_versions for these characters in the window
        placeholders = ",".join("?" for _ in char_ids)
        query = (
            "SELECT object_id, state_json FROM object_versions "  # noqa: S608
            f"WHERE object_id IN ({placeholders}) "
            "AND fetched_at >= ? ORDER BY object_id, fetched_at ASC"
        )
        version_rows = self.conn.execute(
            query,
            [*char_ids, cutoff],
        ).fetchall()

        # Group tribe_ids per object
        object_tribes: dict[str, set[str]] = {}
        for row in version_rows:
            obj_id = row["object_id"]
            try:
                state = json.loads(row["state_json"] or "{}")
            except json.JSONDecodeError:
                continue
            tribe_id = state.get("tribe_id", "")
            if tribe_id:
                if obj_id not in object_tribes:
                    object_tribes[obj_id] = set()
                object_tribes[obj_id].add(str(tribe_id))

        anomalies = []
        for obj_id, tribes in object_tribes.items():
            if len(tribes) >= MIN_TRIBE_COUNT:
                anomalies.append(
                    Anomaly(
                        anomaly_type="RAPID_TRIBE_CHANGE",
                        rule_id="TH1",
                        detector=self.name,
                        object_id=obj_id,
                        evidence={
                            "tribe_ids": sorted(tribes),
                            "tribe_count": len(tribes),
                            "window_days": 30,
                            "description": (
                                f"Drifter — {obj_id[:16]}... flew "
                                f"{len(tribes)} flags in 30 days. "
                                f"Loyalty to none. Possible spy or asset runner"
                            ),
                        },
                    )
                )
        return anomalies

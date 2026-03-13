"""Detection engine — orchestrates all checkers, persists anomalies, deduplicates."""

import json
import logging
import sqlite3
import time

from backend.detection.assembly_checker import AssemblyChecker
from backend.detection.base import Anomaly, BaseChecker
from backend.detection.continuity_checker import ContinuityChecker
from backend.detection.economic_checker import EconomicChecker
from backend.detection.sequence_checker import SequenceChecker

logger = logging.getLogger(__name__)


class DetectionEngine:
    """Orchestrates all detection checkers and stores results.

    Runs as a periodic background task. Deduplicates anomalies by
    (anomaly_type, object_id) to avoid flooding on repeated cycles.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._checkers: list[BaseChecker] = []
        self._register_all_checkers()

    def _register_all_checkers(self) -> None:
        """Register all checker instances.

        NOTE: PodChecker (P1 rule) is async and cannot be registered here.
        It requires a PodVerifier + httpx.AsyncClient and must be called via
        run_async() from an async context. See backend/detection/pod_checker.py.
        TODO: Wire PodChecker into detection_loop when async detection is supported,
        or run it as a separate async background task alongside run_cycle().
        """
        self._checkers = [
            ContinuityChecker(self.conn),
            EconomicChecker(self.conn),
            AssemblyChecker(self.conn),
            SequenceChecker(self.conn),
        ]
        for checker in self._checkers:
            logger.info("Registered checker: %s", checker.name)

    def run_cycle(self) -> list[dict]:
        """Run all checkers and persist new anomalies. Returns list of new anomaly dicts."""
        all_anomalies: list[Anomaly] = []

        for checker in self._checkers:
            try:
                found = checker.check()
                if found:
                    logger.info("%s found %d anomalies", checker.name, len(found))
                all_anomalies.extend(found)
            except Exception:
                logger.exception("Checker %s failed", checker.name)

        # Deduplicate and persist
        new_anomalies = []
        for anomaly in all_anomalies:
            if self._is_duplicate(anomaly):
                continue
            if self._store_anomaly(anomaly):
                new_anomalies.append(anomaly.to_dict())

        if new_anomalies:
            self.conn.commit()
            logger.info(
                "Detection cycle complete: %d new anomalies (from %d total detected)",
                len(new_anomalies),
                len(all_anomalies),
            )
        return new_anomalies

    def _is_duplicate(self, anomaly: Anomaly) -> bool:
        """Check if this anomaly type+object was already detected recently (last 24h)."""
        cutoff = int(time.time()) - 86400
        row = self.conn.execute(
            """SELECT 1 FROM anomalies
               WHERE anomaly_type = ? AND object_id = ? AND detected_at >= ?
               LIMIT 1""",
            (anomaly.anomaly_type, anomaly.object_id, cutoff),
        ).fetchone()
        return row is not None

    def _store_anomaly(self, anomaly: Anomaly) -> bool:
        """Store an anomaly in the database. Returns True if stored."""
        try:
            self.conn.execute(
                """INSERT INTO anomalies
                   (anomaly_id, anomaly_type, severity, category, detector,
                    rule_id, object_id, system_id, detected_at, evidence_json, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNVERIFIED')""",
                (
                    anomaly.anomaly_id,
                    anomaly.anomaly_type,
                    anomaly.severity,
                    anomaly.category,
                    anomaly.detector,
                    anomaly.rule_id,
                    anomaly.object_id,
                    anomaly.system_id,
                    anomaly.detected_at,
                    json.dumps(anomaly.evidence),
                ),
            )
            return True
        except sqlite3.IntegrityError:
            # Duplicate anomaly_id — regenerate and retry once
            anomaly.anomaly_id = f"{anomaly.anomaly_id}-{int(time.time()) % 1000:03d}"
            try:
                self.conn.execute(
                    """INSERT INTO anomalies
                       (anomaly_id, anomaly_type, severity, category, detector,
                        rule_id, object_id, system_id, detected_at, evidence_json, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNVERIFIED')""",
                    (
                        anomaly.anomaly_id,
                        anomaly.anomaly_type,
                        anomaly.severity,
                        anomaly.category,
                        anomaly.detector,
                        anomaly.rule_id,
                        anomaly.object_id,
                        anomaly.system_id,
                        anomaly.detected_at,
                        json.dumps(anomaly.evidence),
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                logger.warning("Could not store anomaly %s — duplicate", anomaly.anomaly_id)
                return False

    def get_anomaly_counts(self) -> dict:
        """Get anomaly counts by severity and type — for stats."""
        by_severity = {}
        rows = self.conn.execute(
            "SELECT severity, COUNT(*) as cnt FROM anomalies GROUP BY severity"
        ).fetchall()
        for row in rows:
            by_severity[row["severity"]] = row["cnt"]

        by_type = {}
        rows = self.conn.execute(
            "SELECT anomaly_type, COUNT(*) as cnt FROM anomalies GROUP BY anomaly_type"
        ).fetchall()
        for row in rows:
            by_type[row["anomaly_type"]] = row["cnt"]

        return {"by_severity": by_severity, "by_type": by_type}

"""Detection engine — orchestrates all checkers and writes anomalies."""

import logging
import sqlite3

logger = logging.getLogger(__name__)


class DetectionEngine:
    """Orchestrates all detection checkers against new events.

    Runs as a periodic background task. Each checker is a pure function
    that receives events/states and returns anomaly dicts or None.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._checkers: list = []

    def register_checker(self, checker) -> None:
        """Register a detection checker."""
        self._checkers.append(checker)
        logger.info("Registered checker: %s", checker.__class__.__name__)

    async def run_cycle(self) -> list[dict]:
        """Run all checkers against unprocessed events. Returns new anomalies."""
        # Skeleton — checkers will be implemented in Sprint 2
        anomalies: list[dict] = []
        logger.debug("Detection cycle: %d checkers registered", len(self._checkers))
        return anomalies

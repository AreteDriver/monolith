"""Sequence checker — detects temporal violations and duplicate transactions.

Rules:
  S1 — Temporal violation: event B depends on A but has earlier timestamp
  S2 — Duplicate transaction: same transaction hash processed multiple times
  S3 — Missing prerequisite: event requires prior event that doesn't exist
  S4 — Block processing gap: large gap in processed block numbers
"""

import logging

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)

# Maximum acceptable block gap before flagging
BLOCK_GAP_THRESHOLD = 100


class SequenceChecker(BaseChecker):
    """Checks event ordering and chain processing integrity."""

    name = "sequence_checker"

    def check(self) -> list[Anomaly]:
        """Run all sequence rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_s2_duplicate_transactions())
        anomalies.extend(self._check_s4_block_gaps())
        # S1 (temporal violation) and S3 (missing prerequisite) require
        # decoded event dependency graph — activated after MUD event decoding
        return anomalies

    def _check_s2_duplicate_transactions(self) -> list[Anomaly]:
        """S2: Same transaction hash appears more than expected.

        A single transaction can emit multiple log entries (different log indexes),
        but the same (tx_hash, log_index) pair should never appear twice.
        We check for suspiciously high event counts per transaction.
        """
        rows = self.conn.execute(
            """SELECT transaction_hash, COUNT(*) as cnt,
                      MIN(block_number) as block,
                      GROUP_CONCAT(DISTINCT event_type) as event_types
               FROM chain_events
               WHERE transaction_hash != ''
               GROUP BY transaction_hash
               HAVING cnt > 20
               ORDER BY cnt DESC
               LIMIT 50"""
        ).fetchall()

        anomalies = []
        for row in rows:
            anomalies.append(
                Anomaly(
                    anomaly_type="DUPLICATE_TRANSACTION",
                    rule_id="S2",
                    detector=self.name,
                    object_id=row["transaction_hash"],
                    evidence={
                        "transaction_hash": row["transaction_hash"],
                        "event_count": row["cnt"],
                        "block_number": row["block"],
                        "event_types": row["event_types"],
                        "description": (
                            f"Transaction {row['transaction_hash'][:18]}... emitted "
                            f"{row['cnt']} events — suspiciously high count"
                        ),
                    },
                )
            )
        return anomalies

    def _check_s4_block_gaps(self) -> list[Anomaly]:
        """S4: Large gap in processed block numbers.

        If we processed block 1000 then block 1200 with nothing in between,
        we may have missed events. This could indicate an RPC issue or
        indexer gap rather than a chain issue.
        """
        rows = self.conn.execute(
            """SELECT block_number FROM chain_events
               WHERE block_number > 0
               GROUP BY block_number
               ORDER BY block_number ASC"""
        ).fetchall()

        if len(rows) < 2:
            return []

        anomalies = []
        blocks = [r["block_number"] for r in rows]

        for i in range(1, len(blocks)):
            gap = blocks[i] - blocks[i - 1]
            if gap > BLOCK_GAP_THRESHOLD:
                anomalies.append(
                    Anomaly(
                        anomaly_type="BLOCK_PROCESSING_GAP",
                        rule_id="S4",
                        detector=self.name,
                        object_id=f"blocks:{blocks[i - 1]}-{blocks[i]}",
                        evidence={
                            "from_block": blocks[i - 1],
                            "to_block": blocks[i],
                            "gap_size": gap,
                            "threshold": BLOCK_GAP_THRESHOLD,
                            "description": (
                                f"Block gap of {gap} between block "
                                f"{blocks[i - 1]} and {blocks[i]} — "
                                f"may indicate missed events"
                            ),
                        },
                    )
                )

        return anomalies

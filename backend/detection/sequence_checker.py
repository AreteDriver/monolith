"""Sequence checker — detects temporal violations and duplicate transactions.

Rules:
  S1 — Temporal violation: event B depends on A but has earlier timestamp
  S2 — Duplicate transaction: same transaction hash processed multiple times
  S3 — Missing prerequisite: event requires prior event that doesn't exist
  S4 — Block processing gap: large gap in processed block numbers
"""

import logging

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

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
        # a cross-event dependency graph — deferred until event volume
        # justifies the complexity
        return anomalies

    def _check_s2_duplicate_transactions(self) -> list[Anomaly]:
        """S2: Suspiciously high event count per transaction.

        A single transaction legitimately emits many events — fuel ticks
        batch-update 20-30+ assemblies per tx (BURNING_UPDATED). We exclude
        fuel-only transactions and flag remaining high-count txs that could
        indicate replay attacks or ingestion bugs.

        Threshold: >50 non-fuel events per transaction.
        """
        rows = self.conn.execute(
            """SELECT transaction_hash, COUNT(*) as cnt,
                      MIN(block_number) as block,
                      GROUP_CONCAT(DISTINCT event_type) as event_types
               FROM chain_events
               WHERE transaction_hash != ''
                 AND event_type NOT LIKE '%::fuel::FuelEvent'
               GROUP BY transaction_hash
               HAVING cnt > 50
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
                            f"Event storm — tx {row['transaction_hash'][:18]}... "
                            f"fired {row['cnt']} non-fuel events. "
                            f"Possible replay or ingestion anomaly"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="chain_event",
                            source_id=row["transaction_hash"],
                            timestamp=0,
                            derivation=(
                                f"S2: {row['cnt']} non-fuel events"
                                f" types: {row['event_types'][:50]}"
                            ),
                        )
                    ],
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
                                f"Blind spot — {gap} blocks dark between "
                                f"{blocks[i - 1]} and {blocks[i]}. "
                                f"Anything could have happened"
                            ),
                        },
                        provenance=[
                            ProvenanceEntry(
                                source_type="chain_event",
                                source_id=f"blocks:{blocks[i - 1]}-{blocks[i]}",
                                timestamp=0,
                                derivation=(
                                    f"S4: {gap}-block gap"
                                    f" {blocks[i - 1]}-{blocks[i]}"
                                ),
                            )
                        ],
                    )
                )

        return anomalies

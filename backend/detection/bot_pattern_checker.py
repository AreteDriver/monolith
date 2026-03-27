"""Bot pattern checker — detects automated transaction patterns.

Rules:
  BP1 — Bot-like activity: wallet has 10+ transactions with coefficient of
         variation (stddev/mean) < 0.15 on inter-transaction intervals,
         suggesting automated/scripted behavior.
"""

import logging

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)

MIN_TX_COUNT = 10
MAX_CV = 0.15


class BotPatternChecker(BaseChecker):
    """Checks wallet activity profiles for bot-like regularity."""

    name = "bot_pattern_checker"

    def check(self) -> list[Anomaly]:
        """Run bot detection rules."""
        return self._check_bp1_regular_intervals()

    def _check_bp1_regular_intervals(self) -> list[Anomaly]:
        """BP1: Low coefficient of variation on tx intervals = bot pattern."""
        rows = self.conn.execute(
            """SELECT wallet_address, tx_count,
                      avg_interval_seconds, interval_stddev
               FROM wallet_activity
               WHERE tx_count >= ?
                 AND avg_interval_seconds > 0
               LIMIT 1000""",
            (MIN_TX_COUNT,),
        ).fetchall()

        anomalies = []
        for row in rows:
            avg_interval = row["avg_interval_seconds"]
            stddev = row["interval_stddev"]
            if stddev is None or avg_interval is None:
                continue

            cv = stddev / avg_interval
            if cv < MAX_CV:
                anomalies.append(
                    Anomaly(
                        anomaly_type="BOT_PATTERN",
                        rule_id="BP1",
                        detector=self.name,
                        object_id=row["wallet_address"],
                        evidence={
                            "wallet": row["wallet_address"],
                            "tx_count": row["tx_count"],
                            "avg_interval_seconds": round(avg_interval, 2),
                            "interval_stddev": round(stddev, 2),
                            "coefficient_of_variation": round(cv, 4),
                            "description": (
                                f"Drone signature — {row['wallet_address'][:16]}... "
                                f"running {row['tx_count']} txns at machine-perfect "
                                f"intervals ({avg_interval:.1f}s avg, CV={cv:.4f}). "
                                f"No human is this regular"
                            ),
                        },
                        provenance=[
                            ProvenanceEntry(
                                source_type="detection_rule",
                                source_id=f"wallet:{row['wallet_address']}",
                                timestamp=0,
                                derivation=(f"BP1: {row['tx_count']} txns, CV={cv:.4f} < {MAX_CV}"),
                            )
                        ],
                    )
                )
        return anomalies

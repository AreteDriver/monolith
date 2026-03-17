"""Wallet concentration checker — detects unusual asset accumulation.

Rules:
  WC1 — Asset concentration: single wallet involved in >50% of transactions
         in a system within the last 24h, with 10+ events minimum.
"""

import json
import logging
import time
from collections import defaultdict

from backend.detection.base import Anomaly, BaseChecker

logger = logging.getLogger(__name__)


class WalletConcentrationChecker(BaseChecker):
    """Checks for wallet dominance in system-level transaction activity."""

    name = "wallet_concentration_checker"

    def check(self) -> list[Anomaly]:
        """Run wallet concentration rules."""
        return self._check_wc1_concentration()

    def _check_wc1_concentration(self) -> list[Anomaly]:
        """WC1: Single wallet >50% of events in a system (min 10 events)."""
        cutoff = int(time.time()) - 86400

        rows = self.conn.execute(
            """SELECT system_id, raw_json
               FROM chain_events
               WHERE timestamp >= ? AND system_id != ''
               LIMIT 10000""",
            (cutoff,),
        ).fetchall()

        # system_id -> {sender -> count}
        system_senders: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        system_totals: dict[str, int] = defaultdict(int)

        for row in rows:
            sys_id = row["system_id"]
            try:
                raw = json.loads(row["raw_json"] or "{}")
            except json.JSONDecodeError:
                continue
            sender = raw.get("sender", "")
            if not sender:
                continue
            system_senders[sys_id][sender] += 1
            system_totals[sys_id] += 1

        anomalies = []
        for sys_id, senders in system_senders.items():
            total = system_totals[sys_id]
            if total < 10:
                continue

            for wallet, count in senders.items():
                ratio = count / total
                if ratio > 0.5:
                    anomalies.append(
                        Anomaly(
                            anomaly_type="ASSET_CONCENTRATION",
                            rule_id="WC1",
                            detector=self.name,
                            object_id=wallet,
                            system_id=sys_id,
                            evidence={
                                "wallet": wallet,
                                "event_count": count,
                                "system_total": total,
                                "concentration_ratio": round(ratio, 3),
                                "description": (
                                    f"Wallet {wallet[:16]}... accounts for "
                                    f"{count}/{total} ({ratio:.0%}) of events "
                                    f"in system {sys_id}"
                                ),
                            },
                        )
                    )
        return anomalies

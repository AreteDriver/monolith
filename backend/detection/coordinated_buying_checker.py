"""Coordinated buying checker — detects clustered intel acquisition signals.

Rules:
  CB1 — Coordinated intel acquisition: 3+ unique wallets transacting in the
        same region within a 10-minute window. Leading indicator of fleet action.
  CB2 — Fleet action likely: 5+ unique buyers OR 3+ buyers acquiring fleet-type
        intel in the same region within a 10-minute window.

Data source: chain_events with inventory or economic activity clustered by
region (via system_id → region mapping in reference_data).
"""

import contextlib
import json
import logging
import time
from collections import defaultdict

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)

# Detection window in seconds
WINDOW_SECONDS = 600  # 10 minutes

# Minimum unique buyers to trigger
MIN_BUYERS_MEDIUM = 3
MIN_BUYERS_CRITICAL = 5
MIN_FLEET_INTEL_CRITICAL = 3


class CoordinatedBuyingChecker(BaseChecker):
    """Detects coordinated wallet activity targeting the same region.

    Watches for clusters of distinct wallets performing transactions
    (item deposits, withdrawals, mints) in the same solar system or
    region within a short time window — a leading indicator of
    coordinated fleet staging or intel acquisition.
    """

    name = "coordinated_buying_checker"

    def check(self) -> list[Anomaly]:
        """Run coordinated buying detection rules."""
        anomalies: list[Anomaly] = []
        clusters = self._find_wallet_clusters()
        for region, cluster in clusters.items():
            anomaly = self._evaluate_cluster(region, cluster)
            if anomaly:
                anomalies.append(anomaly)
        return anomalies

    def _find_wallet_clusters(self) -> dict[str, list[dict]]:
        """Find clusters of wallet activity grouped by system/region.

        Scans recent chain events for distinct sender addresses
        performing economic actions (item transfers, deposits, mints)
        in the same system within the detection window.
        """
        cutoff = int(time.time()) - WINDOW_SECONDS

        # Economic event types that indicate wallet-driven transactions
        rows = self.conn.execute(
            """SELECT ce.event_id, ce.event_type, ce.object_id, ce.system_id,
                      ce.timestamp, ce.raw_json
               FROM chain_events ce
               WHERE ce.timestamp >= ?
                 AND ce.system_id != ''
                 AND (ce.event_type LIKE '%ItemDeposited%'
                      OR ce.event_type LIKE '%ItemWithdrawn%'
                      OR ce.event_type LIKE '%ItemMinted%'
                      OR ce.event_type LIKE '%OwnerCapTransferred%')
               ORDER BY ce.timestamp ASC""",
            (cutoff,),
        ).fetchall()

        # Group by system_id (proxy for region)
        clusters: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            event = dict(row)
            # Extract sender/buyer address from raw event JSON
            raw = {}
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                raw = json.loads(event.get("raw_json", "{}"))

            sender = raw.get("sender", "")
            if not sender:
                continue

            event["sender"] = sender
            event["intel_type"] = self._classify_intel_type(event["event_type"])
            clusters[event["system_id"]].append(event)

        return dict(clusters)

    def _classify_intel_type(self, event_type: str) -> str:
        """Classify event type into intel category."""
        lower = event_type.lower()
        if "transferred" in lower:
            return "fleet"  # Ownership transfers suggest fleet staging
        if "deposited" in lower or "withdrawn" in lower:
            return "resource"  # Supply chain activity
        if "minted" in lower:
            return "base"  # New asset creation
        return "unknown"

    def _evaluate_cluster(self, system_id: str, events: list[dict]) -> Anomaly | None:
        """Evaluate a cluster of events for coordinated buying signals."""
        unique_buyers = {e["sender"] for e in events}
        buyer_count = len(unique_buyers)
        fleet_intel_count = sum(1 for e in events if e.get("intel_type") == "fleet")

        # CB2: Fleet action likely
        if buyer_count >= MIN_BUYERS_CRITICAL or (
            buyer_count >= MIN_BUYERS_MEDIUM and fleet_intel_count >= MIN_FLEET_INTEL_CRITICAL
        ):
            return Anomaly(
                anomaly_type="COORDINATED_BUYING",
                rule_id="CB2",
                detector=self.name,
                object_id=system_id,
                system_id=system_id,
                evidence={
                    "description": (
                        f"Fleet mobilization — {buyer_count} wallets "
                        f"arming up in system {system_id}. "
                        f"Something's about to happen"
                    ),
                    "buyer_count": buyer_count,
                    "fleet_intel_count": fleet_intel_count,
                    "total_events": len(events),
                    "buyers": sorted(unique_buyers)[:10],
                    "window_seconds": WINDOW_SECONDS,
                    "confidence": 0.92,
                },
                provenance=[
                    ProvenanceEntry(
                        source_type="chain_event",
                        source_id=f"cluster:{system_id}",
                        timestamp=events[0].get("timestamp", 0) if events else 0,
                        derivation=(
                            f"CB2: {buyer_count} wallets,"
                            f" {fleet_intel_count} fleet intel"
                            f" in {WINDOW_SECONDS}s"
                        ),
                    )
                ],
            )

        # CB1: Coordinated acquisition detected
        if buyer_count >= MIN_BUYERS_MEDIUM:
            return Anomaly(
                anomaly_type="COORDINATED_BUYING",
                rule_id="CB1",
                detector=self.name,
                object_id=system_id,
                system_id=system_id,
                evidence={
                    "description": (
                        f"Convoy forming — {buyer_count} wallets "
                        f"transacting in system {system_id} within "
                        f"a {WINDOW_SECONDS // 60}-minute window"
                    ),
                    "buyer_count": buyer_count,
                    "fleet_intel_count": fleet_intel_count,
                    "total_events": len(events),
                    "buyers": sorted(unique_buyers)[:10],
                    "window_seconds": WINDOW_SECONDS,
                    "confidence": 0.65,
                },
                provenance=[
                    ProvenanceEntry(
                        source_type="chain_event",
                        source_id=f"cluster:{system_id}",
                        timestamp=events[0].get("timestamp", 0) if events else 0,
                        derivation=(f"CB1: {buyer_count} wallets in {WINDOW_SECONDS // 60}min"),
                    )
                ],
            )

        return None

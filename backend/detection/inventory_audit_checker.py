"""Inventory audit checker — detects conservation-of-mass violations.

Rules:
  IA1 — Inventory conservation violation: net item flow for an assembly
         (deposits - withdrawals - burns) doesn't match expected balance
         based on the item_ledger.
"""

import logging

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)

# Event types that add items
_INFLOW_TYPES = frozenset({"ItemDepositedEvent", "ItemMintedEvent"})
# Event types that remove items
_OUTFLOW_TYPES = frozenset({"ItemWithdrawnEvent", "ItemBurnedEvent", "ItemDestroyedEvent"})


class InventoryAuditChecker(BaseChecker):
    """Checks item ledger conservation — items cannot appear or vanish."""

    name = "inventory_audit_checker"

    def check(self) -> list[Anomaly]:
        """Run inventory audit rules."""
        return self._check_ia1_conservation()

    def _check_ia1_conservation(self) -> list[Anomaly]:
        """IA1: Net item flow < 0 for any assembly+item_type = conservation violation."""
        rows = self.conn.execute(
            """SELECT assembly_id, item_type_id, event_type,
                      SUM(quantity) AS total_qty
               FROM item_ledger
               GROUP BY assembly_id, item_type_id, event_type"""
        ).fetchall()

        # Aggregate per (assembly_id, item_type_id)
        balances: dict[tuple[str, str], int] = {}
        for row in rows:
            key = (row["assembly_id"], row["item_type_id"])
            qty = row["total_qty"]
            if row["event_type"] in _INFLOW_TYPES:
                balances[key] = balances.get(key, 0) + qty
            elif row["event_type"] in _OUTFLOW_TYPES:
                balances[key] = balances.get(key, 0) - qty

        anomalies = []
        for (assembly_id, item_type_id), net in balances.items():
            if net < 0:
                # Look up system_id from objects table
                obj = self._get_object(assembly_id)
                system_id = obj.get("system_id", "") if obj else ""

                anomalies.append(
                    Anomaly(
                        anomaly_type="INVENTORY_CONSERVATION_VIOLATION",
                        rule_id="IA1",
                        detector=self.name,
                        object_id=assembly_id,
                        system_id=system_id,
                        evidence={
                            "assembly_id": assembly_id,
                            "item_type_id": item_type_id,
                            "net_balance": net,
                            "description": (
                                f"Matter violation — {assembly_id[:16]}... shows "
                                f"net {net} for item {item_type_id[:16]}... "
                                f"More left than ever arrived. Conservation broken"
                            ),
                        },
                        provenance=[
                            ProvenanceEntry(
                                source_type="detection_rule",
                                source_id=f"ledger:{assembly_id}:{item_type_id}",
                                timestamp=0,
                                derivation=(
                                    f"IA1: net {net} for {item_type_id[:16]} — more out than in"
                                ),
                            )
                        ],
                    )
                )
        return anomalies

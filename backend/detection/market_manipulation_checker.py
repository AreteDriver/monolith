"""Market manipulation checker — detects wash trading, price fixing, artificial scarcity.

Rules:
  MM1 — Wash trading: Same wallet (or wallets in the same corp) trading items
         back and forth between assemblies they both own. Circular flow
         with no net economic purpose.
  MM2 — Price fixing: Multiple assemblies in the same system setting identical
         non-default fuel/toll prices within a short window. Coordinated
         pricing that suppresses competition.
  MM3 — Artificial scarcity: Single wallet hoarding >60% of a specific item
         type across all tracked assemblies. Cornering supply to manipulate
         perceived value.
"""

import json
import logging
import time
from collections import defaultdict

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)

# Detection parameters
WASH_LOOKBACK_SECONDS = 3600  # 1 hour
WASH_MIN_ROUND_TRIPS = 2  # minimum cycles to flag
PRICE_FIX_WINDOW_SECONDS = 1800  # 30 minutes
PRICE_FIX_MIN_ASSEMBLIES = 3  # minimum assemblies with same price
SCARCITY_THRESHOLD = 0.60  # 60% of total supply


class MarketManipulationChecker(BaseChecker):
    """Detects market manipulation patterns from on-chain economic activity.

    Watches for circular item flows (wash trading), coordinated pricing
    (price fixing), and monopolistic hoarding (artificial scarcity).
    These patterns indicate manipulation of marketplace registries like
    KARUM's ShopRegistry or any future on-chain commerce layer.
    """

    name = "market_manipulation_checker"

    def check(self) -> list[Anomaly]:
        """Run all market manipulation rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_mm1_wash_trading())
        anomalies.extend(self._check_mm2_price_fixing())
        anomalies.extend(self._check_mm3_artificial_scarcity())
        return anomalies

    def _check_mm1_wash_trading(self) -> list[Anomaly]:
        """MM1: Circular item flows between wallets — wash trading signal.

        Looks for deposit/withdraw pairs where the same item type moves
        between two assemblies owned by the same wallet (or wallets that
        transact exclusively with each other) within a short window.
        """
        cutoff = int(time.time()) - WASH_LOOKBACK_SECONDS

        try:
            rows = self.conn.execute(
                """SELECT il1.assembly_id as src_assembly,
                          il2.assembly_id as dst_assembly,
                          il1.item_type_id,
                          COUNT(*) as round_trips,
                          SUM(il1.quantity) as total_volume
                   FROM item_ledger il1
                   JOIN item_ledger il2
                     ON il1.item_type_id = il2.item_type_id
                     AND il1.assembly_id != il2.assembly_id
                     AND il1.event_type = 'withdrawn'
                     AND il2.event_type = 'deposited'
                     AND ABS(il1.timestamp - il2.timestamp) < 300
                     AND il1.timestamp >= ?
                   GROUP BY il1.assembly_id, il2.assembly_id, il1.item_type_id
                   HAVING round_trips >= ?
                   LIMIT 50""",
                (cutoff, WASH_MIN_ROUND_TRIPS),
            ).fetchall()
        except Exception:
            # item_ledger may not exist in older databases
            return []

        anomalies = []
        for row in rows:
            # Check if both assemblies share the same owner
            src_owner = self._get_assembly_owner(row["src_assembly"])
            dst_owner = self._get_assembly_owner(row["dst_assembly"])
            same_owner = src_owner and dst_owner and src_owner == dst_owner

            confidence = 0.85 if same_owner else 0.55
            # Same owner moving items back and forth is a stronger signal
            if not same_owner and row["round_trips"] < 3:
                continue

            system_id = self._resolve_system(row["src_assembly"])
            anomalies.append(
                Anomaly(
                    anomaly_type="WASH_TRADING",
                    rule_id="MM1",
                    detector=self.name,
                    object_id=row["src_assembly"],
                    system_id=system_id,
                    evidence={
                        "src_assembly": row["src_assembly"],
                        "dst_assembly": row["dst_assembly"],
                        "item_type_id": row["item_type_id"],
                        "round_trips": row["round_trips"],
                        "total_volume": row["total_volume"],
                        "same_owner": same_owner,
                        "confidence": confidence,
                        "description": (
                            f"Wash cycle — {row['round_trips']} round trips of "
                            f"item {row['item_type_id'][:16]}... between "
                            f"{row['src_assembly'][:16]}... and "
                            f"{row['dst_assembly'][:16]}..."
                            f"{' (same owner)' if same_owner else ''}"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="detection_rule",
                            source_id=f"wash:{row['src_assembly']}:{row['dst_assembly']}",
                            timestamp=cutoff,
                            derivation=(
                                f"MM1: {row['round_trips']} round trips"
                                f", same_owner={same_owner}"
                            ),
                        )
                    ],
                )
            )
        return anomalies

    def _check_mm2_price_fixing(self) -> list[Anomaly]:
        """MM2: Multiple assemblies setting identical prices in same system.

        Detects coordinated pricing by checking if 3+ assemblies in
        the same system changed their fuel/toll configuration to the
        same non-zero value within a short time window.
        """
        cutoff = int(time.time()) - PRICE_FIX_WINDOW_SECONDS

        # Look for config change events (fuel price, toll settings)
        try:
            rows = self.conn.execute(
                """SELECT ce.object_id, ce.system_id, ce.timestamp, ce.raw_json
                   FROM chain_events ce
                   WHERE ce.timestamp >= ?
                     AND ce.system_id != ''
                     AND (ce.event_type LIKE '%FuelEvent%'
                          OR ce.event_type LIKE '%ConfigChanged%'
                          OR ce.event_type LIKE '%TollSet%'
                          OR ce.event_type LIKE '%PriceChanged%')
                   ORDER BY ce.timestamp ASC""",
                (cutoff,),
            ).fetchall()
        except Exception:
            return []

        # Group by system and extract price values
        system_prices: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            event = dict(row)
            raw = {}
            try:
                raw = json.loads(event.get("raw_json", "{}") or "{}")
            except json.JSONDecodeError:
                continue

            price = self._extract_price(raw)
            if price is not None and price > 0:
                system_prices[event["system_id"]].append(
                    {
                        "object_id": event["object_id"],
                        "price": price,
                        "timestamp": event["timestamp"],
                    }
                )

        anomalies = []
        for system_id, entries in system_prices.items():
            # Group by price value
            by_price: dict[int, list[dict]] = defaultdict(list)
            for entry in entries:
                by_price[entry["price"]].append(entry)

            for price, matching in by_price.items():
                unique_assemblies = {e["object_id"] for e in matching}
                if len(unique_assemblies) >= PRICE_FIX_MIN_ASSEMBLIES:
                    anomalies.append(
                        Anomaly(
                            anomaly_type="PRICE_FIXING",
                            rule_id="MM2",
                            detector=self.name,
                            object_id=system_id,
                            system_id=system_id,
                            evidence={
                                "price_value": price,
                                "assembly_count": len(unique_assemblies),
                                "assemblies": sorted(unique_assemblies)[:10],
                                "window_seconds": PRICE_FIX_WINDOW_SECONDS,
                                "description": (
                                    f"Price cartel — {len(unique_assemblies)} assemblies "
                                    f"in system {system_id} all set price to {price} "
                                    f"within {PRICE_FIX_WINDOW_SECONDS // 60} minutes"
                                ),
                            },
                            provenance=[
                                ProvenanceEntry(
                                    source_type="chain_event",
                                    source_id=f"pricefix:{system_id}:{price}",
                                    timestamp=matching[0]["timestamp"],
                                    derivation=(
                                        f"MM2: {len(unique_assemblies)} assemblies"
                                        f" @ price={price}"
                                    ),
                                )
                            ],
                        )
                    )
        return anomalies

    def _check_mm3_artificial_scarcity(self) -> list[Anomaly]:
        """MM3: Single wallet hoarding majority of a specific item type.

        Checks item_ledger net balances per wallet. If one wallet holds
        >60% of total tracked supply for any item type, it's cornering
        the market — whether to manipulate prices or deny access.
        """
        try:
            rows = self.conn.execute(
                """SELECT assembly_id, item_type_id,
                          SUM(CASE WHEN event_type IN ('minted', 'deposited')
                              THEN quantity ELSE 0 END) -
                          SUM(CASE WHEN event_type IN ('burned', 'withdrawn')
                              THEN quantity ELSE 0 END) as net_balance
                   FROM item_ledger
                   GROUP BY assembly_id, item_type_id
                   HAVING net_balance > 0
                   LIMIT 2000"""
            ).fetchall()
        except Exception:
            return []

        # Build per-item-type totals and per-owner holdings
        item_totals: dict[str, int] = defaultdict(int)
        owner_holdings: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for row in rows:
            item_type = row["item_type_id"]
            balance = row["net_balance"]
            item_totals[item_type] += balance

            owner = self._get_assembly_owner(row["assembly_id"])
            if owner:
                owner_holdings[owner][item_type] += balance

        anomalies = []
        for owner, holdings in owner_holdings.items():
            for item_type, amount in holdings.items():
                total = item_totals.get(item_type, 0)
                if total <= 0:
                    continue
                share = amount / total
                if share >= SCARCITY_THRESHOLD and total >= 10:
                    anomalies.append(
                        Anomaly(
                            anomaly_type="ARTIFICIAL_SCARCITY",
                            rule_id="MM3",
                            detector=self.name,
                            object_id=owner,
                            evidence={
                                "wallet": owner,
                                "item_type_id": item_type,
                                "amount_held": amount,
                                "total_supply": total,
                                "market_share": round(share * 100, 1),
                                "description": (
                                    f"Supply cornered — wallet {owner[:16]}... "
                                    f"holds {share * 100:.0f}% of item "
                                    f"{item_type[:16]}... ({amount}/{total} units)"
                                ),
                            },
                            provenance=[
                                ProvenanceEntry(
                                    source_type="detection_rule",
                                    source_id=f"scarcity:{owner}:{item_type}",
                                    timestamp=0,
                                    derivation=(
                                        f"MM3: {share * 100:.0f}% share"
                                        f" ({amount}/{total})"
                                    ),
                                )
                            ],
                        )
                    )
        return anomalies

    def _get_assembly_owner(self, assembly_id: str) -> str:
        """Get the owner address of an assembly from the objects table."""
        row = self.conn.execute(
            "SELECT owner FROM objects WHERE object_id = ?", (assembly_id,)
        ).fetchone()
        if row:
            return row["owner"] or ""
        return ""

    def _resolve_system(self, assembly_id: str) -> str:
        """Resolve system_id for an assembly."""
        row = self.conn.execute(
            "SELECT system_id FROM objects WHERE object_id = ? AND system_id != ''",
            (assembly_id,),
        ).fetchone()
        return row["system_id"] if row else ""

    @staticmethod
    def _extract_price(raw: dict) -> int | None:
        """Extract a price/toll value from raw event JSON."""
        # Try common field names for price data
        for key in ("price", "toll", "fuel_price", "amount", "value", "new_price"):
            val = raw.get(key)
            if val is not None:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    continue
        # Nested in parsed_json
        parsed = raw.get("parsedJson", raw.get("parsed_json", {}))
        if isinstance(parsed, dict):
            for key in ("price", "toll", "amount", "value"):
                val = parsed.get(key)
                if val is not None:
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        continue
        return None

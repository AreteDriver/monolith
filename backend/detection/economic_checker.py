"""Economic checker — detects supply discrepancies, duplicate mints, negative balances.

Rules:
  E1 — Supply discrepancy: tracked fuel/item totals don't match expected from events
  E2 — Unexplained destruction: items vanished without combat/salvage event
  E3 — Duplicate mint: same creation event ID appears more than once
  E4 — Negative balance: any tracked quantity goes below zero
"""

import contextlib
import json
import logging
import sqlite3

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)


class EconomicChecker(BaseChecker):
    """Checks economic integrity — supply conservation, balance validity."""

    name = "economic_checker"

    def check(self) -> list[Anomaly]:
        """Run all economic rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_e1_supply_discrepancy())
        anomalies.extend(self._check_e1_item_supply())
        anomalies.extend(self._check_e2_unexplained_destruction())
        anomalies.extend(self._check_e3_duplicate_mint())
        anomalies.extend(self._check_e4_negative_balance())
        return anomalies

    def _check_e1_supply_discrepancy(self) -> list[Anomaly]:
        """E1: Fuel amounts changed between snapshots without matching events.

        Compares fuel.amount across consecutive snapshots for network nodes.
        If fuel decreased without a corresponding burn or withdraw event, flag it.
        """
        # Get network nodes with multiple snapshots
        rows = self.conn.execute(
            """SELECT ws1.object_id,
                      ws1.state_data as new_state, ws1.snapshot_time as new_time,
                      ws2.state_data as old_state, ws2.snapshot_time as old_time
               FROM world_states ws1
               JOIN world_states ws2 ON ws1.object_id = ws2.object_id
                 AND ws2.snapshot_time = (
                   SELECT MAX(snapshot_time) FROM world_states
                   WHERE object_id = ws1.object_id AND snapshot_time < ws1.snapshot_time
                 )
               WHERE ws1.object_type = 'smartassemblies'
                 AND ws1.snapshot_time = (
                   SELECT MAX(snapshot_time) FROM world_states
                   WHERE object_id = ws1.object_id
                 )
               LIMIT 500"""
        ).fetchall()

        anomalies = []
        for row in rows:
            try:
                new_data = json.loads(row["new_state"])
                old_data = json.loads(row["old_state"])
            except json.JSONDecodeError:
                continue

            # Check fuel amounts on network nodes
            new_fuel = self._extract_fuel_amount(new_data)
            old_fuel = self._extract_fuel_amount(old_data)

            if old_fuel is None or new_fuel is None:
                continue
            if new_fuel >= old_fuel:
                continue  # fuel increased or unchanged — OK

            delta = old_fuel - new_fuel
            # Check if there are chain events explaining the decrease
            events = self._events_for_object(row["object_id"], since=row["old_time"])
            if events:
                continue  # events exist that may explain it

            system_id = self._extract_system(new_data)
            anomalies.append(
                Anomaly(
                    anomaly_type="SUPPLY_DISCREPANCY",
                    rule_id="E1",
                    detector=self.name,
                    object_id=row["object_id"],
                    system_id=system_id,
                    evidence={
                        "old_fuel": old_fuel,
                        "new_fuel": new_fuel,
                        "delta": delta,
                        "old_snapshot_time": row["old_time"],
                        "new_snapshot_time": row["new_time"],
                        "chain_events_in_window": 0,
                        "description": (
                            f"Phantom ledger — {delta} units of fuel vanished "
                            f"between sweeps with no chain trail"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"snapshot:{row['object_id']}:{row['old_time']}",
                            timestamp=row["old_time"],
                            derivation=f"E1: old snapshot fuel={old_fuel}",
                        ),
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"snapshot:{row['object_id']}:{row['new_time']}",
                            timestamp=row["new_time"],
                            derivation=(
                                f"E1: fuel={new_fuel},"
                                f" delta={delta}, no chain events"
                            ),
                        ),
                    ],
                )
            )
        return anomalies

    def _check_e1_item_supply(self) -> list[Anomaly]:
        """E1b: Item inventory doesn't reconcile with ledger events."""
        try:
            rows = self.conn.execute(
                """SELECT assembly_id, item_type_id,
                          SUM(CASE WHEN event_type IN ('minted', 'deposited')
                              THEN quantity ELSE 0 END) as total_in,
                          SUM(CASE WHEN event_type IN ('burned', 'withdrawn')
                              THEN quantity ELSE 0 END) as total_out
                   FROM item_ledger
                   GROUP BY assembly_id, item_type_id
                   HAVING total_in > 0 OR total_out > 0
                   LIMIT 500"""
            ).fetchall()
        except sqlite3.OperationalError:
            # Table may not exist in older databases
            return []

        anomalies = []
        for row in rows:
            expected_balance = row["total_in"] - row["total_out"]
            obj = self._get_object(row["assembly_id"])
            if not obj:
                continue

            try:
                state = json.loads(obj["current_state"] or "{}")
            except json.JSONDecodeError:
                continue

            inventory = state.get("inventory", {})
            if not isinstance(inventory, dict):
                continue

            actual = inventory.get(row["item_type_id"], 0)
            if actual != expected_balance:
                anomalies.append(
                    Anomaly(
                        anomaly_type="SUPPLY_DISCREPANCY",
                        rule_id="E1",
                        detector=self.name,
                        object_id=row["assembly_id"],
                        system_id=obj.get("system_id", ""),
                        evidence={
                            "item_type_id": row["item_type_id"],
                            "expected_balance": expected_balance,
                            "actual_balance": actual,
                            "total_minted_deposited": row["total_in"],
                            "total_burned_withdrawn": row["total_out"],
                            "description": (
                                f"Phantom ledger — item {row['item_type_id'][:16]}... "
                                f"doesn't add up: ledger says {expected_balance}, "
                                f"cargo hold shows {actual}"
                            ),
                        },
                        provenance=[
                            ProvenanceEntry(
                                source_type="detection_rule",
                                source_id=f"ledger:{row['assembly_id']}:{row['item_type_id']}",
                                timestamp=0,
                                derivation=(
                                    f"E1: ledger={expected_balance}"
                                    f", cargo={actual}"
                                ),
                            )
                        ],
                    )
                )
        return anomalies

    # Staleness threshold: 7 days. Assemblies can sit idle for days/weeks
    # in EVE Frontier without chain events. A 2h window produced mass false
    # positives from every idle assembly. 7 days balances signal vs noise —
    # if an assembly had chain activity within the last week but none since,
    # AND was previously online, it's worth investigating.
    E2_STALENESS_SECONDS = 7 * 86400  # 7 days

    def _check_e2_unexplained_destruction(self) -> list[Anomaly]:
        """E2: Object disappeared from API between snapshots without kill/destroy event.

        If an object was present in snapshot T1 but absent in T2, and no
        destruction event exists on chain, the object vanished without explanation.
        Only flags objects that were previously ONLINE (actively used) and have
        been silent for >7 days — idle assemblies are normal in EVE Frontier.
        """
        # Objects last seen >7 days ago that aren't destroyed
        rows = self.conn.execute(
            """SELECT object_id, object_type, current_state, system_id, last_seen
               FROM objects
               WHERE destroyed_at IS NULL
                 AND last_seen > 0
                 AND last_seen < (strftime('%s', 'now') - ?)
                 AND object_type = 'smartassemblies'
               LIMIT 200""",
            (self.E2_STALENESS_SECONDS,),
        ).fetchall()

        anomalies = []
        for row in rows:
            obj_id = row["object_id"]
            state = {}
            with contextlib.suppress(json.JSONDecodeError):
                state = json.loads(row["current_state"] or "{}")

            # Only flag objects that were actively ONLINE — idle/offline/unanchored
            # assemblies going quiet is expected behavior in EVE Frontier
            obj_state = state.get("state", "")
            if obj_state != "ONLINE":
                continue
            owner = state.get("owner", {})
            if isinstance(owner, dict) and owner.get("address") == "0x" + "0" * 40:
                continue

            # Check for destruction events
            events = self._events_for_object(obj_id, since=row["last_seen"])
            has_destroy = any("destroy" in (e.get("event_type", "") or "").lower() for e in events)
            if has_destroy:
                continue

            anomalies.append(
                Anomaly(
                    anomaly_type="UNEXPLAINED_DESTRUCTION",
                    rule_id="E2",
                    detector=self.name,
                    object_id=obj_id,
                    system_id=row["system_id"] or "",
                    evidence={
                        "last_seen": row["last_seen"],
                        "last_state": state.get("state", "unknown"),
                        "object_type": state.get("type", row["object_type"]),
                        "chain_events_since": len(events),
                        "description": (
                            f"Vanishing act — last seen at {row['last_seen']}, "
                            f"gone from all subsequent sweeps. No wreckage, "
                            f"no destruction event. Just gone"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="world_state",
                            source_id=f"object:{obj_id}",
                            timestamp=row["last_seen"],
                            derivation=(
                                f"E2: last seen {row['last_seen']}"
                                ", no destruction event"
                            ),
                        )
                    ],
                )
            )
        return anomalies

    # Inventory event types are expected to batch (multiple per tx per object)
    _BATCH_SAFE_SUFFIXES = frozenset(
        {
            "ItemMintedEvent",
            "ItemBurnedEvent",
            "ItemDepositedEvent",
            "ItemWithdrawnEvent",
            "ItemDestroyedEvent",
            "FuelEvent",
        }
    )

    def _check_e3_duplicate_mint(self) -> list[Anomaly]:
        """E3: Same object receives duplicate events of the same type in one tx.

        On Sui, a single PTB can legitimately emit multiple events of the
        same type for batch inventory/fuel operations. We exclude inventory
        and fuel event types entirely (batch operations are normal), and
        only flag other event types (status, ownership, assembly creation,
        killmails) when the SAME object_id appears 3+ times in a single tx.
        """
        rows = self.conn.execute(
            """SELECT transaction_hash, event_type, object_id,
                      COUNT(*) as cnt,
                      GROUP_CONCAT(event_id) as event_ids
               FROM chain_events
               WHERE event_type != '' AND object_id != ''
               GROUP BY transaction_hash, event_type, object_id
               HAVING cnt > 2
               LIMIT 50"""
        ).fetchall()

        anomalies = []
        for row in rows:
            # Skip batch-safe event types (inventory/fuel ops are expected duplicates)
            etype = row["event_type"]
            event_suffix = etype.rsplit("::", 1)[-1] if "::" in etype else ""
            if event_suffix in self._BATCH_SAFE_SUFFIXES:
                continue

            # Resolve system_id from the target object or chain event
            system_id = self._resolve_system_id(row["object_id"], row["transaction_hash"])
            anomalies.append(
                Anomaly(
                    anomaly_type="DUPLICATE_MINT",
                    rule_id="E3",
                    detector=self.name,
                    object_id=row["transaction_hash"],
                    system_id=system_id,
                    evidence={
                        "transaction_hash": row["transaction_hash"],
                        "event_type": row["event_type"],
                        "target_object": row["object_id"],
                        "duplicate_count": row["cnt"],
                        "event_ids": row["event_ids"],
                        "description": (
                            f"Double stamp — {row['object_id'][:16]}... got "
                            f"{row['cnt']}x {event_suffix} in a single tx "
                            f"({row['transaction_hash'][:18]}...)"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="chain_event",
                            source_id=row["transaction_hash"],
                            timestamp=0,
                            derivation=(
                                f"E3: {row['cnt']}x"
                                f" {row['event_type']}"
                                f" for {row['object_id'][:16]}"
                            ),
                        )
                    ],
                )
            )
        return anomalies

    def _resolve_system_id(self, object_id: str, tx_hash: str) -> str:
        """Resolve system_id from the objects table or chain_events."""
        # Try objects table first
        row = self.conn.execute(
            "SELECT system_id FROM objects WHERE object_id = ? AND system_id != ''",
            (object_id,),
        ).fetchone()
        if row:
            return row["system_id"]
        # Fall back to chain_events for this tx
        row = self.conn.execute(
            "SELECT system_id FROM chain_events "
            "WHERE transaction_hash = ? AND system_id != '' LIMIT 1",
            (tx_hash,),
        ).fetchone()
        if row:
            return row["system_id"]
        return ""

    def _check_e4_negative_balance(self) -> list[Anomaly]:
        """E4: Any fuel amount is negative.

        Fuel amounts should never go below zero. A negative value indicates
        an accounting error in the contract or API.
        """
        rows = self.conn.execute(
            """SELECT object_id, current_state, system_id
               FROM objects
               WHERE object_type = 'smartassemblies'
               LIMIT 500"""
        ).fetchall()

        anomalies = []
        for row in rows:
            try:
                state = json.loads(row["current_state"] or "{}")
            except json.JSONDecodeError:
                continue

            fuel_amount = self._extract_fuel_amount(state)
            if fuel_amount is not None and fuel_amount < 0:
                anomalies.append(
                    Anomaly(
                        anomaly_type="NEGATIVE_BALANCE",
                        rule_id="E4",
                        detector=self.name,
                        object_id=row["object_id"],
                        system_id=row["system_id"] or "",
                        evidence={
                            "fuel_amount": fuel_amount,
                            "assembly_type": state.get("type", "unknown"),
                            "description": (
                                f"Negative mass — fuel balance hit {fuel_amount}. "
                                f"Conservation laws don't bend out here"
                            ),
                        },
                        provenance=[
                            ProvenanceEntry(
                                source_type="world_state",
                                source_id=f"object:{row['object_id']}",
                                timestamp=0,
                                derivation=(
                                    f"E4: fuel={fuel_amount}"
                                    ", negative balance"
                                ),
                            )
                        ],
                    )
                )

            # Check item inventory for negative balances
            inventory = state.get("inventory", {})
            if isinstance(inventory, dict):
                for item_type, balance in inventory.items():
                    if isinstance(balance, (int, float)) and balance < 0:
                        anomalies.append(
                            Anomaly(
                                anomaly_type="NEGATIVE_BALANCE",
                                rule_id="E4",
                                detector=self.name,
                                object_id=row["object_id"],
                                system_id=row["system_id"] or "",
                                evidence={
                                    "item_type_id": item_type,
                                    "balance": balance,
                                    "description": (
                                        f"Negative mass — item {item_type[:16]}... "
                                        f"balance dropped to {balance}. "
                                        f"Impossible arithmetic"
                                    ),
                                },
                                provenance=[
                                    ProvenanceEntry(
                                        source_type="world_state",
                                        source_id=f"object:{row['object_id']}",
                                        timestamp=0,
                                        derivation=(
                                            f"E4: item {item_type[:16]}"
                                            f" balance={balance}, negative"
                                        ),
                                    )
                                ],
                            )
                        )
        return anomalies

    @staticmethod
    def _extract_fuel_amount(state: dict) -> int | None:
        """Extract fuel amount from assembly state data."""
        # networkNode.fuel.amount for network nodes
        nn = state.get("networkNode", {})
        if isinstance(nn, dict):
            fuel = nn.get("fuel", {})
            if isinstance(fuel, dict) and "amount" in fuel:
                try:
                    return int(fuel["amount"])
                except (ValueError, TypeError):
                    return None
        return None

    @staticmethod
    def _extract_system(state: dict) -> str:
        """Extract system ID from state data."""
        solar = state.get("solarSystem", {})
        if isinstance(solar, dict):
            return str(solar.get("id", ""))
        return ""

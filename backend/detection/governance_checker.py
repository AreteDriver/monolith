"""Governance checker — detects organizational patterns from on-chain signals.

NOW rules (detectable with existing events):
  GV1 — Coordinated Delegation: Multiple OwnerCaps transferred to same address
         within 24h → org formation, hostile consolidation, or DAO bootstrap.
  GV2 — Treasury Formation: Diverse wallets depositing items to single assembly
         in coordinated window → collective treasury pattern.
  GV3 — Gate Network Consolidation: Multiple gates linked/relinked by same owner
         in short window → infrastructure power play or network takeover.

FUTURE rules (pending Ergod DAO contract deployment):
  GV4 — DAO Genesis Burst: Multiple DAO shared objects created in rapid succession
  GV5 — Proposal Storm: Abnormal proposal submission rate (governance spam/attack)
  GV6 — Vote Manipulation: Single wallet >66% of votes on high-stakes proposal
  GV7 — Treasury Drain: Large withdrawal from DAO treasury without matching proposal
  GV8 — SubDAO Proliferation: Rapid subDAO creation (namespace squatting)
  GV9 — Ticker Squatting: Bulk ticker registrations by single wallet
  GV10 — Federation Power Shift: Parent DAO revenue routing changed significantly
  GV11 — Hanging Trade: Trade contract left with missing items after SSU owner
         removed inventory without updating trade state (orphaned escrow)
"""

import contextlib
import json
import logging
import time
from collections import Counter, defaultdict

from backend.detection.base import Anomaly, BaseChecker, ProvenanceEntry

logger = logging.getLogger(__name__)

# Lookback windows
LOOKBACK_24H = 24 * 3600
LOOKBACK_6H = 6 * 3600

# Thresholds
MIN_COORDINATED_TRANSFERS = 3  # OwnerCaps to same address
MIN_DIVERSE_DEPOSITORS = 4  # unique wallets → same assembly
MIN_GATE_CONSOLIDATION = 3  # gates linked/relinked by same owner


class GovernanceChecker(BaseChecker):
    """Detects organizational and governance patterns from chain signals."""

    name = "governance_checker"

    def check(self) -> list[Anomaly]:
        """Run all governance rules."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_gv1_coordinated_delegation())
        anomalies.extend(self._check_gv2_treasury_formation())
        anomalies.extend(self._check_gv3_gate_consolidation())
        return anomalies

    def _check_gv1_coordinated_delegation(self) -> list[Anomaly]:
        """GV1: Detect multiple OwnerCaps transferred to the same address.

        When 3+ assemblies transfer OwnerCap to the same recipient within 24h,
        this signals org formation (DAO bootstrap), hostile consolidation, or
        corporate restructuring. Cross-reference with tribe_cache to distinguish
        friendly reorg from hostile takeover.
        """
        since = int(time.time()) - LOOKBACK_24H
        anomalies: list[Anomaly] = []

        rows = self.conn.execute(
            """SELECT * FROM chain_events
               WHERE timestamp >= ?
               AND (
                   event_type IN ('TransferObject', 'OwnerCapTransferred', 'TransferEvent')
                   OR raw_json LIKE '%OwnerCap%'
                   OR raw_json LIKE '%ownerCap%'
               )
               ORDER BY timestamp ASC""",
            (since,),
        ).fetchall()

        # Group by recipient address
        recipient_transfers: defaultdict[str, list[dict]] = defaultdict(list)

        for row in rows:
            event = dict(row)
            raw = event.get("raw_json", "{}")
            parsed = {}
            if isinstance(raw, str):
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(raw)
            elif isinstance(raw, dict):
                parsed = raw

            parsed_json = parsed.get("parsedJson", parsed)
            to_addr = self._extract_address(parsed_json, "recipient", "to", "newOwner")
            if not to_addr:
                continue

            recipient_transfers[to_addr].append(event)

        for recipient, transfers in recipient_transfers.items():
            if len(transfers) < MIN_COORDINATED_TRANSFERS:
                continue

            object_ids = [t.get("object_id", "unknown") for t in transfers]
            first_ts = min(t.get("timestamp", 0) for t in transfers)
            last_ts = max(t.get("timestamp", 0) for t in transfers)
            window_minutes = (last_ts - first_ts) / 60

            anomalies.append(
                Anomaly(
                    anomaly_type="COORDINATED_DELEGATION",
                    rule_id="GV1",
                    detector=self.name,
                    object_id=recipient,
                    evidence={
                        "recipient": recipient,
                        "transfer_count": len(transfers),
                        "object_ids": object_ids[:10],
                        "window_minutes": round(window_minutes, 1),
                        "first_transfer": first_ts,
                        "last_transfer": last_ts,
                        "description": (
                            f"Power consolidation — {len(transfers)} OwnerCaps "
                            f"transferred to {recipient[:16]}... within "
                            f"{window_minutes:.0f}min. Org formation or hostile "
                            f"takeover in progress"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="chain_event",
                            source_id=t.get("transaction_hash", ""),
                            timestamp=t.get("timestamp", 0),
                            derivation=(f"GV1: OwnerCap transfer #{i + 1} to {recipient[:16]}"),
                        )
                        for i, t in enumerate(transfers[:5])
                    ],
                )
            )

        return anomalies

    def _check_gv2_treasury_formation(self) -> list[Anomaly]:
        """GV2: Detect diverse wallets depositing to a single assembly.

        When 4+ unique wallets deposit items to the same assembly within 6h,
        this signals collective treasury formation — a DAO-like pattern where
        multiple players pool resources. Relevant for Ergod's DAO white paper
        (subDAO treasury with 20% upward routing to parent).
        """
        since = int(time.time()) - LOOKBACK_6H
        anomalies: list[Anomaly] = []

        # Look for item deposits grouped by assembly
        rows = self.conn.execute(
            """SELECT * FROM chain_events
               WHERE timestamp >= ?
               AND event_type LIKE '%Deposit%'
               ORDER BY timestamp ASC""",
            (since,),
        ).fetchall()

        # Group by target assembly
        assembly_depositors: defaultdict[str, set[str]] = defaultdict(set)
        assembly_events: defaultdict[str, list[dict]] = defaultdict(list)

        for row in rows:
            event = dict(row)
            raw = event.get("raw_json", "{}")
            parsed = {}
            if isinstance(raw, str):
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(raw)
            elif isinstance(raw, dict):
                parsed = raw

            assembly_id = event.get("object_id", "")
            parsed_json = parsed.get("parsedJson", parsed)
            depositor = self._extract_address(parsed_json, "sender", "owner", "from", "depositor")
            if not assembly_id or not depositor:
                continue

            assembly_depositors[assembly_id].add(depositor)
            assembly_events[assembly_id].append(event)

        for assembly_id, depositors in assembly_depositors.items():
            if len(depositors) < MIN_DIVERSE_DEPOSITORS:
                continue

            events = assembly_events[assembly_id]
            first_ts = min(e.get("timestamp", 0) for e in events)
            last_ts = max(e.get("timestamp", 0) for e in events)

            anomalies.append(
                Anomaly(
                    anomaly_type="TREASURY_FORMATION",
                    rule_id="GV2",
                    detector=self.name,
                    object_id=assembly_id,
                    evidence={
                        "assembly_id": assembly_id,
                        "unique_depositors": len(depositors),
                        "depositor_addresses": sorted(depositors)[:10],
                        "total_deposits": len(events),
                        "first_deposit": first_ts,
                        "last_deposit": last_ts,
                        "description": (
                            f"Treasury formation — {len(depositors)} unique wallets "
                            f"depositing to {assembly_id[:16]}... "
                            f"({len(events)} deposits). Collective resource pooling "
                            f"or DAO treasury bootstrap"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="chain_event",
                            source_id=e.get("transaction_hash", ""),
                            timestamp=e.get("timestamp", 0),
                            derivation=f"GV2: deposit #{i + 1} to {assembly_id[:16]}",
                        )
                        for i, e in enumerate(events[:5])
                    ],
                )
            )

        return anomalies

    def _check_gv3_gate_consolidation(self) -> list[Anomaly]:
        """GV3: Detect gate network consolidation by single operator.

        When one address links/relinks 3+ gates within 6h, this signals
        infrastructure power play — someone building or taking over a gate
        network. In the context of Ergod's DAO framework, this could indicate
        a tribe asserting control over trade routes or a federation forming
        a shared highway.
        """
        since = int(time.time()) - LOOKBACK_6H
        anomalies: list[Anomaly] = []

        rows = self.conn.execute(
            """SELECT * FROM chain_events
               WHERE timestamp >= ?
               AND event_type IN ('GateLinkedEvent', 'GateUnlinkedEvent', 'GateCreatedEvent')
               ORDER BY timestamp ASC""",
            (since,),
        ).fetchall()

        # Group by operator (sender/owner)
        operator_actions: defaultdict[str, list[dict]] = defaultdict(list)

        for row in rows:
            event = dict(row)
            raw = event.get("raw_json", "{}")
            parsed = {}
            if isinstance(raw, str):
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(raw)
            elif isinstance(raw, dict):
                parsed = raw

            parsed_json = parsed.get("parsedJson", parsed)
            operator = self._extract_address(parsed_json, "sender", "owner", "creator")
            if not operator:
                # Fall back to object owner from objects table
                obj_id = event.get("object_id", "")
                if obj_id:
                    obj_row = self.conn.execute(
                        "SELECT owner FROM objects WHERE object_id = ?",
                        (obj_id,),
                    ).fetchone()
                    if obj_row:
                        operator = obj_row["owner"] if isinstance(obj_row, dict) else obj_row[0]

            if not operator:
                continue

            operator_actions[operator].append(event)

        for operator, actions in operator_actions.items():
            if len(actions) < MIN_GATE_CONSOLIDATION:
                continue

            gate_ids = list({a.get("object_id", "unknown") for a in actions})
            event_types = Counter(a.get("event_type", "") for a in actions)
            first_ts = min(a.get("timestamp", 0) for a in actions)
            last_ts = max(a.get("timestamp", 0) for a in actions)
            window_minutes = (last_ts - first_ts) / 60

            anomalies.append(
                Anomaly(
                    anomaly_type="GATE_NETWORK_CONSOLIDATION",
                    rule_id="GV3",
                    detector=self.name,
                    object_id=operator,
                    evidence={
                        "operator": operator,
                        "action_count": len(actions),
                        "unique_gates": len(gate_ids),
                        "gate_ids": gate_ids[:10],
                        "event_breakdown": dict(event_types),
                        "window_minutes": round(window_minutes, 1),
                        "description": (
                            f"Gate network consolidation — {operator[:16]}... "
                            f"modified {len(gate_ids)} gates ({len(actions)} actions) "
                            f"in {window_minutes:.0f}min. Infrastructure power play "
                            f"or highway formation"
                        ),
                    },
                    provenance=[
                        ProvenanceEntry(
                            source_type="chain_event",
                            source_id=a.get("transaction_hash", ""),
                            timestamp=a.get("timestamp", 0),
                            derivation=(
                                f"GV3: {a.get('event_type', '')} on "
                                f"{a.get('object_id', '')[:16]} by {operator[:16]}"
                            ),
                        )
                        for i, a in enumerate(actions[:5])
                    ],
                )
            )

        return anomalies

    @staticmethod
    def _extract_address(d: dict, *keys: str) -> str:
        """Extract an address from parsed event data, trying multiple keys."""
        for key in keys:
            val = d.get(key)
            if val and isinstance(val, str):
                return val
            if isinstance(val, dict):
                addr = val.get("address", val.get("id", ""))
                if addr:
                    return str(addr)
        return ""

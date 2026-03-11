"""Demo seed script — populates database with realistic sample anomalies.

Run this to populate a fresh Monolith instance with demo data
so judges can see the full detection → report → alert flow.

Usage:
    python demo_seed.py [--db monolith.db]
"""

import json
import sys
import time

from backend.db.database import init_db
from backend.reports.formatter import format_json, format_markdown
from backend.reports.llm_narrator import _template_narration
from backend.reports.report_builder import build_report, store_report

DEMO_OBJECTS = [
    {
        "object_id": "0x4f2a8c91d3e7b5f2a8c91d3e7b5f2a8c91d3e7b5",
        "object_type": "SmartStorageUnit",
        "current_state": json.dumps({"state": "online", "energyUsage": 100}),
        "current_owner": "0x1234567890abcdef1234567890abcdef12345678",
        "system_id": "30012602",
    },
    {
        "object_id": "0xa7b3c1d9e8f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0",
        "object_type": "SmartGate",
        "current_state": json.dumps({"state": "online", "energyUsage": 250}),
        "current_owner": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "system_id": "30004759",
    },
    {
        "object_id": "0xc5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3",
        "object_type": "NetworkNode",
        "current_state": json.dumps({"state": "offline"}),
        "current_owner": "0xabcdef0123456789abcdef0123456789abcdef01",
        "system_id": "30002187",
    },
]

DEMO_ANOMALIES = [
    {
        "anomaly_id": "MNL-20260311-0001",
        "anomaly_type": "PHANTOM_ITEM_CHANGE",
        "severity": "HIGH",
        "category": "STATE_INCONSISTENCY",
        "detector": "assembly_checker",
        "rule_id": "A4",
        "object_id": "0x4f2a8c91d3e7b5f2a8c91d3e7b5f2a8c91d3e7b5",
        "system_id": "30012602",
        "evidence_json": json.dumps(
            {
                "description": (
                    "Storage unit energyUsage changed from 50 to 100 "
                    "with no chain events in the observation window"
                ),
                "changes": {"energyUsage": {"old": 50, "new": 100}},
                "old_snapshot_time": int(time.time()) - 900,
                "new_snapshot_time": int(time.time()),
                "events_in_window": 0,
            }
        ),
    },
    {
        "anomaly_id": "MNL-20260311-0002",
        "anomaly_type": "RESURRECTION",
        "severity": "CRITICAL",
        "category": "DATA_INTEGRITY",
        "detector": "continuity_checker",
        "rule_id": "C2",
        "object_id": "0xa7b3c1d9e8f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0",
        "system_id": "30004759",
        "evidence_json": json.dumps(
            {
                "description": (
                    "Smart gate was marked destroyed at block 18234567 "
                    "but new event appeared at block 18235890"
                ),
                "destroyed_at_block": 18234567,
                "post_destruction_event": {
                    "block_number": 18235890,
                    "transaction_hash": "0x9f8e7d6c5b4a3928170605f4e3d2c1b0a9f8e7d6",
                    "event_type": "Store_SetRecord",
                },
            }
        ),
    },
    {
        "anomaly_id": "MNL-20260311-0003",
        "anomaly_type": "UNEXPLAINED_OWNERSHIP_CHANGE",
        "severity": "CRITICAL",
        "category": "DATA_INTEGRITY",
        "detector": "assembly_checker",
        "rule_id": "A5",
        "object_id": "0xc5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3",
        "system_id": "30002187",
        "evidence_json": json.dumps(
            {
                "description": (
                    "Network node ownership changed from "
                    "0xabcdef01...ef01 to 0x99887766...7766 "
                    "without a transfer event on chain"
                ),
                "old_owner": "0xabcdef0123456789abcdef0123456789abcdef01",
                "new_owner": "0x9988776655443322110099887766554433221100",
                "old_snapshot_time": int(time.time()) - 600,
                "new_snapshot_time": int(time.time()),
            }
        ),
    },
    {
        "anomaly_id": "MNL-20260311-0004",
        "anomaly_type": "SUPPLY_DISCREPANCY",
        "severity": "HIGH",
        "category": "ECONOMIC",
        "detector": "economic_checker",
        "rule_id": "E1",
        "object_id": "0x4f2a8c91d3e7b5f2a8c91d3e7b5f2a8c91d3e7b5",
        "system_id": "30012602",
        "evidence_json": json.dumps(
            {
                "description": (
                    "Fuel decreased by 150 units without depositFuel "
                    "or withdrawFuel events in observation window"
                ),
                "fuel_old": 500,
                "fuel_new": 350,
                "delta": -150,
                "events_in_window": 0,
            }
        ),
    },
    {
        "anomaly_id": "MNL-20260311-0005",
        "anomaly_type": "STATE_GAP",
        "severity": "HIGH",
        "category": "CONTINUITY",
        "detector": "continuity_checker",
        "rule_id": "C3",
        "object_id": "0xa7b3c1d9e8f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0",
        "system_id": "30004759",
        "evidence_json": json.dumps(
            {
                "description": (
                    "Smart gate jumped from 'online' to 'unanchored' "
                    "without going through 'offline' first"
                ),
                "from_state": "online",
                "to_state": "unanchored",
                "expected_intermediate": "offline",
                "transaction_hash": "0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
            }
        ),
    },
    {
        "anomaly_id": "MNL-20260311-0006",
        "anomaly_type": "ORPHAN_OBJECT",
        "severity": "MEDIUM",
        "category": "CONTINUITY",
        "detector": "continuity_checker",
        "rule_id": "C1",
        "object_id": "0xff00ee11dd22cc33bb44aa5599886677ff00ee11",
        "system_id": "",
        "evidence_json": json.dumps(
            {
                "description": (
                    "Chain event references object 0xff00ee11...ee11 which has no creation record"
                ),
                "event_type": "Store_SetRecord",
                "block_number": 18236100,
                "transaction_hash": "0x0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b",
            }
        ),
    },
]


def seed(db_path: str = "monolith.db") -> None:
    """Seed the database with demo data."""
    conn = init_db(db_path)
    now = int(time.time())

    # Insert demo objects
    for obj in DEMO_OBJECTS:
        conn.execute(
            "INSERT OR IGNORE INTO objects "
            "(object_id, object_type, current_state, current_owner, "
            "system_id, last_seen, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                obj["object_id"],
                obj["object_type"],
                obj["current_state"],
                obj["current_owner"],
                obj["system_id"],
                now,
                now - 86400,
            ),
        )

    # Insert demo anomalies
    for anom in DEMO_ANOMALIES:
        conn.execute(
            "INSERT OR IGNORE INTO anomalies "
            "(anomaly_id, anomaly_type, severity, category, detector, "
            "rule_id, object_id, system_id, detected_at, evidence_json, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNVERIFIED')",
            (
                anom["anomaly_id"],
                anom["anomaly_type"],
                anom["severity"],
                anom["category"],
                anom["detector"],
                anom["rule_id"],
                anom["object_id"],
                anom["system_id"],
                now - 300,
                anom["evidence_json"],
            ),
        )

    conn.commit()

    # Generate reports for first 3 anomalies
    for anom in DEMO_ANOMALIES[:3]:
        row = conn.execute(
            "SELECT * FROM anomalies WHERE anomaly_id = ?",
            (anom["anomaly_id"],),
        ).fetchone()
        if not row:
            continue

        anomaly_dict = dict(row)
        report = build_report(anomaly_dict, conn)

        # Add template narration
        evidence = json.loads(anom["evidence_json"])
        report["plain_english"] = _template_narration(
            anom["anomaly_type"],
            evidence,
        )
        report["format_markdown"] = format_markdown(report)
        report["format_json"] = json.dumps(format_json(report))

        store_report(report, conn)
        print(f"  Report {report['report_id']} for {anom['anomaly_type']}")

    conn.close()

    print(f"\nSeeded {len(DEMO_OBJECTS)} objects, {len(DEMO_ANOMALIES)} anomalies, 3 reports")
    print(f"Database: {db_path}")
    print("\nStart Monolith:")
    print("  python -m uvicorn backend.main:app --reload")
    print("  Open http://localhost:8000")


if __name__ == "__main__":
    db = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else "monolith.db"
    seed(db)

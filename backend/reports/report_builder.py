"""Report builder — transforms anomaly records into structured bug reports.

Takes an anomaly dict (from DB) and builds a complete report with all sections:
summary, affected entities, evidence, chain references, reproduction context,
and recommended investigation steps.
"""

import json
import sqlite3
import time
from datetime import UTC, datetime

from backend.detection.anomaly_scorer import RULE_CLASSIFICATION

# Maps anomaly_type to investigation recommendations
INVESTIGATION_STEPS: dict[str, list[str]] = {
    "ORPHAN_OBJECT": [
        "Query chain for all events referencing this object ID",
        "Check if object was created before monitoring started (backfill gap)",
        "Verify MUD indexer is processing all Store_SetRecord events",
    ],
    "RESURRECTION": [
        "Verify destruction event was genuine (not a state flag reset)",
        "Query chain for all post-destruction transactions",
        "Check if object ID was recycled (new object, same ID)",
        "This is a critical data integrity issue if confirmed",
    ],
    "STATE_GAP": [
        "Query chain for events between the two snapshot timestamps",
        "Check if intermediate state transitions were processed but not recorded",
        "Verify the valid transition map matches current contract logic",
    ],
    "STUCK_OBJECT": [
        "Check if a pending transaction is stuck in the mempool",
        "Verify the assembly contract's state machine allows resolution",
        "Check if the player's wallet has sufficient gas",
    ],
    "SUPPLY_DISCREPANCY": [
        "Compare fuel burn rate against elapsed time",
        "Check if fuel was consumed by a linked assembly",
        "Query chain for depositFuel/withdrawFuel events in the window",
    ],
    "UNEXPLAINED_DESTRUCTION": [
        "Check if object reappears in next API poll (transient API issue)",
        "Query chain for destroyDeployable or unanchor events",
        "Verify API pagination didn't skip this object",
    ],
    "DUPLICATE_MINT": [
        "Examine transaction receipts for both events",
        "Check if this is a known multi-event transaction pattern",
        "Verify event deduplication in the ingestion layer",
    ],
    "NEGATIVE_BALANCE": [
        "This should be impossible — verify contract arithmetic",
        "Check for integer overflow/underflow in fuel calculations",
        "Query historical fuel events to trace the balance to negative",
    ],
    "CONTRACT_STATE_MISMATCH": [
        "Query chain state directly (not via API) for this object",
        "Check API cache/indexer lag — wait 2 minutes and re-check",
        "If persistent: contract state and API are diverged",
    ],
    "PHANTOM_ITEM_CHANGE": [
        "Query chain for ALL events referencing this object in the window",
        "Check if MUD indexer missed events (indexer gap vs chain gap)",
        "Verify the changed properties can only be modified via chain tx",
    ],
    "UNEXPLAINED_OWNERSHIP_CHANGE": [
        "Query chain for transfer events for this object",
        "Check if ownership was changed via admin/system function",
        "This is critical — ownership should never change without on-chain record",
    ],
    "DUPLICATE_TRANSACTION": [
        "Examine if this is a complex transaction with many sub-operations",
        "Check for RPC response deduplication issues",
        "Verify ingestion layer isn't double-processing blocks",
    ],
    "BLOCK_PROCESSING_GAP": [
        "Check if the RPC node was unavailable during the gap window",
        "Query the missing block range for any world contract events",
        "This may indicate indexer downtime, not a chain issue",
    ],
}


def generate_report_id() -> str:
    """Generate a report ID: MNL-{YYYYMMDD}-{seq}."""
    date_str = datetime.now(tz=UTC).strftime("%Y%m%d")
    seq = int(time.time()) % 10000
    return f"MNL-{date_str}-{seq:04d}"


def build_report(anomaly_row: dict, conn: sqlite3.Connection | None = None) -> dict:
    """Build a complete bug report from an anomaly database row.

    Returns a report dict ready for storage in bug_reports table.
    """
    report_id = generate_report_id()
    now = int(time.time())

    # Parse evidence
    evidence = {}
    if anomaly_row.get("evidence_json"):
        try:
            evidence = json.loads(anomaly_row["evidence_json"])
        except json.JSONDecodeError:
            evidence = {"raw": anomaly_row["evidence_json"]}

    # Build summary from evidence description
    summary = evidence.get("description", f"{anomaly_row['anomaly_type']} detected")

    # Build chain references
    chain_refs = _extract_chain_references(evidence, anomaly_row)

    # Build reproduction context
    reproduction = _build_reproduction_context(anomaly_row, evidence)

    # Get investigation steps
    investigation = INVESTIGATION_STEPS.get(
        anomaly_row["anomaly_type"],
        ["Review the evidence block and chain references for manual investigation"],
    )

    # Build affected entities section
    affected = _build_affected_entities(anomaly_row, evidence, conn)

    report = {
        "report_id": report_id,
        "anomaly_id": anomaly_row["anomaly_id"],
        "title": _generate_title(anomaly_row),
        "severity": anomaly_row["severity"],
        "category": anomaly_row["category"],
        "summary": summary,
        "affected_entities": affected,
        "evidence_json": json.dumps(evidence),
        "plain_english": "",  # Filled by LLM narrator
        "chain_references": json.dumps(chain_refs),
        "reproduction_context": json.dumps(reproduction),
        "recommended_investigation": json.dumps(investigation),
        "generated_at": now,
    }
    return report


def _generate_title(anomaly: dict) -> str:
    """Generate a concise report title."""
    atype = anomaly["anomaly_type"].replace("_", " ").title()
    obj_id = anomaly.get("object_id", "")
    if obj_id and len(obj_id) > 16:
        obj_id = obj_id[:8] + "..." + obj_id[-4:]
    system = anomaly.get("system_id", "")
    if system and system != "0":
        return f"{atype} — Object {obj_id} in System {system}"
    return f"{atype} — Object {obj_id}"


def _extract_chain_references(evidence: dict, anomaly: dict) -> list[dict]:
    """Extract chain transaction references from evidence."""
    refs = []
    tx_hash = evidence.get("transaction_hash", "")
    if tx_hash:
        refs.append(
            {
                "type": "transaction",
                "hash": tx_hash,
                "explorer_url": f"https://sepolia-optimism.etherscan.io/tx/{tx_hash}",
            }
        )

    block = evidence.get("block_number")
    if block:
        refs.append(
            {
                "type": "block",
                "number": block,
                "explorer_url": f"https://sepolia-optimism.etherscan.io/block/{block}",
            }
        )

    # Check for post-destruction event refs
    post_event = evidence.get("post_destruction_event", {})
    if post_event.get("transaction_hash"):
        refs.append(
            {
                "type": "transaction",
                "hash": post_event["transaction_hash"],
                "label": "post_destruction",
                "explorer_url": (
                    f"https://sepolia-optimism.etherscan.io/tx/{post_event['transaction_hash']}"
                ),
            }
        )

    return refs


def _build_reproduction_context(anomaly: dict, evidence: dict) -> dict:
    """Build reproduction context for the report."""
    rule_id = anomaly.get("rule_id", "")
    severity, category = RULE_CLASSIFICATION.get(rule_id, ("LOW", "BEHAVIORAL"))

    context = {
        "detector": anomaly.get("detector", ""),
        "rule_id": rule_id,
        "rule_severity": severity,
        "rule_category": category,
        "detection_time": anomaly.get("detected_at", 0),
    }

    # Add snapshot window if available
    old_time = evidence.get("old_snapshot_time") or evidence.get("snapshot_old_time")
    new_time = evidence.get("new_snapshot_time") or evidence.get("snapshot_new_time")
    if old_time and new_time:
        context["observation_window_seconds"] = new_time - old_time
        context["snapshot_start"] = old_time
        context["snapshot_end"] = new_time

    return context


def _build_affected_entities(
    anomaly: dict, evidence: dict, conn: sqlite3.Connection | None
) -> dict:
    """Build the affected entities section."""
    obj_id = anomaly.get("object_id", "")
    entities: dict = {
        "object_id": obj_id,
        "system_id": anomaly.get("system_id", ""),
    }

    # Try to enrich from objects table
    if conn and obj_id:
        row = conn.execute(
            "SELECT object_type, current_owner FROM objects WHERE object_id = ?",
            (obj_id,),
        ).fetchone()
        if row:
            entities["object_type"] = row["object_type"]
            entities["owner"] = row["current_owner"]

    return entities


def store_report(report: dict, conn: sqlite3.Connection) -> bool:
    """Store a built report in the bug_reports table."""
    try:
        conn.execute(
            """INSERT INTO bug_reports
               (report_id, anomaly_id, title, severity, category, summary,
                evidence_json, plain_english, chain_references,
                reproduction_context, recommended_investigation,
                generated_at, format_markdown, format_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report["report_id"],
                report["anomaly_id"],
                report["title"],
                report["severity"],
                report["category"],
                report["summary"],
                report["evidence_json"],
                report.get("plain_english", ""),
                report["chain_references"],
                report["reproduction_context"],
                report["recommended_investigation"],
                report["generated_at"],
                report.get("format_markdown", ""),
                report.get("format_json", ""),
            ),
        )
        # Update anomaly with report_id
        conn.execute(
            "UPDATE anomalies SET report_id = ? WHERE anomaly_id = ?",
            (report["report_id"], report["anomaly_id"]),
        )
        conn.commit()
        return True
    except Exception:
        return False

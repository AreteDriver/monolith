"""Submit API — player bug submission tool."""

import json
import sqlite3
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.reports.formatter import format_json, format_markdown
from backend.reports.llm_narrator import narrate_anomaly
from backend.reports.report_builder import build_report, store_report

router = APIRouter(prefix="/api/submit", tags=["submit"])


class SubmitRequest(BaseModel):
    """Player bug submission payload."""

    object_id: str
    object_type: str = ""
    observed_at: int = 0
    description: str = ""
    character_name: str = ""


def _get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


@router.post("")
async def submit_observation(request: Request, body: SubmitRequest) -> dict:
    """Player submits a bug observation — Monolith pulls chain evidence."""
    conn = _get_db(request)
    settings = request.app.state.settings

    observed_at = body.observed_at or int(time.time())
    window_start = observed_at - 1800  # ±30 min
    window_end = observed_at + 1800

    # Fetch chain events in window
    events = conn.execute(
        "SELECT event_id, event_type, block_number, transaction_hash, "
        "timestamp FROM chain_events "
        "WHERE object_id = ? AND timestamp BETWEEN ? AND ? "
        "ORDER BY timestamp",
        (body.object_id, window_start, window_end),
    ).fetchall()

    # Fetch world state snapshots in window
    snapshots = conn.execute(
        "SELECT state_data, snapshot_time FROM world_states "
        "WHERE object_id = ? AND snapshot_time BETWEEN ? AND ? "
        "ORDER BY snapshot_time",
        (body.object_id, window_start, window_end),
    ).fetchall()

    # Check for existing anomalies on this object in window
    anomalies = conn.execute(
        "SELECT * FROM anomalies "
        "WHERE object_id = ? AND detected_at BETWEEN ? AND ? "
        "ORDER BY detected_at DESC",
        (body.object_id, window_start, window_end),
    ).fetchall()

    events_list = [dict(e) for e in events]
    snapshots_list = [dict(s) for s in snapshots]

    if anomalies:
        # Use first detected anomaly to generate report
        anomaly = dict(anomalies[0])
        report = build_report(anomaly, conn)

        # Add player context to report
        report["summary"] = (
            f"Player-reported: {body.description}\n\nAuto-detected: {report['summary']}"
        )

        narration = await narrate_anomaly(
            anomaly_type=anomaly["anomaly_type"],
            evidence=json.loads(anomaly.get("evidence_json", "{}")),
            rule_id=anomaly.get("rule_id", ""),
            severity=anomaly["severity"],
            api_key=settings.anthropic_api_key,
        )
        report["plain_english"] = narration
        report["format_markdown"] = format_markdown(report)
        report["format_json"] = json.dumps(format_json(report))

        stored = store_report(report, conn)

        return {
            "status": "anomaly_found",
            "report_id": report["report_id"] if stored else None,
            "anomaly_id": anomaly["anomaly_id"],
            "anomaly_type": anomaly["anomaly_type"],
            "severity": anomaly["severity"],
            "events_in_window": len(events_list),
            "snapshots_in_window": len(snapshots_list),
        }

    # No anomaly detected — return raw chain data
    return {
        "status": "no_anomaly_detected",
        "object_id": body.object_id,
        "message": (
            "Monolith did not detect a rule violation, but here is the raw "
            "chain state for your object during the reported window."
        ),
        "events_in_window": events_list,
        "snapshots_in_window": len(snapshots_list),
        "observation": {
            "description": body.description,
            "observed_at": observed_at,
            "character_name": body.character_name,
        },
    }


@router.get("/{object_id}/status")
def get_object_status(request: Request, object_id: str) -> dict:
    """Quick check — does this object have any anomalies?"""
    conn = _get_db(request)

    obj = conn.execute("SELECT * FROM objects WHERE object_id = ?", (object_id,)).fetchone()

    anomaly_count = conn.execute(
        "SELECT COUNT(*) FROM anomalies WHERE object_id = ?",
        (object_id,),
    ).fetchone()[0]

    return {
        "object_id": object_id,
        "found": obj is not None,
        "anomaly_count": anomaly_count,
        "object_type": obj["object_type"] if obj else None,
    }

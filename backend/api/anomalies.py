"""Anomalies API — list, filter, and view detected anomalies."""

import json
import sqlite3
from enum import Enum

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


class AnomalyStatus(str, Enum):
    """Valid anomaly statuses."""

    UNVERIFIED = "UNVERIFIED"
    CONFIRMED = "CONFIRMED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"


class StatusUpdateRequest(BaseModel):
    """Request body for updating anomaly status."""

    status: AnomalyStatus
    note: str = ""


def _get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


@router.get("")
def list_anomalies(
    request: Request,
    severity: str | None = None,
    anomaly_type: str | None = None,
    status: str | None = None,
    system_id: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List anomalies with optional filters."""
    conn = _get_db(request)
    query = "SELECT * FROM anomalies WHERE 1=1"
    params: list = []

    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if anomaly_type:
        query += " AND anomaly_type = ?"
        params.append(anomaly_type)
    if status:
        query += " AND status = ?"
        params.append(status)
    if system_id:
        query += " AND system_id = ?"
        params.append(system_id)

    query += " ORDER BY detected_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return {
        "data": [_row_to_dict(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


@router.get("/{anomaly_id}")
def get_anomaly(request: Request, anomaly_id: str) -> dict:
    """Get a single anomaly by ID."""
    conn = _get_db(request)
    row = conn.execute("SELECT * FROM anomalies WHERE anomaly_id = ?", (anomaly_id,)).fetchone()
    if not row:
        return {"error": "not_found"}
    return _row_to_dict(row)


@router.patch("/{anomaly_id}/status")
def update_anomaly_status(
    request: Request,
    anomaly_id: str,
    body: StatusUpdateRequest,
) -> dict:
    """Update an anomaly's status (e.g., CONFIRMED, FALSE_POSITIVE, RESOLVED)."""
    conn = _get_db(request)
    row = conn.execute(
        "SELECT anomaly_id FROM anomalies WHERE anomaly_id = ?",
        (anomaly_id,),
    ).fetchone()
    if not row:
        return {"error": "not_found"}

    conn.execute(
        "UPDATE anomalies SET status = ? WHERE anomaly_id = ?",
        (body.status.value, anomaly_id),
    )
    conn.commit()

    updated = conn.execute(
        "SELECT * FROM anomalies WHERE anomaly_id = ?",
        (anomaly_id,),
    ).fetchone()
    return _row_to_dict(updated)


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a Row to a dict, parsing JSON fields."""
    d = dict(row)
    if d.get("evidence_json"):
        try:
            d["evidence"] = json.loads(d["evidence_json"])
        except json.JSONDecodeError:
            d["evidence"] = {}
    return d

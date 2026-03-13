"""Anomalies API — list, filter, and view detected anomalies."""

import json
import sqlite3

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


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


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a Row to a dict, parsing JSON fields."""
    d = dict(row)
    if d.get("evidence_json"):
        try:
            d["evidence"] = json.loads(d["evidence_json"])
        except json.JSONDecodeError:
            d["evidence"] = {}
    return d

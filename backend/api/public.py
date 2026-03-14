"""Public API v1 — read-only versioned endpoints for external consumers."""

import json
import sqlite3
import time

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/v1", tags=["public"])

START_TIME = time.time()


def _get_db(request: Request) -> sqlite3.Connection:
    """Get database connection from request state."""
    return request.app.state.db


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a Row to a dict, parsing JSON fields."""
    d = dict(row)
    if d.get("evidence_json"):
        try:
            d["evidence"] = json.loads(d["evidence_json"])
        except json.JSONDecodeError:
            d["evidence"] = {}
    return d


@router.get("/anomalies")
def list_anomalies(
    request: Request,
    severity: str | None = None,
    anomaly_type: str | None = None,
    system_id: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List anomalies (read-only, no status updates).

    Args:
        request: FastAPI request with DB connection.
        severity: Filter by severity level.
        anomaly_type: Filter by anomaly type.
        system_id: Filter by system ID.
        limit: Max results to return.
        offset: Pagination offset.

    Returns:
        Paginated list of anomalies.
    """
    conn = _get_db(request)
    query = "SELECT * FROM anomalies WHERE 1=1"
    params: list = []

    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if anomaly_type:
        query += " AND anomaly_type = ?"
        params.append(anomaly_type)
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


@router.get("/anomalies/{anomaly_id}")
def get_anomaly(request: Request, anomaly_id: str) -> dict:
    """Get a single anomaly by ID (read-only).

    Args:
        request: FastAPI request with DB connection.
        anomaly_id: The anomaly ID to look up.

    Returns:
        Anomaly details or error.
    """
    conn = _get_db(request)
    row = conn.execute("SELECT * FROM anomalies WHERE anomaly_id = ?", (anomaly_id,)).fetchone()
    if not row:
        return {"error": "not_found"}
    return _row_to_dict(row)


@router.get("/health")
def health(request: Request) -> dict:
    """Simplified public health endpoint.

    Args:
        request: FastAPI request with DB connection.

    Returns:
        Status, version, uptime, and chain info.
    """
    settings = request.app.state.settings
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": int(time.time() - START_TIME),
        "chain": settings.chain,
    }


@router.get("/stats")
def stats(request: Request) -> dict:
    """Public anomaly statistics — counts by severity and type.

    Args:
        request: FastAPI request with DB connection.

    Returns:
        Anomaly counts grouped by severity and type.
    """
    conn = _get_db(request)
    now = int(time.time())
    cutoff_24h = now - 86400

    total_24h = conn.execute(
        "SELECT COUNT(*) FROM anomalies WHERE detected_at >= ?",
        (cutoff_24h,),
    ).fetchone()[0]

    by_severity = {}
    for row in conn.execute(
        "SELECT severity, COUNT(*) as cnt FROM anomalies WHERE detected_at >= ? GROUP BY severity",
        (cutoff_24h,),
    ).fetchall():
        by_severity[row["severity"]] = row["cnt"]

    by_type = {}
    for row in conn.execute(
        "SELECT anomaly_type, COUNT(*) as cnt FROM anomalies "
        "WHERE detected_at >= ? GROUP BY anomaly_type ORDER BY cnt DESC",
        (cutoff_24h,),
    ).fetchall():
        by_type[row["anomaly_type"]] = row["cnt"]

    return {
        "anomaly_rate_24h": total_24h,
        "by_severity": by_severity,
        "by_type": by_type,
    }

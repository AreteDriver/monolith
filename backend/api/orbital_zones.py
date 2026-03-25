"""Orbital Zones API — zone status, feral AI events, threat overview."""

import contextlib
import json
import sqlite3

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/orbital-zones", tags=["orbital_zones"])


def _get_db(request: Request) -> sqlite3.Connection:
    """Get database connection from request state."""
    return request.app.state.db


@router.get("")
def list_zones(
    request: Request,
    system_id: str | None = Query(None, description="Filter by system ID"),
    threat_level: str | None = Query(None, description="Filter by threat level"),
    limit: int = Query(100, le=500),
) -> dict:
    """List orbital zones with optional filters."""
    conn = _get_db(request)
    clauses = []
    params: list = []

    if system_id:
        clauses.append("system_id = ?")
        params.append(system_id)
    if threat_level:
        clauses.append("threat_level = ?")
        params.append(threat_level.upper())

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    try:
        rows = conn.execute(
            f"SELECT * FROM orbital_zones {where} "  # noqa: S608
            f"ORDER BY last_polled DESC LIMIT ?",
            params,
        ).fetchall()
        return {"data": [dict(r) for r in rows], "count": len(rows)}
    except sqlite3.OperationalError:
        return {"data": [], "count": 0}


@router.get("/threats")
def threat_overview(request: Request) -> dict:
    """Aggregate threat levels across all orbital zones."""
    conn = _get_db(request)
    try:
        rows = conn.execute(
            "SELECT threat_level, COUNT(*) as count, "
            "AVG(feral_ai_tier) as avg_tier "
            "FROM orbital_zones GROUP BY threat_level"
        ).fetchall()
        return {"data": [dict(r) for r in rows]}
    except sqlite3.OperationalError:
        return {"data": []}


@router.get("/feral-ai/events")
def list_feral_ai_events(
    request: Request,
    zone_id: str | None = Query(None),
    event_type: str | None = Query(None),
    limit: int = Query(50, le=200),
) -> dict:
    """List feral AI events with optional filters."""
    conn = _get_db(request)
    clauses = []
    params: list = []

    if zone_id:
        clauses.append("zone_id = ?")
        params.append(zone_id)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    try:
        rows = conn.execute(
            f"SELECT * FROM feral_ai_events {where} "  # noqa: S608
            f"ORDER BY detected_at DESC LIMIT ?",
            params,
        ).fetchall()
        data = []
        for r in rows:
            d = dict(r)
            if d.get("action_json"):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    d["action"] = json.loads(d["action_json"])
            data.append(d)
        return {"data": data, "count": len(data)}
    except sqlite3.OperationalError:
        return {"data": [], "count": 0}


@router.get("/cycle")
def cycle_info(request: Request) -> dict:
    """Current universe cycle metadata."""
    import time

    # Cycle 5 started March 11, 2026 (Shroud of Fear)
    cycle_start = 1741651200  # 2026-03-11T00:00:00Z
    now = int(time.time())
    days_elapsed = (now - cycle_start) // 86400

    return {
        "cycle": 5,
        "name": "Shroud of Fear",
        "started_at": cycle_start,
        "days_elapsed": days_elapsed,
    }

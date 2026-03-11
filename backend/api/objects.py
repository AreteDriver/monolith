"""Objects API — track entity state history."""

import contextlib
import json
import sqlite3

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/objects", tags=["objects"])


def _get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


@router.get("/{object_id}")
def get_object(request: Request, object_id: str) -> dict:
    """Get an object's full state trail — current state, transitions, anomalies."""
    conn = _get_db(request)

    # Current object record
    obj = conn.execute("SELECT * FROM objects WHERE object_id = ?", (object_id,)).fetchone()
    if not obj:
        return {"error": "not_found"}

    obj_dict = dict(obj)
    if obj_dict.get("current_state"):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            obj_dict["current_state"] = json.loads(obj_dict["current_state"])

    # State transitions (most recent first)
    transitions = conn.execute(
        "SELECT * FROM state_transitions WHERE object_id = ? ORDER BY timestamp DESC LIMIT 100",
        (object_id,),
    ).fetchall()

    # Anomalies for this object
    anomalies = conn.execute(
        "SELECT anomaly_id, anomaly_type, severity, category, "
        "rule_id, detected_at, evidence_json FROM anomalies "
        "WHERE object_id = ? ORDER BY detected_at DESC LIMIT 50",
        (object_id,),
    ).fetchall()

    # Recent chain events
    events = conn.execute(
        "SELECT event_id, event_type, block_number, transaction_hash, "
        "timestamp FROM chain_events WHERE object_id = ? "
        "ORDER BY timestamp DESC LIMIT 50",
        (object_id,),
    ).fetchall()

    return {
        "object": obj_dict,
        "transitions": [dict(t) for t in transitions],
        "anomalies": [_parse_anomaly(dict(a)) for a in anomalies],
        "events": [dict(e) for e in events],
    }


@router.get("")
def search_objects(
    request: Request,
    object_type: str | None = None,
    system_id: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Search/list tracked objects with filters."""
    conn = _get_db(request)
    query = "SELECT * FROM objects WHERE 1=1"
    params: list = []

    if object_type:
        query += " AND object_type = ?"
        params.append(object_type)
    if system_id:
        query += " AND system_id = ?"
        params.append(system_id)
    if q:
        query += " AND object_id LIKE ?"
        params.append(f"%{q}%")

    query += " ORDER BY last_seen DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return {
        "data": [dict(r) for r in rows],
        "limit": limit,
        "offset": offset,
    }


def _parse_anomaly(a: dict) -> dict:
    if a.get("evidence_json"):
        try:
            a["evidence"] = json.loads(a["evidence_json"])
        except (json.JSONDecodeError, TypeError):
            a["evidence"] = {}
    return a

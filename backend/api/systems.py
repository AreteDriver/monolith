"""Systems API — resolve system IDs to names from reference data."""

import json
import sqlite3

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/systems", tags=["systems"])


def _get_db(request: Request) -> sqlite3.Connection:
    """Get database connection from request state."""
    return request.app.state.db


@router.get("/resolve")
def resolve_system_names(
    request: Request,
    ids: str = Query(..., description="Comma-separated system IDs"),
) -> dict:
    """Resolve system IDs to names from reference_data table.

    Args:
        request: FastAPI request with DB connection.
        ids: Comma-separated system IDs to resolve.

    Returns:
        Dict mapping system_id to name.
    """
    conn = _get_db(request)
    system_ids = [s.strip() for s in ids.split(",") if s.strip()]
    if not system_ids:
        return {"data": {}}

    placeholders = ",".join("?" for _ in system_ids)
    try:
        rows = conn.execute(
            f"SELECT data_id, name FROM reference_data "  # noqa: S608
            f"WHERE data_type = 'solarsystems' AND data_id IN ({placeholders})",
            system_ids,
        ).fetchall()
        result = {row["data_id"]: row["name"] for row in rows}
    except Exception:
        result = {}

    return {"data": result}


@router.get("/{system_id}")
def get_system(request: Request, system_id: str) -> dict:
    """Get full system data from reference_data.

    Args:
        request: FastAPI request with DB connection.
        system_id: The system ID to look up.

    Returns:
        Full system data including parsed data_json.
    """
    conn = _get_db(request)
    try:
        row = conn.execute(
            "SELECT * FROM reference_data WHERE data_type = 'solarsystems' AND data_id = ?",
            (system_id,),
        ).fetchone()
    except Exception:
        return {"error": "reference_data table not available"}

    if not row:
        return {"error": "not_found"}

    d = dict(row)
    if d.get("data_json"):
        try:
            d["data"] = json.loads(d["data_json"])
        except json.JSONDecodeError:
            d["data"] = {}
    return d

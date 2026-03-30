"""Status API — service health dashboard and history."""

import logging
import sqlite3
import time

from fastapi import APIRouter, Query, Request

from backend.alerts.service_health import get_health_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/status", tags=["status"])


def _get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


@router.get("")
def get_status(request: Request) -> dict:
    """Get current status of all monitored services."""
    conn = _get_db(request)
    now = int(time.time())

    # Prefer in-memory state (always up-to-date, survives DB locks).
    # Fall back to DB if memory is empty (e.g. fresh boot before first check).
    mem_state = get_health_state()

    services = []
    if mem_state:
        for name, state in mem_state.items():
            services.append(
                {
                    "service_name": name,
                    "status": state["status"],
                    "response_time_ms": state["response_time_ms"],
                    "error_message": state["error_message"],
                    "last_checked_at": state["last_checked_at"],
                    "last_change_at": state["last_change_at"],
                    "consecutive_failures": state["consecutive_failures"],
                }
            )
    else:
        try:
            rows = conn.execute(
                "SELECT service_name, current_status, last_change_at, "
                "consecutive_failures, last_checked_at FROM service_state"
            ).fetchall()
            for row in rows:
                latest = conn.execute(
                    "SELECT response_time_ms, error_message FROM service_checks "
                    "WHERE service_name = ? ORDER BY checked_at DESC LIMIT 1",
                    (row["service_name"],),
                ).fetchone()
                services.append(
                    {
                        "service_name": row["service_name"],
                        "status": row["current_status"],
                        "response_time_ms": latest["response_time_ms"] if latest else 0,
                        "error_message": latest["error_message"] if latest else None,
                        "last_checked_at": row["last_checked_at"],
                        "last_change_at": row["last_change_at"],
                        "consecutive_failures": row["consecutive_failures"],
                    }
                )
        except sqlite3.OperationalError:
            pass

    # Compute overall status — external dependency failures are "degraded",
    # only internal loop failures are "down" (Monolith core is still serving).
    internal = [s["status"] for s in services if s["service_name"].startswith("loop:")]
    external = [s["status"] for s in services if not s["service_name"].startswith("loop:")]
    if "down" in internal:
        overall = "down"
    elif "down" in external or "degraded" in internal or "degraded" in external:
        overall = "degraded"
    elif internal or external:
        overall = "up"
    else:
        overall = "unknown"

    # Loop heartbeat status from app state
    loops = {}
    heartbeats = getattr(request.app.state, "loop_heartbeats", {})
    expected_intervals = getattr(request.app.state, "loop_intervals", {})
    for loop_name, expected in expected_intervals.items():
        last_beat = heartbeats.get(loop_name)
        if last_beat is None:
            loops[loop_name] = "waiting"
        else:
            age = now - last_beat
            if age > expected * 4:
                loops[loop_name] = "stalled"
            elif age > expected * 2:
                loops[loop_name] = "slow"
            else:
                loops[loop_name] = "ok"

    # Event lag
    event_lag = 0
    try:
        row = conn.execute("SELECT COUNT(*) FROM chain_events WHERE processed = 0").fetchone()
        event_lag = row[0] if row else 0
    except sqlite3.OperationalError:
        pass

    # Detection error rate
    detection_error_rate = 0.0
    try:
        rows = conn.execute(
            "SELECT error FROM detection_cycles ORDER BY started_at DESC LIMIT 10"
        ).fetchall()
        if rows:
            detection_error_rate = round(sum(1 for r in rows if r["error"]) / len(rows), 2)
    except sqlite3.OperationalError:
        pass

    return {
        "services": services,
        "monolith": {
            "loops": loops,
            "event_lag": event_lag,
            "detection_error_rate": detection_error_rate,
        },
        "overall": overall,
        "checked_at": now,
    }


@router.get("/history")
def get_status_history(
    request: Request,
    service: str = Query(..., description="Service name to get history for"),
    limit: int = Query(50, ge=1, le=200, description="Number of checks to return"),
) -> dict:
    """Get recent health check history for a specific service."""
    conn = _get_db(request)
    checks = []
    try:
        rows = conn.execute(
            "SELECT status, response_time_ms, error_message, checked_at "
            "FROM service_checks WHERE service_name = ? ORDER BY checked_at DESC LIMIT ?",
            (service, limit),
        ).fetchall()
        for row in rows:
            checks.append(
                {
                    "status": row["status"],
                    "response_time_ms": row["response_time_ms"],
                    "error_message": row["error_message"],
                    "checked_at": row["checked_at"],
                }
            )
    except sqlite3.OperationalError:
        pass

    return {
        "service_name": service,
        "checks": checks,
    }

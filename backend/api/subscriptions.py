"""Subscriptions API — Discord webhook subscription management."""

import json
import sqlite3
import time
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])

SUBSCRIPTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sub_id TEXT UNIQUE NOT NULL,
    webhook_url TEXT NOT NULL,
    severity_filter TEXT NOT NULL DEFAULT '[]',
    event_types TEXT NOT NULL DEFAULT '[]',
    created_at INTEGER NOT NULL,
    active INTEGER DEFAULT 1
);
"""

SUBSCRIPTIONS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_subscriptions_active ON subscriptions(active);
"""


def _get_db(request: Request) -> sqlite3.Connection:
    """Get database connection from request state."""
    return request.app.state.db


class SubscriptionCreateRequest(BaseModel):
    """Request body for creating a webhook subscription."""

    webhook_url: str
    severity_filter: list[str] = []
    event_types: list[str] = []


@router.post("")
def create_subscription(request: Request, body: SubscriptionCreateRequest) -> dict:
    """Create a new webhook subscription.

    Args:
        request: FastAPI request with DB connection.
        body: Subscription details including webhook URL and filters.

    Returns:
        Created subscription details.
    """
    conn = _get_db(request)
    sub_id = str(uuid.uuid4())[:8]
    now = int(time.time())

    severity_json = json.dumps(body.severity_filter)
    event_types_json = json.dumps(body.event_types)

    try:
        conn.execute(
            "INSERT INTO subscriptions "
            "(sub_id, webhook_url, severity_filter, event_types, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (sub_id, body.webhook_url, severity_json, event_types_json, now),
        )
        conn.commit()
    except sqlite3.OperationalError:
        return {"error": "subscriptions table not available"}

    return {
        "sub_id": sub_id,
        "webhook_url": body.webhook_url,
        "severity_filter": body.severity_filter,
        "event_types": body.event_types,
        "created_at": now,
    }


@router.get("")
def list_subscriptions(request: Request) -> dict:
    """List all active webhook subscriptions.

    Args:
        request: FastAPI request with DB connection.

    Returns:
        List of active subscriptions.
    """
    conn = _get_db(request)

    try:
        rows = conn.execute(
            "SELECT * FROM subscriptions WHERE active = 1 ORDER BY created_at DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        return {"data": [], "error": "subscriptions table not available"}

    data = []
    for row in rows:
        d = dict(row)
        try:
            d["severity_filter"] = json.loads(d.get("severity_filter", "[]"))
        except json.JSONDecodeError:
            d["severity_filter"] = []
        try:
            d["event_types"] = json.loads(d.get("event_types", "[]"))
        except json.JSONDecodeError:
            d["event_types"] = []
        data.append(d)

    return {"data": data}


@router.delete("/{sub_id}")
def delete_subscription(request: Request, sub_id: str) -> dict:
    """Deactivate a webhook subscription.

    Args:
        request: FastAPI request with DB connection.
        sub_id: The subscription ID to deactivate.

    Returns:
        Confirmation of deletion.
    """
    conn = _get_db(request)
    try:
        row = conn.execute(
            "SELECT sub_id FROM subscriptions WHERE sub_id = ? AND active = 1",
            (sub_id,),
        ).fetchone()
        if not row:
            return {"error": "not_found"}

        conn.execute(
            "UPDATE subscriptions SET active = 0 WHERE sub_id = ?",
            (sub_id,),
        )
        conn.commit()
    except sqlite3.OperationalError:
        return {"error": "subscriptions table not available"}

    return {"deleted": sub_id}

"""Subscription dispatcher — sends anomaly alerts to registered webhooks."""

import json
import logging
import sqlite3

import httpx

logger = logging.getLogger(__name__)

# Severity → Discord embed color (decimal)
_SEVERITY_COLORS = {
    "CRITICAL": 0xFF0000,
    "HIGH": 0xFF8C00,
    "MEDIUM": 0xFFD700,
    "LOW": 0x808080,
}


def _truncate(val: str, max_len: int) -> str:
    """Truncate a string with ellipsis if it exceeds max_len."""
    if len(val) <= max_len:
        return val
    return val[: max_len - 3] + "..."


def _build_embed(anomaly: dict) -> dict:
    """Build a Discord-compatible embed payload for an anomaly."""
    severity = anomaly.get("severity", "LOW")
    evidence = anomaly.get("evidence", {})
    description = evidence.get("description", anomaly.get("anomaly_type", "Unknown"))

    return {
        "title": f"\U0001f6a8 {severity}: {anomaly.get('anomaly_type', 'Unknown')}",
        "description": description[:200],
        "color": _SEVERITY_COLORS.get(severity, 0x808080),
        "fields": [
            {
                "name": "Anomaly ID",
                "value": f"`{anomaly.get('anomaly_id', 'N/A')}`",
                "inline": True,
            },
            {
                "name": "Object",
                "value": f"`{_truncate(anomaly.get('object_id', 'N/A'), 20)}`",
                "inline": True,
            },
            {
                "name": "Detector",
                "value": anomaly.get("detector", "unknown"),
                "inline": True,
            },
            {
                "name": "Rule",
                "value": anomaly.get("rule_id", "N/A"),
                "inline": True,
            },
        ],
        "footer": {"text": "MONOLITH v0.5.0 — EVE Frontier Blockchain Integrity Monitor"},
    }


def _matches_filters(
    anomaly: dict,
    severity_filter: list[str],
    event_types: list[str],
) -> bool:
    """Check if an anomaly matches a subscription's filters.

    If a filter list is non-empty, the anomaly must match at least one entry.
    If both filters are empty, everything matches.
    """
    severity = anomaly.get("severity", "LOW")
    anomaly_type = anomaly.get("anomaly_type", "")

    if severity_filter and severity not in severity_filter:
        return False
    return not (event_types and anomaly_type not in event_types)


async def dispatch_to_subscribers(conn, anomaly: dict) -> int:
    """Dispatch an anomaly alert to all matching active subscriptions.

    Args:
        conn: SQLite database connection.
        anomaly: Anomaly dict with keys like severity, anomaly_type, etc.

    Returns:
        Count of successful webhook sends.
    """
    try:
        rows = conn.execute(
            "SELECT sub_id, webhook_url, severity_filter, event_types "
            "FROM subscriptions WHERE active = 1"
        ).fetchall()
    except sqlite3.OperationalError:
        logger.debug("subscriptions table not available — skipping dispatch")
        return 0
    except Exception:
        logger.exception("Failed to query subscriptions")
        return 0

    if not rows:
        return 0

    embed = _build_embed(anomaly)
    payload = {"embeds": [embed]}
    sent = 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        for row in rows:
            webhook_url = row["webhook_url"] if isinstance(row, sqlite3.Row) else row[1]
            raw_severity = row["severity_filter"] if isinstance(row, sqlite3.Row) else row[2]
            raw_events = row["event_types"] if isinstance(row, sqlite3.Row) else row[3]

            try:
                severity_filter = json.loads(raw_severity) if raw_severity else []
            except (json.JSONDecodeError, TypeError):
                severity_filter = []

            try:
                event_types = json.loads(raw_events) if raw_events else []
            except (json.JSONDecodeError, TypeError):
                event_types = []

            if not _matches_filters(anomaly, severity_filter, event_types):
                continue

            try:
                resp = await client.post(webhook_url, json=payload)
                if resp.status_code in (200, 204):
                    sent += 1
                    logger.info(
                        "Subscription dispatch sent to %s (sub %s)",
                        _truncate(webhook_url, 40),
                        row["sub_id"] if isinstance(row, sqlite3.Row) else row[0],
                    )
                else:
                    logger.warning(
                        "Subscription webhook %s returned %d",
                        _truncate(webhook_url, 40),
                        resp.status_code,
                    )
            except Exception:
                logger.exception(
                    "Subscription dispatch failed for %s",
                    _truncate(webhook_url, 40),
                )

    return sent

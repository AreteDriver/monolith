"""Anomaly enrichment — resolve who/what/when/where behind each detection.

Takes raw anomalies (hex object IDs, empty system IDs, no entity names)
and enriches them with:
- Entity name and type (from objects table / chain events)
- System name (from reference_data)
- Owner identity (address → name via tribe_cache or objects)
- Related killmails in the same system/timeframe
- Connected chain events that triggered the detection
"""

import contextlib
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def enrich_anomalies(conn: sqlite3.Connection, limit: int = 50) -> int:
    """Enrich recent anomalies that have no context_json yet.

    Returns the number of anomalies enriched.
    """
    if conn is None:
        return 0

    try:
        rows = conn.execute(
            "SELECT id, anomaly_id, object_id, system_id, detected_at, evidence_json "
            "FROM anomalies WHERE context_json IS NULL "
            "ORDER BY detected_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        if not rows:
            return 0

        enriched = 0
        for row in rows:
            context = _build_context(conn, row)
            if context:
                conn.execute(
                    "UPDATE anomalies SET context_json = ? WHERE id = ?",
                    (json.dumps(context), row["id"]),
                )
                enriched += 1

        if enriched:
            conn.commit()
            logger.info("Enriched %d anomalies with intel context", enriched)

        return enriched
    except (AttributeError, sqlite3.OperationalError) as exc:
        logger.warning("Enrichment skipped: %s", exc)
        return 0


def _build_context(conn: sqlite3.Connection, anomaly: sqlite3.Row) -> dict:
    """Build enriched context for a single anomaly."""
    object_id = anomaly["object_id"] or ""
    system_id = anomaly["system_id"] or ""
    detected_at = anomaly["detected_at"] or 0

    context = {}

    # 1. Resolve object — find full ID, type, owner from objects table
    obj = _resolve_object(conn, object_id)
    if obj:
        context["entity_name"] = obj.get("name", "")
        context["entity_type"] = obj.get("type", "")
        context["owner"] = obj.get("owner", "")
        if obj.get("system_id"):
            system_id = obj["system_id"]
            context["system_id"] = system_id

    # 2. Resolve system name
    if system_id:
        context["system_id"] = system_id
        sys_name = _resolve_system_name(conn, system_id)
        if sys_name:
            context["system_name"] = sys_name

    # 3. Find related chain events (what triggered this)
    related_events = _find_related_events(conn, object_id, detected_at)
    if related_events:
        context["related_events"] = related_events

    # 4. Find nearby killmails (who was fighting here)
    if system_id:
        killmails = _find_nearby_killmails(conn, system_id, detected_at)
        if killmails:
            context["nearby_killmails"] = killmails

    # 5. Resolve owner name if we have an owner address
    if context.get("owner"):
        owner_name = _resolve_entity_name(conn, context["owner"])
        if owner_name:
            context["owner_name"] = owner_name

    return context


def _resolve_object(conn: sqlite3.Connection, object_id: str) -> dict | None:
    """Resolve object_id (possibly truncated) to full object data."""
    if not object_id:
        return None

    # Try exact match first
    row = conn.execute(
        "SELECT object_id, object_type, system_id, current_owner, current_state "
        "FROM objects WHERE object_id = ?",
        (object_id,),
    ).fetchone()

    # Try prefix match for truncated IDs
    if not row and len(object_id) > 10:
        row = conn.execute(
            "SELECT object_id, object_type, system_id, current_owner, current_state "
            "FROM objects WHERE object_id LIKE ? LIMIT 1",
            (object_id + "%",),
        ).fetchone()

    if not row:
        return None

    state = {}
    with contextlib.suppress(json.JSONDecodeError, TypeError):
        state = json.loads(row["current_state"] or "{}")

    name = state.get("name", state.get("display_name", ""))
    obj_type = row["object_type"] or state.get("type", "")

    return {
        "full_id": row["object_id"],
        "type": obj_type,
        "system_id": row["system_id"] or "",
        "owner": row["current_owner"] or "",
        "name": name,
    }


def _resolve_system_name(conn: sqlite3.Connection, system_id: str) -> str:
    """Resolve system_id to human-readable name from reference_data."""
    row = conn.execute(
        "SELECT name FROM reference_data WHERE data_type = 'solarsystems' AND data_id = ?",
        (system_id,),
    ).fetchone()
    return row["name"] if row else ""


def _resolve_entity_name(conn: sqlite3.Connection, address: str) -> str:
    """Try to resolve an on-chain address to a display name."""
    if not address:
        return ""

    # Check objects table for character type
    row = conn.execute(
        "SELECT current_state FROM objects WHERE object_id = ? AND object_type = 'character'",
        (address,),
    ).fetchone()
    if row:
        try:
            state = json.loads(row["current_state"] or "{}")
            name = state.get("name", state.get("display_name", ""))
            if name:
                return name
        except (json.JSONDecodeError, TypeError):
            pass

    # Check tribe_cache
    row = conn.execute(
        "SELECT name FROM tribe_cache WHERE tribe_id = ? OR tribe_id LIKE ?",
        (address, address[:20] + "%"),
    ).fetchone()
    if row:
        return row["name"]

    return ""


def _find_related_events(
    conn: sqlite3.Connection, object_id: str, detected_at: int, window: int = 3600
) -> list[dict]:
    """Find chain events related to this object near detection time."""
    if not object_id:
        return []

    # Search with prefix match for truncated IDs
    rows = conn.execute(
        "SELECT event_type, timestamp, transaction_hash "
        "FROM chain_events WHERE object_id LIKE ? "
        "AND timestamp BETWEEN ? AND ? "
        "ORDER BY timestamp DESC LIMIT 5",
        (object_id + "%", detected_at - window, detected_at + 300),
    ).fetchall()

    return [
        {
            "event_type": _short_event_type(r["event_type"]),
            "timestamp": r["timestamp"],
            "tx": (r["transaction_hash"] or "")[:16],
        }
        for r in rows
    ]


def _find_nearby_killmails(
    conn: sqlite3.Connection, system_id: str, detected_at: int, window: int = 86400
) -> list[dict]:
    """Find killmails in the same system within 24h of detection."""
    rows = conn.execute(
        "SELECT payload FROM nexus_events "
        "WHERE event_type = 'killmail' AND solar_system_id = ? "
        "AND received_at BETWEEN ? AND ? "
        "ORDER BY received_at DESC LIMIT 3",
        (system_id, detected_at - window, detected_at + 3600),
    ).fetchall()

    results = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            continue

        victim_id = payload.get("victim_character_id", "")
        attackers_raw = payload.get("attacker_character_ids", "[]")
        if isinstance(attackers_raw, str):
            try:
                attackers = json.loads(attackers_raw)
            except (json.JSONDecodeError, TypeError):
                attackers = []
        else:
            attackers = attackers_raw if isinstance(attackers_raw, list) else []

        attacker_names = []
        for a in attackers:
            if isinstance(a, dict):
                attacker_names.append(a.get("name") or a.get("characterId", "")[:12])
            else:
                attacker_names.append(str(a)[:12])

        results.append(
            {
                "killmail_id": payload.get("killmail_id", ""),
                "victim": victim_id[:16] if victim_id else "",
                "attackers": attacker_names[:3],
                "timestamp": payload.get("timestamp", 0),
            }
        )

    return results


def _short_event_type(event_type: str) -> str:
    """Extract short event name from full Move event type string."""
    # "0xpkg::module::EventName" → "EventName"
    if "::" in event_type:
        return event_type.rsplit("::", 1)[-1]
    return event_type

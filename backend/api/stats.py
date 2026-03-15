"""Stats API — anomaly rates and system health metrics."""

import json
import sqlite3
import time

from fastapi import APIRouter, Request

from backend.alerts.github_issues import get_filed_count

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


@router.get("")
def get_stats(request: Request) -> dict:
    """Get anomaly statistics — rates, breakdowns, system health."""
    conn = _get_db(request)
    now = int(time.time())
    cutoff_24h = now - 86400

    # Total anomalies last 24h
    total_24h = conn.execute(
        "SELECT COUNT(*) FROM anomalies WHERE detected_at >= ?",
        (cutoff_24h,),
    ).fetchone()[0]

    # By severity
    by_severity = {}
    for row in conn.execute(
        "SELECT severity, COUNT(*) as cnt FROM anomalies WHERE detected_at >= ? GROUP BY severity",
        (cutoff_24h,),
    ).fetchall():
        by_severity[row["severity"]] = row["cnt"]

    # By type
    by_type = {}
    for row in conn.execute(
        "SELECT anomaly_type, COUNT(*) as cnt FROM anomalies "
        "WHERE detected_at >= ? GROUP BY anomaly_type ORDER BY cnt DESC",
        (cutoff_24h,),
    ).fetchall():
        by_type[row["anomaly_type"]] = row["cnt"]

    # By detector
    by_detector = {}
    for row in conn.execute(
        "SELECT detector, COUNT(*) as cnt FROM anomalies WHERE detected_at >= ? GROUP BY detector",
        (cutoff_24h,),
    ).fetchall():
        by_detector[row["detector"]] = row["cnt"]

    # By system (top 10)
    by_system = []
    for row in conn.execute(
        "SELECT system_id, COUNT(*) as cnt FROM anomalies "
        "WHERE detected_at >= ? AND system_id != '' "
        "GROUP BY system_id ORDER BY cnt DESC LIMIT 10",
        (cutoff_24h,),
    ).fetchall():
        by_system.append({"system_id": row["system_id"], "count": row["cnt"]})

    # Hourly rate (last 24 buckets)
    hourly_rate = []
    for i in range(24):
        bucket_start = cutoff_24h + (i * 3600)
        bucket_end = bucket_start + 3600
        count = conn.execute(
            "SELECT COUNT(*) FROM anomalies WHERE detected_at >= ? AND detected_at < ?",
            (bucket_start, bucket_end),
        ).fetchone()[0]
        hourly_rate.append({"hour": i, "timestamp": bucket_start, "count": count})

    # False positive rate
    total_all = conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
    false_positives = conn.execute(
        "SELECT COUNT(*) FROM anomalies WHERE status = 'FALSE_POSITIVE'"
    ).fetchone()[0]
    fp_rate = false_positives / total_all if total_all > 0 else 0.0

    # Events processed 24h
    events_24h = conn.execute(
        "SELECT COUNT(*) FROM chain_events WHERE timestamp >= ?",
        (cutoff_24h,),
    ).fetchone()[0]

    # Last block
    last_block_row = conn.execute("SELECT MAX(block_number) FROM chain_events").fetchone()
    last_block = last_block_row[0] if last_block_row and last_block_row[0] else 0

    # POD-related anomalies in last 24h
    try:
        pod_24h = conn.execute(
            "SELECT COUNT(*) FROM anomalies "
            "WHERE detected_at >= ? AND ("
            "  LOWER(detector) LIKE '%pod%' OR LOWER(anomaly_type) LIKE '%pod%'"
            ")",
            (cutoff_24h,),
        ).fetchone()[0]
    except Exception:
        pod_24h = 0

    return {
        "anomaly_rate_24h": total_24h,
        "anomaly_rate_by_hour": hourly_rate,
        "by_severity": by_severity,
        "by_type": by_type,
        "by_detector": by_detector,
        "by_system": by_system,
        "false_positive_rate": round(fp_rate, 4),
        "events_processed_24h": events_24h,
        "last_block_processed": last_block,
        "bug_reports_filed": get_filed_count(conn),
        "pod_anomalies_24h": pod_24h,
    }


@router.get("/map")
def get_map_data(request: Request) -> dict:
    """Get anomaly-affected systems with coordinates for map rendering."""
    conn = _get_db(request)

    # Resolve effective system_id: prefer anomaly's own, fall back to objects table
    # COALESCE + NULLIF treats '' same as NULL for the fallback
    rows = conn.execute(
        "SELECT COALESCE(NULLIF(a.system_id, ''), o.system_id, '') as eff_system_id, "
        "  COUNT(*) as count, "
        "  SUM(CASE WHEN a.severity = 'CRITICAL' THEN 1 ELSE 0 END) as critical, "
        "  SUM(CASE WHEN a.severity = 'HIGH' THEN 1 ELSE 0 END) as high, "
        "  SUM(CASE WHEN a.severity = 'MEDIUM' THEN 1 ELSE 0 END) as medium, "
        "  SUM(CASE WHEN a.severity = 'LOW' THEN 1 ELSE 0 END) as low "
        "FROM anomalies a "
        "LEFT JOIN objects o ON a.object_id = o.object_id "
        "WHERE a.status != 'FALSE_POSITIVE' "
        "GROUP BY eff_system_id "
        "HAVING eff_system_id != '' "
        "ORDER BY count DESC"
    ).fetchall()

    systems = []
    system_ids = [r["eff_system_id"] for r in rows]

    # Batch-fetch coordinates from reference_data
    coords = {}
    if system_ids:
        placeholders = ",".join("?" for _ in system_ids)
        ref_rows = conn.execute(
            f"SELECT data_id, name, data_json FROM reference_data "  # noqa: S608
            f"WHERE data_type = 'solarsystems' AND data_id IN ({placeholders})",
            system_ids,
        ).fetchall()
        for ref in ref_rows:
            try:
                data = json.loads(ref["data_json"]) if ref["data_json"] else {}
                loc = data.get("location", {})
                coords[ref["data_id"]] = {
                    "name": ref["name"] or data.get("name", ""),
                    "x": loc.get("x", 0),
                    "z": loc.get("z", 0),
                }
            except (json.JSONDecodeError, TypeError):
                pass

    for row in rows:
        sid = row["eff_system_id"]
        c = coords.get(sid)
        if not c:
            continue
        systems.append(
            {
                "system_id": sid,
                "name": c["name"],
                "x": c["x"],
                "z": c["z"],
                "count": row["count"],
                "critical": row["critical"],
                "high": row["high"],
                "medium": row["medium"],
                "low": row["low"],
            }
        )

    # Recent events for animated markers (last 24h, newest first)
    # Same COALESCE fallback to objects.system_id
    now = int(time.time())
    cutoff_24h = now - 86400
    event_rows = conn.execute(
        "SELECT a.anomaly_id, a.anomaly_type, a.severity, a.detected_at, "
        "  COALESCE(NULLIF(a.system_id, ''), o.system_id, '') as eff_system_id "
        "FROM anomalies a "
        "LEFT JOIN objects o ON a.object_id = o.object_id "
        "WHERE a.status != 'FALSE_POSITIVE' "
        "AND a.detected_at >= ? "
        "AND COALESCE(NULLIF(a.system_id, ''), o.system_id, '') != '' "
        "ORDER BY a.detected_at DESC LIMIT 200",
        (cutoff_24h,),
    ).fetchall()

    recent_events = []
    for ev in event_rows:
        sid = ev["eff_system_id"]
        c = coords.get(sid)
        if not c:
            continue
        recent_events.append(
            {
                "anomaly_id": ev["anomaly_id"],
                "anomaly_type": ev["anomaly_type"],
                "severity": ev["severity"],
                "system_id": sid,
                "system_name": c["name"],
                "x": c["x"],
                "z": c["z"],
                "detected_at": ev["detected_at"],
            }
        )

    return {"systems": systems, "recent_events": recent_events}


@router.get("/ledger")
def get_ledger_stats(request: Request) -> dict:
    """Get item ledger statistics — event counts, top assemblies, breakdown.

    Args:
        request: FastAPI request with DB connection.

    Returns:
        Ledger stats including totals, top assemblies, and event type breakdown.
    """
    conn = _get_db(request)

    try:
        # Total distinct item combos tracked
        total_items = conn.execute(
            "SELECT COUNT(DISTINCT assembly_id || ':' || item_type_id) FROM item_ledger"
        ).fetchone()[0]

        # Total events
        total_events = conn.execute("SELECT COUNT(*) FROM item_ledger").fetchone()[0]

        # Top 10 most active assemblies by event count
        top_assemblies = []
        for row in conn.execute(
            "SELECT assembly_id, COUNT(*) as cnt FROM item_ledger "
            "GROUP BY assembly_id ORDER BY cnt DESC LIMIT 10"
        ).fetchall():
            top_assemblies.append(
                {
                    "assembly_id": row["assembly_id"],
                    "event_count": row["cnt"],
                }
            )

        # Breakdown by event_type
        by_event_type = {}
        for row in conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM item_ledger "
            "GROUP BY event_type ORDER BY cnt DESC"
        ).fetchall():
            by_event_type[row["event_type"]] = row["cnt"]

    except Exception:
        return {
            "total_items_tracked": 0,
            "total_events": 0,
            "top_assemblies": [],
            "by_event_type": {},
            "error": "item_ledger table empty or unavailable",
        }

    return {
        "total_items_tracked": total_items,
        "total_events": total_events,
        "top_assemblies": top_assemblies,
        "by_event_type": by_event_type,
    }

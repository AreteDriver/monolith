"""Stats API — anomaly rates and system health metrics."""

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
    }

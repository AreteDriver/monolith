"""Stats API — anomaly rates and system health metrics."""

import asyncio
import json
import logging
import sqlite3
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.alerts.github_issues import get_filed_count
from backend.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])

# In-memory cache for static background systems (24K systems, ~2MB JSON).
# Reference data changes only on server restart, so cache indefinitely.
_bg_systems_cache: list[dict] | None = None
_bg_systems_etag: str | None = None
_bg_bounds: dict | None = None  # {min_x, max_x, min_z, max_z, range_x, range_z}

# WatchTower overlay cache — refreshed every 60s, serves stale on failure.
_wt_cache: dict | None = None
_wt_cache_time: float = 0
_WT_CACHE_TTL = 60  # seconds

# Map data cache — anomaly aggregation is expensive, cache for 30s.
_map_cache: dict | None = None
_map_cache_time: float = 0
_MAP_CACHE_TTL = 30  # seconds


def clear_map_cache() -> None:
    """Clear the map data cache (used by tests)."""
    global _map_cache, _map_cache_time  # noqa: PLW0603
    _map_cache = None
    _map_cache_time = 0


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
    except sqlite3.OperationalError:
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
    global _map_cache, _map_cache_time  # noqa: PLW0603
    now = time.time()
    if _map_cache is not None and (now - _map_cache_time) < _MAP_CACHE_TTL:
        return _map_cache

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

    # Ensure bg systems are loaded so we have bounds for normalization
    _load_bg_systems(conn)
    bounds = _bg_bounds

    for row in rows:
        sid = row["eff_system_id"]
        c = coords.get(sid)
        if not c:
            continue
        entry = {
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
        if bounds:
            entry["nx"] = (c["x"] - bounds["min_x"]) / bounds["range_x"]
            entry["nz"] = (c["z"] - bounds["min_z"]) / bounds["range_z"]
        systems.append(entry)

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
        entry = {
            "anomaly_id": ev["anomaly_id"],
            "anomaly_type": ev["anomaly_type"],
            "severity": ev["severity"],
            "system_id": sid,
            "system_name": c["name"],
            "x": c["x"],
            "z": c["z"],
            "detected_at": ev["detected_at"],
        }
        if bounds:
            entry["nx"] = (c["x"] - bounds["min_x"]) / bounds["range_x"]
            entry["nz"] = (c["z"] - bounds["min_z"]) / bounds["range_z"]
        recent_events.append(entry)

    result = {
        "systems": systems,
        "recent_events": recent_events,
    }
    _map_cache = result
    _map_cache_time = time.time()
    return result


def _load_bg_systems(conn: sqlite3.Connection) -> list[dict]:
    """Load and cache background systems from reference_data."""
    global _bg_systems_cache, _bg_systems_etag  # noqa: PLW0603
    if _bg_systems_cache is not None:
        return _bg_systems_cache

    all_systems = []
    all_ref = conn.execute(
        "SELECT data_id, name, data_json FROM reference_data WHERE data_type = 'solarsystems'"
    ).fetchall()
    for ref in all_ref:
        try:
            data = json.loads(ref["data_json"]) if ref["data_json"] else {}
            loc = data.get("location", {})
            x = loc.get("x", 0)
            z = loc.get("z", 0)
            if x == 0 and z == 0:
                continue
            all_systems.append(
                {
                    "system_id": ref["data_id"],
                    "name": ref["name"] or data.get("name", ""),
                    "x": x,
                    "z": z,
                }
            )
        except (json.JSONDecodeError, TypeError):
            pass

    # Compute coordinate bounds for normalization (Python handles big ints)
    global _bg_bounds  # noqa: PLW0603
    if all_systems:
        min_x = min(s["x"] for s in all_systems)
        max_x = max(s["x"] for s in all_systems)
        min_z = min(s["z"] for s in all_systems)
        max_z = max(s["z"] for s in all_systems)
        range_x = max_x - min_x or 1
        range_z = max_z - min_z or 1
        _bg_bounds = {
            "min_x": min_x,
            "max_x": max_x,
            "min_z": min_z,
            "max_z": max_z,
            "range_x": range_x,
            "range_z": range_z,
        }
        # Pre-compute normalized coords (0..1) server-side to avoid JS float64 precision loss
        for s in all_systems:
            s["nx"] = (s["x"] - min_x) / range_x
            s["nz"] = (s["z"] - min_z) / range_z

    _bg_systems_cache = all_systems
    _bg_systems_etag = str(len(all_systems))
    logger.info("Background systems cached: %d systems", len(all_systems))
    return all_systems


@router.get("/map/systems")
def get_background_systems(request: Request):
    """Get all background systems (slim: nx/nz/name only to keep payload under 500KB)."""
    conn = _get_db(request)
    systems = _load_bg_systems(conn)

    # Support ETag for client-side caching
    if_none_match = request.headers.get("if-none-match")
    if if_none_match == _bg_systems_etag:
        from starlette.responses import Response

        return Response(status_code=304)

    # Strip raw coords — frontend only needs normalized nx/nz + name
    slim = [
        {
            "system_id": s["system_id"],
            "name": s["name"],
            "nx": round(s["nx"], 6),
            "nz": round(s["nz"], 6),
        }
        for s in systems
        if "nx" in s
    ]

    # Don't cache empty responses — static data may still be loading
    cache_control = "public, max-age=3600" if slim else "no-cache"

    return JSONResponse(
        content={"all_systems": slim},
        headers={
            "Cache-Control": cache_control,
            "ETag": _bg_systems_etag or "",
        },
    )


@router.post("/map/enrich")
def enrich_system_ids(request: Request) -> dict:
    """One-time backfill: enrich objects.system_id from existing nexus killmails."""
    conn = _get_db(request)
    rows = conn.execute(
        "SELECT payload, solar_system_id FROM nexus_events "
        "WHERE event_type = 'killmail' AND solar_system_id != ''"
    ).fetchall()

    enriched = 0
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            continue
        solar_id = row["solar_system_id"]
        object_ids = set()
        for key in ("victim", "killer"):
            entity = payload.get(key, {})
            if isinstance(entity, dict):
                oid = entity.get("id", "") or entity.get("address", "")
                if oid:
                    object_ids.add(str(oid))
        for oid in object_ids:
            cur = conn.execute(
                "UPDATE objects SET system_id = ? "
                "WHERE object_id = ? AND (system_id IS NULL OR system_id = '')",
                (solar_id, oid),
            )
            enriched += cur.rowcount
    conn.commit()
    return {"enriched_objects": enriched, "killmails_processed": len(rows)}


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

    except sqlite3.OperationalError:
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


def _build_coord_lookup(conn: sqlite3.Connection) -> dict[str, dict]:
    """Build system_id → {nx, nz, name} lookup from reference_data.

    Reuses the cached background systems to avoid re-querying 24K rows.
    """
    _load_bg_systems(conn)
    if not _bg_systems_cache:
        return {}
    return {
        s["system_id"]: {"nx": s.get("nx", 0), "nz": s.get("nz", 0), "name": s.get("name", "")}
        for s in _bg_systems_cache
        if "nx" in s
    }


async def _fetch_watchtower(client: httpx.AsyncClient, path: str) -> dict | list | None:
    """Fetch a single WatchTower endpoint, return None on any failure."""
    settings = get_settings()
    url = f"{settings.watchtower_api_url}{path}"
    try:
        resp = await client.get(url, timeout=settings.watchtower_api_timeout)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        logger.warning("WatchTower fetch failed: %s → %s", path, exc)
        return None


@router.get("/map/watchtower")
async def get_watchtower_overlay(request: Request) -> dict:
    """WatchTower intelligence overlay — hotzones, threat forecast, assemblies.

    Fetches from WatchTower API, joins with local reference_data for normalized
    coordinates, caches 60s, and serves stale data on upstream failure.
    """
    global _wt_cache, _wt_cache_time  # noqa: PLW0603

    now = time.time()
    if _wt_cache and (now - _wt_cache_time) < _WT_CACHE_TTL:
        return _wt_cache

    conn = _get_db(request)
    coord_lookup = _build_coord_lookup(conn)

    if not coord_lookup:
        logger.warning("No reference_data for WatchTower coord resolution")
        return _wt_cache or {"hotzones": [], "threat_systems": [], "assemblies": []}

    # Fetch all 3 endpoints in parallel
    async with httpx.AsyncClient() as client:
        hz_raw, threat_raw, asm_raw = await asyncio.gather(
            _fetch_watchtower(client, "/hotzones?window=7d&limit=50"),
            _fetch_watchtower(client, "/predictions/map"),
            _fetch_watchtower(client, "/assemblies"),
        )

    # If all three failed, serve stale cache
    if hz_raw is None and threat_raw is None and asm_raw is None:
        logger.warning("All WatchTower fetches failed, serving stale cache")
        return _wt_cache or {"hotzones": [], "threat_systems": [], "assemblies": []}

    # --- Hotzones: join with coords ---
    hotzones = []
    for hz in (hz_raw or {}).get("hotzones", []):
        sid = hz.get("solar_system_id", "")
        coord = coord_lookup.get(sid)
        if not coord:
            continue
        hotzones.append(
            {
                "system_id": sid,
                "name": hz.get("solar_system_name") or coord["name"],
                "nx": coord["nx"],
                "nz": coord["nz"],
                "kills": hz.get("kills", 0),
                "danger_level": hz.get("danger_level", "minimal"),
                "unique_attackers": hz.get("unique_attackers", 0),
            }
        )

    # --- Threat forecast: join with coords ---
    threat_systems = []
    for ts in (threat_raw or {}).get("systems", []):
        sid = ts.get("solar_system_id", "")
        coord = coord_lookup.get(sid)
        if not coord:
            continue
        threat_systems.append(
            {
                "system_id": sid,
                "name": ts.get("solar_system_name") or coord["name"],
                "nx": coord["nx"],
                "nz": coord["nz"],
                "threat_score": ts.get("threat_score", 0),
                "threat_level": ts.get("threat_level", "minimal"),
                "kill_trend": ts.get("kill_trend", "none"),
                "kills_7d": ts.get("kills_7d", 0),
            }
        )

    # --- Assemblies: join with coords (use reference_data, not WT's sparse positions) ---
    assemblies = []
    for asm in (asm_raw or {}).get("assemblies", []):
        sid = asm.get("solar_system_id", "")
        coord = coord_lookup.get(sid)
        if not coord:
            continue
        assemblies.append(
            {
                "assembly_id": asm.get("assembly_id", ""),
                "type": asm.get("type", "Unknown"),
                "system_id": sid,
                "name": asm.get("solar_system_name") or coord["name"],
                "nx": coord["nx"],
                "nz": coord["nz"],
                "state": asm.get("state", "unknown"),
            }
        )

    result = {
        "hotzones": hotzones,
        "threat_systems": threat_systems,
        "assemblies": assemblies,
        "fetched_at": int(now),
    }
    _wt_cache = result
    _wt_cache_time = now
    return result

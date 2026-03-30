"""Service health checker — monitors external services and internal loop health."""

import dataclasses
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)


# In-memory health state — always reflects the latest check results,
# even when SQLite is locked and record_check() can't write.
# Key: service_name, Value: dict with status, response_time_ms, error_message,
# last_checked_at, last_change_at, consecutive_failures.
_health_state: dict[str, dict] = {}


@dataclasses.dataclass
class CheckResult:
    """Result of a single service health check."""

    service_name: str
    status: str  # "up", "down", "degraded"
    response_time_ms: int
    error_message: str | None
    checked_at: int


async def check_world_api(
    client: httpx.AsyncClient,
    base_url: str,
    timeout: int = 10,
    degraded_threshold_ms: int = 5000,
) -> CheckResult:
    """Check World API health via /config endpoint."""
    now = int(time.time())
    start = time.monotonic()
    try:
        resp = await client.get(f"{base_url}/config", timeout=float(timeout))
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code != 200:
            return CheckResult("world_api", "down", elapsed_ms, f"HTTP {resp.status_code}", now)
        if elapsed_ms > degraded_threshold_ms:
            return CheckResult("world_api", "degraded", elapsed_ms, "Slow response", now)
        return CheckResult("world_api", "up", elapsed_ms, None, now)
    except (httpx.HTTPError, OSError) as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return CheckResult("world_api", "down", elapsed_ms, str(exc)[:200], now)


async def check_sui_rpc(
    client: httpx.AsyncClient,
    rpc_url: str,
    timeout: int = 10,
    degraded_threshold_ms: int = 5000,
) -> CheckResult:
    """Check Sui RPC health via getLatestCheckpointSequenceNumber."""
    now = int(time.time())
    start = time.monotonic()
    try:
        resp = await client.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sui_getLatestCheckpointSequenceNumber",
                "params": [],
            },
            timeout=float(timeout),
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code != 200:
            return CheckResult("sui_rpc", "down", elapsed_ms, f"HTTP {resp.status_code}", now)
        data = resp.json()
        if "result" not in data:
            return CheckResult("sui_rpc", "down", elapsed_ms, "No result in RPC response", now)
        if elapsed_ms > degraded_threshold_ms:
            return CheckResult("sui_rpc", "degraded", elapsed_ms, "Slow response", now)
        return CheckResult("sui_rpc", "up", elapsed_ms, None, now)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return CheckResult("sui_rpc", "down", elapsed_ms, str(exc)[:200], now)


async def check_watchtower(
    client: httpx.AsyncClient,
    base_url: str,
    timeout: int = 10,
    degraded_threshold_ms: int = 5000,
) -> CheckResult:
    """Check WatchTower API health."""
    now = int(time.time())
    start = time.monotonic()
    try:
        resp = await client.get(f"{base_url}/health", timeout=float(timeout))
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code != 200:
            return CheckResult("watchtower", "down", elapsed_ms, f"HTTP {resp.status_code}", now)
        if elapsed_ms > degraded_threshold_ms:
            return CheckResult("watchtower", "degraded", elapsed_ms, "Slow response", now)
        return CheckResult("watchtower", "up", elapsed_ms, None, now)
    except (httpx.HTTPError, OSError) as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return CheckResult("watchtower", "down", elapsed_ms, str(exc)[:200], now)


def check_loop_health(
    heartbeats: dict[str, float],
    expected_intervals: dict[str, int],
    stall_multiplier: float = 2.0,
) -> list[CheckResult]:
    """Check if background loops are running on schedule.

    Args:
        heartbeats: dict of loop_name -> last heartbeat timestamp (time.time())
        expected_intervals: dict of loop_name -> expected interval in seconds
        stall_multiplier: alert if no heartbeat in N * expected_interval
    """
    now = time.time()
    now_int = int(now)
    results = []

    for loop_name, expected in expected_intervals.items():
        last_beat = heartbeats.get(loop_name)
        service_name = f"loop:{loop_name}"

        if last_beat is None:
            # Loop hasn't reported yet — could be in initial delay
            results.append(CheckResult(service_name, "up", 0, "Awaiting first heartbeat", now_int))
            continue

        age = now - last_beat
        threshold = expected * stall_multiplier

        if age > threshold * 2:
            results.append(
                CheckResult(service_name, "down", 0, f"No heartbeat for {int(age)}s", now_int)
            )
        elif age > threshold:
            results.append(
                CheckResult(
                    service_name,
                    "degraded",
                    0,
                    f"Heartbeat {int(age)}s old (expected {expected}s)",
                    now_int,
                )
            )
        else:
            results.append(CheckResult(service_name, "up", 0, None, now_int))

    return results


def check_event_lag(conn: sqlite3.Connection) -> CheckResult:
    """Check unprocessed event count as a health signal."""
    now = int(time.time())
    try:
        row = conn.execute("SELECT COUNT(*) FROM chain_events WHERE processed = 0").fetchone()
        count = row[0] if row else 0

        if count > 5000:
            return CheckResult("event_lag", "down", 0, f"{count} unprocessed events", now)
        if count > 1000:
            return CheckResult("event_lag", "degraded", 0, f"{count} unprocessed events", now)
        return CheckResult("event_lag", "up", 0, None, now)
    except sqlite3.OperationalError as exc:
        return CheckResult("event_lag", "down", 0, str(exc)[:200], now)


def check_detection_errors(conn: sqlite3.Connection) -> CheckResult:
    """Check recent detection cycle error rate."""
    now = int(time.time())
    try:
        rows = conn.execute(
            "SELECT error FROM detection_cycles ORDER BY started_at DESC LIMIT 10"
        ).fetchall()

        if not rows:
            return CheckResult("detection_health", "up", 0, "No cycles recorded yet", now)

        error_count = sum(1 for r in rows if r["error"])
        total = len(rows)
        rate = error_count / total

        if rate > 0.8:
            return CheckResult(
                "detection_health", "down", 0, f"{error_count}/{total} cycles failed", now
            )
        if rate > 0.5:
            return CheckResult(
                "detection_health", "degraded", 0, f"{error_count}/{total} cycles failed", now
            )
        return CheckResult("detection_health", "up", 0, None, now)
    except sqlite3.OperationalError as exc:
        return CheckResult("detection_health", "down", 0, str(exc)[:200], now)


def _update_memory_state(result: CheckResult) -> str | None:
    """Update in-memory health state. Returns transition string if state changed."""
    name = result.service_name
    prev = _health_state.get(name)

    if prev is None:
        _health_state[name] = {
            "status": result.status,
            "response_time_ms": result.response_time_ms,
            "error_message": result.error_message,
            "last_checked_at": result.checked_at,
            "last_change_at": result.checked_at,
            "consecutive_failures": 0 if result.status == "up" else 1,
        }
        return None

    old_status = prev["status"]
    new_failures = 0 if result.status == "up" else prev["consecutive_failures"] + 1

    prev["status"] = result.status
    prev["response_time_ms"] = result.response_time_ms
    prev["error_message"] = result.error_message
    prev["last_checked_at"] = result.checked_at
    prev["consecutive_failures"] = new_failures

    if old_status != result.status:
        prev["last_change_at"] = result.checked_at
        return f"{old_status}->{result.status}"
    return None


def get_health_state() -> dict[str, dict]:
    """Return the current in-memory health state for all services."""
    return _health_state


def record_check(conn: sqlite3.Connection, result: CheckResult) -> str | None:
    """Record a health check and detect state transitions.

    Always updates in-memory state. DB write is best-effort — if SQLite is
    locked, the in-memory state still reflects reality so /api/status stays
    accurate.

    Returns transition string (e.g. "up->down") if state changed, None otherwise.
    """
    # Always update in-memory state first
    transition = _update_memory_state(result)

    try:
        # Insert check record
        conn.execute(
            "INSERT INTO service_checks "
            "(service_name, status, response_time_ms, error_message, checked_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                result.service_name,
                result.status,
                result.response_time_ms,
                result.error_message,
                result.checked_at,
            ),
        )

        # Get current state from DB
        row = conn.execute(
            "SELECT current_status, consecutive_failures FROM service_state WHERE service_name = ?",
            (result.service_name,),
        ).fetchone()

        mem = _health_state[result.service_name]

        if row is None:
            conn.execute(
                "INSERT INTO service_state "
                "(service_name, current_status, last_change_at, "
                "consecutive_failures, last_checked_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    result.service_name,
                    result.status,
                    result.checked_at,
                    mem["consecutive_failures"],
                    result.checked_at,
                ),
            )
        elif transition:
            conn.execute(
                "UPDATE service_state SET current_status = ?, last_change_at = ?, "
                "consecutive_failures = ?, last_checked_at = ? WHERE service_name = ?",
                (
                    result.status,
                    result.checked_at,
                    mem["consecutive_failures"],
                    result.checked_at,
                    result.service_name,
                ),
            )
        else:
            conn.execute(
                "UPDATE service_state "
                "SET consecutive_failures = ?, last_checked_at = ? "
                "WHERE service_name = ?",
                (mem["consecutive_failures"], result.checked_at, result.service_name),
            )
        conn.commit()
    except sqlite3.OperationalError:
        logger.warning(
            "DB locked — health state for %s updated in memory only (%s)",
            result.service_name,
            result.status,
        )

    return transition

"""Tests for service health checker."""

import time

import httpx
import pytest
import respx

from backend.alerts.service_health import (
    CheckResult,
    check_detection_errors,
    check_event_lag,
    check_loop_health,
    check_sui_rpc,
    check_watchtower,
    check_world_api,
    record_check,
)

# --- External check tests ---


@pytest.mark.asyncio
async def test_world_api_up():
    """World API returns up when healthy."""
    with respx.mock:
        respx.get("https://example.com/config").respond(200, json={"ok": True})
        async with httpx.AsyncClient() as client:
            result = await check_world_api(client, "https://example.com", timeout=5)
    assert result.service_name == "world_api"
    assert result.status == "up"
    assert result.error_message is None


@pytest.mark.asyncio
async def test_world_api_down_on_error():
    """World API returns down on HTTP error."""
    with respx.mock:
        respx.get("https://example.com/config").respond(500)
        async with httpx.AsyncClient() as client:
            result = await check_world_api(client, "https://example.com", timeout=5)
    assert result.status == "down"
    assert "500" in result.error_message


@pytest.mark.asyncio
async def test_world_api_down_on_timeout():
    """World API returns down on connection failure."""
    with respx.mock:
        respx.get("https://example.com/config").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        async with httpx.AsyncClient() as client:
            result = await check_world_api(client, "https://example.com", timeout=1)
    assert result.status == "down"
    assert "refused" in result.error_message.lower()


@pytest.mark.asyncio
async def test_sui_rpc_up():
    """Sui RPC returns up when healthy."""
    with respx.mock:
        respx.post("https://rpc.example.com").respond(
            200, json={"jsonrpc": "2.0", "result": "12345"}
        )
        async with httpx.AsyncClient() as client:
            result = await check_sui_rpc(client, "https://rpc.example.com", timeout=5)
    assert result.status == "up"


@pytest.mark.asyncio
async def test_sui_rpc_down_no_result():
    """Sui RPC returns down when result missing."""
    with respx.mock:
        respx.post("https://rpc.example.com").respond(
            200, json={"jsonrpc": "2.0", "error": {"code": -32000}}
        )
        async with httpx.AsyncClient() as client:
            result = await check_sui_rpc(client, "https://rpc.example.com", timeout=5)
    assert result.status == "down"


@pytest.mark.asyncio
async def test_watchtower_up():
    """WatchTower returns up when healthy."""
    with respx.mock:
        respx.get("https://wt.example.com/health").respond(200, json={"status": "ok"})
        async with httpx.AsyncClient() as client:
            result = await check_watchtower(client, "https://wt.example.com", timeout=5)
    assert result.status == "up"


@pytest.mark.asyncio
async def test_watchtower_down():
    """WatchTower returns down on failure."""
    with respx.mock:
        respx.get("https://wt.example.com/health").respond(503)
        async with httpx.AsyncClient() as client:
            result = await check_watchtower(client, "https://wt.example.com", timeout=5)
    assert result.status == "down"


# --- Internal check tests ---


def test_loop_health_all_ok():
    """All loops report up when heartbeats are recent."""
    now = time.time()
    heartbeats = {"chain_poll": now - 10, "detection": now - 100}
    expected = {"chain_poll": 30, "detection": 300}
    results = check_loop_health(heartbeats, expected)
    assert all(r.status == "up" for r in results)


def test_loop_health_stalled():
    """Loop reports degraded when heartbeat exceeds threshold."""
    now = time.time()
    heartbeats = {"chain_poll": now - 100}  # 100s old, threshold is 30*2=60
    expected = {"chain_poll": 30}
    results = check_loop_health(heartbeats, expected)
    assert results[0].status == "degraded"


def test_loop_health_down():
    """Loop reports down when heartbeat exceeds 2x threshold."""
    now = time.time()
    heartbeats = {"chain_poll": now - 200}  # 200s old, threshold*2 is 30*4=120
    expected = {"chain_poll": 30}
    results = check_loop_health(heartbeats, expected)
    assert results[0].status == "down"


def test_loop_health_no_heartbeat():
    """Loop reports up (waiting) when no heartbeat yet."""
    heartbeats = {}
    expected = {"chain_poll": 30}
    results = check_loop_health(heartbeats, expected)
    assert results[0].status == "up"
    assert "first heartbeat" in results[0].error_message.lower()


def test_event_lag_ok(db_conn):
    """Event lag reports up when no unprocessed events."""
    result = check_event_lag(db_conn)
    assert result.status == "up"


def test_event_lag_degraded(db_conn):
    """Event lag reports degraded above 1000 unprocessed."""
    for i in range(1100):
        db_conn.execute(
            "INSERT INTO chain_events (event_id, event_type, processed) VALUES (?, 'test', 0)",
            (f"evt-{i}",),
        )
    db_conn.commit()
    result = check_event_lag(db_conn)
    assert result.status == "degraded"


def test_event_lag_down(db_conn):
    """Event lag reports down above 5000 unprocessed."""
    for i in range(5100):
        db_conn.execute(
            "INSERT INTO chain_events (event_id, event_type, processed) VALUES (?, 'test', 0)",
            (f"evt-{i}",),
        )
    db_conn.commit()
    result = check_event_lag(db_conn)
    assert result.status == "down"


def test_detection_errors_ok(db_conn):
    """Detection health up when no errors."""
    for i in range(10):
        db_conn.execute(
            "INSERT INTO detection_cycles (started_at, finished_at, error) VALUES (?, ?, NULL)",
            (float(i), float(i + 1)),
        )
    db_conn.commit()
    result = check_detection_errors(db_conn)
    assert result.status == "up"


def test_detection_errors_degraded(db_conn):
    """Detection health degraded when >50% cycles fail."""
    for i in range(10):
        error = "boom" if i < 6 else None
        db_conn.execute(
            "INSERT INTO detection_cycles (started_at, finished_at, error) VALUES (?, ?, ?)",
            (float(i), float(i + 1), error),
        )
    db_conn.commit()
    result = check_detection_errors(db_conn)
    assert result.status == "degraded"


def test_detection_errors_down(db_conn):
    """Detection health down when >80% cycles fail."""
    for i in range(10):
        error = "boom" if i < 9 else None
        db_conn.execute(
            "INSERT INTO detection_cycles (started_at, finished_at, error) VALUES (?, ?, ?)",
            (float(i), float(i + 1), error),
        )
    db_conn.commit()
    result = check_detection_errors(db_conn)
    assert result.status == "down"


# --- State transition tests ---


def test_record_check_first(db_conn):
    """First check initializes state, no transition alert."""
    result = CheckResult("world_api", "up", 150, None, int(time.time()))
    transition = record_check(db_conn, result)
    assert transition is None
    row = db_conn.execute("SELECT * FROM service_state WHERE service_name = 'world_api'").fetchone()
    assert row["current_status"] == "up"


def test_record_check_transition(db_conn):
    """State change produces transition string."""
    now = int(time.time())
    # Initialize
    record_check(db_conn, CheckResult("sui_rpc", "up", 100, None, now))
    # Transition
    transition = record_check(db_conn, CheckResult("sui_rpc", "down", 0, "timeout", now + 60))
    assert transition == "up->down"


def test_record_check_no_transition(db_conn):
    """Same status produces no transition."""
    now = int(time.time())
    record_check(db_conn, CheckResult("sui_rpc", "up", 100, None, now))
    transition = record_check(db_conn, CheckResult("sui_rpc", "up", 120, None, now + 60))
    assert transition is None


def test_record_check_consecutive_failures(db_conn):
    """Consecutive failures increment on non-up status."""
    now = int(time.time())
    record_check(db_conn, CheckResult("wt", "up", 100, None, now))
    record_check(db_conn, CheckResult("wt", "down", 0, "err", now + 60))
    record_check(db_conn, CheckResult("wt", "down", 0, "err", now + 120))
    row = db_conn.execute(
        "SELECT consecutive_failures FROM service_state WHERE service_name = 'wt'"
    ).fetchone()
    assert row["consecutive_failures"] == 2


def test_record_check_failure_reset(db_conn):
    """Consecutive failures reset on recovery."""
    now = int(time.time())
    record_check(db_conn, CheckResult("wt", "up", 100, None, now))
    record_check(db_conn, CheckResult("wt", "down", 0, "err", now + 60))
    record_check(db_conn, CheckResult("wt", "down", 0, "err", now + 120))
    record_check(db_conn, CheckResult("wt", "up", 90, None, now + 180))
    row = db_conn.execute(
        "SELECT consecutive_failures FROM service_state WHERE service_name = 'wt'"
    ).fetchone()
    assert row["consecutive_failures"] == 0


def test_service_checks_history(db_conn):
    """Check records are persisted."""
    now = int(time.time())
    for i in range(5):
        record_check(db_conn, CheckResult("test_svc", "up", 100 + i, None, now + i))
    rows = db_conn.execute(
        "SELECT COUNT(*) FROM service_checks WHERE service_name = 'test_svc'"
    ).fetchone()
    assert rows[0] == 5

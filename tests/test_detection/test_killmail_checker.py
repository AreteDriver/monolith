"""Tests for killmail reconciliation checker (K1, K2 rules)."""

import json
import time

import httpx
import pytest
import respx

from backend.db.database import init_db
from backend.detection.killmail_checker import (
    LOOKBACK_SECONDS,
    KillmailChecker,
)


@pytest.fixture
def db_conn():
    """In-memory SQLite database with full schema."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


WORLD_API_URL = "https://world-api-stillness.live.tech.evefrontier.com"


def _insert_chain_kill(conn, event_id, victim_id, killer_id, ts, killmail_id=""):
    """Insert a KillmailCreatedEvent into chain_events."""
    parsed = {
        "parsedJson": {
            "victim_id": victim_id,
            "killer_id": killer_id,
        }
    }
    if killmail_id:
        parsed["parsedJson"]["killmail_id"] = killmail_id
    conn.execute(
        "INSERT INTO chain_events "
        "(event_id, event_type, object_id, timestamp, raw_json, processed) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (event_id, "KillmailCreatedEvent", victim_id, ts, json.dumps(parsed)),
    )
    conn.commit()


def _make_world_kill(killmail_id="", victim_id="", killer_id="", timestamp=0):
    """Build a World API killmail dict."""
    kill = {}
    if killmail_id:
        kill["killmail_id"] = killmail_id
    if victim_id:
        kill["victim"] = {"id": victim_id}
    if killer_id:
        kill["killer"] = {"id": killer_id}
    if timestamp:
        kill["timestamp"] = timestamp
    return kill


@pytest.mark.asyncio
@respx.mock
async def test_k1_missing_chain_kill(db_conn):
    """K1: World API kill with no chain event flagged as MISSING_CHAIN_KILL."""
    now = int(time.time())
    world_kills = [_make_world_kill("km-001", "victim-a", "killer-b", now)]

    respx.get(f"{WORLD_API_URL}/v2/killmails?limit=100").respond(
        200, json={"data": world_kills, "metadata": {}}
    )

    async with httpx.AsyncClient() as client:
        checker = KillmailChecker(db_conn, client, WORLD_API_URL)
        anomalies = await checker.run_async()

    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.anomaly_type == "MISSING_CHAIN_KILL"
    assert a.rule_id == "K1"
    assert a.severity == "HIGH"
    assert a.category == "DATA_INTEGRITY"
    assert "km-001" in a.object_id


@pytest.mark.asyncio
@respx.mock
async def test_k2_chain_only_kill(db_conn):
    """K2: Chain kill with no World API match flagged as CHAIN_ONLY_KILL."""
    now = int(time.time())
    _insert_chain_kill(db_conn, "evt-001", "victim-x", "killer-y", now, "km-999")

    # World API returns empty
    respx.get(f"{WORLD_API_URL}/v2/killmails?limit=100").respond(
        200, json={"data": [], "metadata": {}}
    )

    async with httpx.AsyncClient() as client:
        checker = KillmailChecker(db_conn, client, WORLD_API_URL)
        anomalies = await checker.run_async()

    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.anomaly_type == "CHAIN_ONLY_KILL"
    assert a.rule_id == "K2"
    assert a.severity == "MEDIUM"
    assert a.category == "DATA_INTEGRITY"


@pytest.mark.asyncio
@respx.mock
async def test_match_by_killmail_id(db_conn):
    """Kills that match by killmail_id produce no anomalies."""
    now = int(time.time())
    _insert_chain_kill(db_conn, "evt-001", "victim-a", "killer-b", now, "km-001")

    world_kills = [_make_world_kill("km-001", "victim-a", "killer-b", now)]
    respx.get(f"{WORLD_API_URL}/v2/killmails?limit=100").respond(
        200, json={"data": world_kills, "metadata": {}}
    )

    async with httpx.AsyncClient() as client:
        checker = KillmailChecker(db_conn, client, WORLD_API_URL)
        anomalies = await checker.run_async()

    assert len(anomalies) == 0


@pytest.mark.asyncio
@respx.mock
async def test_match_by_victim_and_timestamp(db_conn):
    """Kills that match by victim_id + close timestamp produce no anomalies."""
    now = int(time.time())
    # Chain kill 30 seconds before World API timestamp — within window
    _insert_chain_kill(db_conn, "evt-002", "victim-a", "killer-b", now - 30)

    world_kills = [_make_world_kill("", "victim-a", "killer-b", now)]
    respx.get(f"{WORLD_API_URL}/v2/killmails?limit=100").respond(
        200, json={"data": world_kills, "metadata": {}}
    )

    async with httpx.AsyncClient() as client:
        checker = KillmailChecker(db_conn, client, WORLD_API_URL)
        anomalies = await checker.run_async()

    assert len(anomalies) == 0


@pytest.mark.asyncio
@respx.mock
async def test_no_match_outside_time_window(db_conn):
    """Kills with same victim but timestamp outside window are NOT matched."""
    now = int(time.time())
    # Chain kill 120 seconds before — outside the 60s match window
    _insert_chain_kill(db_conn, "evt-003", "victim-a", "killer-b", now - 120)

    world_kills = [_make_world_kill("", "victim-a", "killer-b", now)]
    respx.get(f"{WORLD_API_URL}/v2/killmails?limit=100").respond(
        200, json={"data": world_kills, "metadata": {}}
    )

    async with httpx.AsyncClient() as client:
        checker = KillmailChecker(db_conn, client, WORLD_API_URL)
        anomalies = await checker.run_async()

    # K1 for the unmatched world kill, K2 for the unmatched chain kill
    types = {a.anomaly_type for a in anomalies}
    assert "MISSING_CHAIN_KILL" in types
    assert "CHAIN_ONLY_KILL" in types


@pytest.mark.asyncio
@respx.mock
async def test_world_api_error_returns_empty(db_conn):
    """World API failure returns no anomalies (doesn't crash)."""
    respx.get(f"{WORLD_API_URL}/v2/killmails?limit=100").respond(500)

    async with httpx.AsyncClient() as client:
        checker = KillmailChecker(db_conn, client, WORLD_API_URL)
        anomalies = await checker.run_async()

    assert anomalies == []


@pytest.mark.asyncio
@respx.mock
async def test_old_chain_kills_excluded(db_conn):
    """Chain kills older than LOOKBACK_SECONDS are not checked."""
    old_ts = int(time.time()) - LOOKBACK_SECONDS - 3600
    _insert_chain_kill(db_conn, "evt-old", "victim-old", "killer-old", old_ts)

    respx.get(f"{WORLD_API_URL}/v2/killmails?limit=100").respond(
        200, json={"data": [], "metadata": {}}
    )

    async with httpx.AsyncClient() as client:
        checker = KillmailChecker(db_conn, client, WORLD_API_URL)
        anomalies = await checker.run_async()

    # Old chain kill should not produce K2
    assert len(anomalies) == 0


@pytest.mark.asyncio
@respx.mock
async def test_world_api_flat_list_response(db_conn):
    """Handle World API returning a flat list instead of wrapped format."""
    now = int(time.time())
    world_kills = [_make_world_kill("km-flat", "victim-f", "killer-g", now)]

    respx.get(f"{WORLD_API_URL}/v2/killmails?limit=100").respond(200, json=world_kills)

    async with httpx.AsyncClient() as client:
        checker = KillmailChecker(db_conn, client, WORLD_API_URL)
        anomalies = await checker.run_async()

    assert len(anomalies) == 1
    assert anomalies[0].anomaly_type == "MISSING_CHAIN_KILL"


def test_sync_check_raises(db_conn):
    """check() raises NotImplementedError — async only."""
    checker = KillmailChecker(db_conn, None, WORLD_API_URL)
    with pytest.raises(NotImplementedError):
        checker.check()


@pytest.mark.asyncio
@respx.mock
async def test_camel_case_chain_fields(db_conn):
    """Chain events with camelCase parsedJson keys are matched correctly."""
    now = int(time.time())
    # Insert with camelCase keys
    parsed = {
        "parsedJson": {"victimId": "victim-cc", "killerId": "killer-cc", "killmailId": "km-cc"},
    }
    db_conn.execute(
        "INSERT INTO chain_events "
        "(event_id, event_type, object_id, timestamp, raw_json, processed) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        ("evt-cc", "KillmailCreatedEvent", "victim-cc", now, json.dumps(parsed)),
    )
    db_conn.commit()

    world_kills = [_make_world_kill("km-cc", "victim-cc", "killer-cc", now)]
    respx.get(f"{WORLD_API_URL}/v2/killmails?limit=100").respond(
        200, json={"data": world_kills, "metadata": {}}
    )

    async with httpx.AsyncClient() as client:
        checker = KillmailChecker(db_conn, client, WORLD_API_URL)
        anomalies = await checker.run_async()

    assert len(anomalies) == 0


@pytest.mark.asyncio
@respx.mock
async def test_multiple_kills_mixed(db_conn):
    """Multiple kills: some matched, some not — correct anomaly counts."""
    now = int(time.time())

    # Matched kill (by killmail_id)
    _insert_chain_kill(db_conn, "evt-m1", "v1", "k1", now, "km-matched")

    # Chain-only kill (no world match)
    _insert_chain_kill(db_conn, "evt-m2", "v2", "k2", now, "km-chain-only")

    world_kills = [
        _make_world_kill("km-matched", "v1", "k1", now),
        _make_world_kill("km-world-only", "v3", "k3", now),  # World-only
    ]
    respx.get(f"{WORLD_API_URL}/v2/killmails?limit=100").respond(
        200, json={"data": world_kills, "metadata": {}}
    )

    async with httpx.AsyncClient() as client:
        checker = KillmailChecker(db_conn, client, WORLD_API_URL)
        anomalies = await checker.run_async()

    types = [a.anomaly_type for a in anomalies]
    assert types.count("MISSING_CHAIN_KILL") == 1  # km-world-only
    assert types.count("CHAIN_ONLY_KILL") == 1  # km-chain-only

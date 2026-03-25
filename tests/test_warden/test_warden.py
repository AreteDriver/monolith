"""Tests for Warden autonomous threat verification."""

import time

import pytest

from backend.db.database import init_db
from backend.warden.warden import Warden


@pytest.fixture
def conn():
    """Fresh in-memory DB for Warden tests."""
    c = init_db(":memory:")
    yield c
    c.close()


def _seed_anomaly(conn, anomaly_id, rule_id="C1", object_id="0xabc", status="UNVERIFIED"):
    """Insert a test anomaly."""
    conn.execute(
        "INSERT INTO anomalies "
        "(anomaly_id, anomaly_type, severity, category, detector, "
        "rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, 'TEST', 'CRITICAL', 'DATA_INTEGRITY', 'test', "
        "?, ?, 'sys-1', ?, '{}', ?)",
        (anomaly_id, rule_id, object_id, int(time.time()), status),
    )
    conn.commit()


@pytest.mark.asyncio
async def test_warden_idle_no_anomalies(conn):
    """Warden returns idle when no unverified anomalies."""
    warden = Warden(conn, "https://fake-rpc.example.com")
    result = await warden.run_cycle()
    assert result["status"] == "idle"


@pytest.mark.asyncio
async def test_warden_max_cycles_pauses(conn):
    """Warden pauses after max_cycles."""
    warden = Warden(conn, "https://fake-rpc.example.com", max_cycles=2)
    warden.cycles_run = 2
    result = await warden.run_cycle()
    assert result["status"] == "paused"


@pytest.mark.asyncio
async def test_warden_chain_unreachable(conn, respx_mock):
    """Warden skips cycle when chain is unreachable."""
    rpc_url = "https://fake-rpc.example.com"
    respx_mock.post(rpc_url).respond(500, text="down")

    _seed_anomaly(conn, "MNLT-TEST-001")

    warden = Warden(conn, rpc_url)
    result = await warden.run_cycle()
    assert result["status"] == "chain_unreachable"


@pytest.mark.asyncio
async def test_warden_verifies_c1(conn, respx_mock):
    """Warden verifies C1 (Ghost Signal) when object exists on chain."""
    rpc_url = "https://fake-rpc.example.com"

    # First call: checkpoint check (returns valid)
    # Second call: sui_getObject for C1 verification
    respx_mock.post(rpc_url).mock(
        side_effect=[
            # Checkpoint check
            _json_response({"jsonrpc": "2.0", "id": 1, "result": "99999"}),
            # Object exists
            _json_response({"jsonrpc": "2.0", "id": 1, "result": {"data": {"objectId": "0xabc"}}}),
        ]
    )

    _seed_anomaly(conn, "MNLT-TEST-C1", rule_id="C1", object_id="0xabc")

    warden = Warden(conn, rpc_url)
    result = await warden.run_cycle()
    assert result["verified"] == 1

    # Check DB was updated
    row = conn.execute("SELECT status FROM anomalies WHERE anomaly_id = 'MNLT-TEST-C1'").fetchone()
    assert row["status"] == "VERIFIED"


@pytest.mark.asyncio
async def test_warden_dismisses_c1_missing(conn, respx_mock):
    """Warden dismisses C1 when object doesn't exist on chain."""
    rpc_url = "https://fake-rpc.example.com"

    respx_mock.post(rpc_url).mock(
        side_effect=[
            # Checkpoint
            _json_response({"jsonrpc": "2.0", "id": 1, "result": "99999"}),
            # Object not found
            _json_response({"jsonrpc": "2.0", "id": 1, "result": {"error": {"code": "notExists"}}}),
        ]
    )

    _seed_anomaly(conn, "MNLT-TEST-C1-MISS", rule_id="C1", object_id="0xgone")

    warden = Warden(conn, rpc_url)
    result = await warden.run_cycle()
    assert result["dismissed"] == 1

    row = conn.execute(
        "SELECT status FROM anomalies WHERE anomaly_id = 'MNLT-TEST-C1-MISS'"
    ).fetchone()
    assert row["status"] == "DISMISSED"


def test_warden_reset_cycles(conn):
    """reset_cycles resets the counter."""
    warden = Warden(conn, "https://fake-rpc.example.com")
    warden.cycles_run = 10
    warden.reset_cycles()
    assert warden.cycles_run == 0


def _json_response(data):
    """Create an httpx Response for respx mocking."""
    import httpx

    return httpx.Response(200, json=data)

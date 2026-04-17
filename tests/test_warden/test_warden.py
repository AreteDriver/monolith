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


@pytest.mark.asyncio
async def test_warden_verifies_c2_lazarus(conn, respx_mock):
    """Warden verifies C2 (Lazarus) when destroyed object still exists."""
    rpc_url = "https://fake-rpc.example.com"

    respx_mock.post(rpc_url).mock(
        side_effect=[
            _json_response({"jsonrpc": "2.0", "id": 1, "result": "99999"}),
            _json_response(
                {"jsonrpc": "2.0", "id": 1, "result": {"data": {"objectId": "0xzombie"}}}
            ),
        ]
    )

    _seed_anomaly(conn, "MNLT-TEST-C2", rule_id="C2", object_id="0xzombie")

    warden = Warden(conn, rpc_url)
    result = await warden.run_cycle()
    assert result["verified"] == 1

    row = conn.execute("SELECT status FROM anomalies WHERE anomaly_id = 'MNLT-TEST-C2'").fetchone()
    assert row["status"] == "VERIFIED"


@pytest.mark.asyncio
async def test_warden_a1_state_divergence(conn, respx_mock):
    """Warden verifies A1 (Forked State) when chain state exists."""
    rpc_url = "https://fake-rpc.example.com"

    respx_mock.post(rpc_url).mock(
        side_effect=[
            _json_response({"jsonrpc": "2.0", "id": 1, "result": "99999"}),
            _json_response({
                "jsonrpc": "2.0", "id": 1,
                "result": {"data": {"content": {"fields": {"state": "ONLINE"}}}},
            }),
        ]
    )

    _seed_anomaly(conn, "MNLT-TEST-A1", rule_id="A1", object_id="0xforked")

    warden = Warden(conn, rpc_url)
    result = await warden.run_cycle()
    assert result["verified"] == 1


@pytest.mark.asyncio
async def test_warden_default_rule_keeps_verified(conn, respx_mock):
    """Warden keeps anomalies as VERIFIED for unknown rules (cannot disprove)."""
    rpc_url = "https://fake-rpc.example.com"

    respx_mock.post(rpc_url).mock(
        side_effect=[
            _json_response({"jsonrpc": "2.0", "id": 1, "result": "99999"}),
        ]
    )

    _seed_anomaly(conn, "MNLT-TEST-E1", rule_id="E1", object_id="0xeconomic")

    warden = Warden(conn, rpc_url)
    result = await warden.run_cycle()
    assert result["verified"] == 1

    row = conn.execute("SELECT status FROM anomalies WHERE anomaly_id = 'MNLT-TEST-E1'").fetchone()
    assert row["status"] == "VERIFIED"


@pytest.mark.asyncio
async def test_warden_error_in_verification(conn, respx_mock):
    """Warden counts errors when verification raises an unexpected exception."""
    from unittest.mock import AsyncMock, patch

    rpc_url = "https://fake-rpc.example.com"

    respx_mock.post(rpc_url).mock(
        side_effect=[
            _json_response({"jsonrpc": "2.0", "id": 1, "result": "99999"}),
        ]
    )

    _seed_anomaly(conn, "MNLT-TEST-ERR", rule_id="C1", object_id="0xerr")

    warden = Warden(conn, rpc_url)
    # Patch _verify_anomaly to raise an unexpected error
    with patch.object(warden, "_verify_anomaly", new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = await warden.run_cycle()
    assert result["errors"] == 1


def test_warden_append_provenance(conn):
    """_append_provenance adds to existing provenance chain."""
    import json

    _seed_anomaly(conn, "MNLT-PROV-1")
    # Set initial provenance
    conn.execute(
        "UPDATE anomalies SET provenance_json = ? WHERE anomaly_id = 'MNLT-PROV-1'",
        (json.dumps([{"source_type": "initial", "source_id": "test",
                       "timestamp": 0, "derivation": "seed"}]),),
    )
    conn.commit()

    warden = Warden(conn, "https://fake")
    warden._append_provenance("MNLT-PROV-1", "sui_rpc", "checkpoint:1000", "test derivation")

    row = conn.execute(
        "SELECT provenance_json FROM anomalies WHERE anomaly_id = 'MNLT-PROV-1'"
    ).fetchone()
    prov = json.loads(row["provenance_json"])
    assert len(prov) == 2
    assert prov[1]["source_type"] == "sui_rpc"


def test_warden_append_provenance_bad_existing_json(conn):
    """_append_provenance handles corrupt existing provenance gracefully."""
    _seed_anomaly(conn, "MNLT-PROV-BAD")
    conn.execute(
        "UPDATE anomalies SET provenance_json = 'not json' WHERE anomaly_id = 'MNLT-PROV-BAD'"
    )
    conn.commit()

    warden = Warden(conn, "https://fake")
    warden._append_provenance("MNLT-PROV-BAD", "sui_rpc", "cp:1", "test")

    row = conn.execute(
        "SELECT provenance_json FROM anomalies WHERE anomaly_id = 'MNLT-PROV-BAD'"
    ).fetchone()
    import json

    prov = json.loads(row["provenance_json"])
    assert len(prov) == 1  # Only the new entry (old was unparseable)


def test_warden_append_provenance_nonexistent_anomaly(conn):
    """_append_provenance does nothing for non-existent anomaly."""
    warden = Warden(conn, "https://fake")
    # Should not raise
    warden._append_provenance("NONEXISTENT", "sui_rpc", "cp:1", "test")


def test_warden_get_unverified_empty_object_id(conn):
    """_get_unverified_anomalies excludes anomalies with empty object_id."""
    conn.execute(
        "INSERT INTO anomalies "
        "(anomaly_id, anomaly_type, severity, category, detector, "
        "rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, 'TEST', 'CRITICAL', 'DATA_INTEGRITY', 'test', "
        "'C1', '', 'sys-1', ?, '{}', 'UNVERIFIED')",
        ("MNLT-EMPTY-OBJ", int(time.time())),
    )
    conn.commit()

    warden = Warden(conn, "https://fake")
    unverified = warden._get_unverified_anomalies()
    assert len(unverified) == 0


def _json_response(data):
    """Create an httpx Response for respx mocking."""
    from httpx import Response

    return Response(200, json=data)

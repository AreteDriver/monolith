"""Tests for POD checker — P1 chain state verification."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.detection.pod_checker import PodChecker, _nested_get


def _seed_object_with_snapshot(conn, obj_id, state_data, system_id=""):
    """Insert an object + world state snapshot for POD checking."""
    now = int(time.time())
    conn.execute(
        "INSERT INTO objects (object_id, object_type, system_id, last_seen) "
        "VALUES (?, 'smartassemblies', ?, ?)",
        (obj_id, system_id, now),
    )
    conn.execute(
        "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
        "VALUES (?, 'smartassemblies', ?, ?, 'chain')",
        (obj_id, json.dumps(state_data), now),
    )
    conn.commit()


def test_check_raises_not_implemented(db_conn):
    """PodChecker.check() must raise — it requires async."""
    checker = PodChecker(db_conn)
    with pytest.raises(NotImplementedError, match="async"):
        checker.check()


@pytest.mark.asyncio
async def test_p1_no_objects(db_conn):
    """P1: No objects to check → no anomalies."""
    checker = PodChecker(db_conn)
    client = AsyncMock(spec=httpx.AsyncClient)
    result = await checker.run_async(client)
    assert result == []


@pytest.mark.asyncio
async def test_p1_matching_state(db_conn):
    """P1: Local state matches chain → no anomaly."""
    obj_id = "0xabc123"
    _seed_object_with_snapshot(db_conn, obj_id, {"owner": {"address": "0xowner1"}, "state": "ONLINE"})

    chain_response = {
        "data": {
            "object": {
                "address": obj_id,
                "version": 5,
                "owner": {"owner": {"address": "0xowner1"}},
                "asMoveObject": {
                    "contents": {
                        "json": json.dumps({"state": "ONLINE"}),
                    }
                },
            }
        }
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = chain_response
    mock_resp.raise_for_status = MagicMock()

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp

    checker = PodChecker(db_conn)
    result = await checker.run_async(client)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_p1_owner_mismatch(db_conn):
    """P1: Owner differs between local and chain → CRITICAL anomaly."""
    obj_id = "0xdef456"
    _seed_object_with_snapshot(db_conn, obj_id, {"owner": {"address": "0xowner_local"}})

    chain_response = {
        "data": {
            "object": {
                "address": obj_id,
                "version": 10,
                "owner": {"owner": {"address": "0xowner_chain"}},
                "asMoveObject": {"contents": {"json": "{}"}},
            }
        }
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = chain_response
    mock_resp.raise_for_status = MagicMock()

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp

    checker = PodChecker(db_conn)
    result = await checker.run_async(client)
    assert len(result) == 1
    assert result[0].anomaly_type == "CHAIN_STATE_MISMATCH"
    assert result[0].rule_id == "P1"
    assert "owner" in result[0].evidence["mismatches"]


@pytest.mark.asyncio
async def test_p1_state_mismatch(db_conn):
    """P1: State field differs → CRITICAL anomaly."""
    obj_id = "0xghi789"
    _seed_object_with_snapshot(db_conn, obj_id, {"state": "ONLINE"})

    chain_response = {
        "data": {
            "object": {
                "address": obj_id,
                "version": 3,
                "owner": {},
                "asMoveObject": {
                    "contents": {"json": json.dumps({"state": "OFFLINE"})}
                },
            }
        }
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = chain_response
    mock_resp.raise_for_status = MagicMock()

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp

    checker = PodChecker(db_conn)
    result = await checker.run_async(client)
    assert len(result) == 1
    assert "state" in result[0].evidence["mismatches"]


@pytest.mark.asyncio
async def test_p1_graphql_error(db_conn):
    """P1: GraphQL returns error → skip, no anomaly."""
    obj_id = "0xerr001"
    _seed_object_with_snapshot(db_conn, obj_id, {"state": "ONLINE"})

    chain_response = {"errors": [{"message": "Object not found"}]}

    mock_resp = MagicMock()
    mock_resp.json.return_value = chain_response
    mock_resp.raise_for_status = MagicMock()

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp

    checker = PodChecker(db_conn)
    result = await checker.run_async(client)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_p1_http_error(db_conn):
    """P1: HTTP error → skip, no anomaly."""
    obj_id = "0xerr002"
    _seed_object_with_snapshot(db_conn, obj_id, {"state": "ONLINE"})

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = httpx.ConnectError("Connection refused")

    checker = PodChecker(db_conn)
    result = await checker.run_async(client)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_p1_creates_own_client(db_conn):
    """P1: run_async without client creates its own."""
    checker = PodChecker(db_conn)
    # No objects → should return empty without error
    with patch("backend.detection.pod_checker.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await checker.run_async()
        assert result == []


def test_nested_get():
    """_nested_get traverses nested dicts safely."""
    d = {"a": {"b": {"c": 42}}}
    assert _nested_get(d, "a", "b", "c") == 42
    assert _nested_get(d, "a", "b", "missing") is None
    assert _nested_get(d, "x") is None
    assert _nested_get({}, "a") is None


def test_nested_get_non_dict():
    """_nested_get handles non-dict intermediates."""
    assert _nested_get({"a": "string"}, "a", "b") is None
    assert _nested_get({"a": None}, "a", "b") is None


def test_compare_with_chain_fuel_mismatch():
    """_compare_with_chain detects fuel amount differences."""
    local = {"networkNode": {"fuel": {"amount": 1000}}}
    chain_obj = {
        "owner": {},
        "asMoveObject": {
            "contents": {
                "json": json.dumps({"networkNode": {"fuel": {"amount": 500}}})
            }
        },
    }
    mismatches = PodChecker._compare_with_chain(local, chain_obj)
    assert "fuel" in mismatches
    assert mismatches["fuel"]["local"] == 1000
    assert mismatches["fuel"]["chain"] == 500

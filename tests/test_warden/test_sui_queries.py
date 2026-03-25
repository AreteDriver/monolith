"""Tests for Warden Sui read-only queries."""

import pytest

from backend.warden.sui_queries import (
    _rpc_call,
    get_latest_checkpoint,
    get_object_state,
    verify_object_exists,
)


@pytest.mark.asyncio
async def test_get_object_state_success(respx_mock):
    """Successful object fetch returns parsed result."""
    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "data": {
                    "objectId": "0xabc",
                    "content": {"type": "test::Object", "fields": {"value": 42}},
                }
            },
        },
    )

    result = await get_object_state(rpc_url, "0xabc")
    assert result is not None
    assert result["data"]["objectId"] == "0xabc"


@pytest.mark.asyncio
async def test_get_object_state_error(respx_mock):
    """RPC error returns None."""
    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(500, text="Internal Server Error")

    result = await get_object_state(rpc_url, "0xbad")
    assert result is None


@pytest.mark.asyncio
async def test_verify_object_exists_true(respx_mock):
    """Existing object returns True."""
    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(
        200,
        json={"jsonrpc": "2.0", "id": 1, "result": {"data": {"objectId": "0xexist"}}},
    )

    assert await verify_object_exists(rpc_url, "0xexist") is True


@pytest.mark.asyncio
async def test_verify_object_exists_not_found(respx_mock):
    """Non-existent object returns False."""
    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(
        200,
        json={"jsonrpc": "2.0", "id": 1, "result": {"error": {"code": "notExists"}}},
    )

    # Result contains error key → should return False
    assert await verify_object_exists(rpc_url, "0xghost") is False


@pytest.mark.asyncio
async def test_get_latest_checkpoint(respx_mock):
    """Checkpoint query returns integer."""
    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(
        200,
        json={"jsonrpc": "2.0", "id": 1, "result": "12345"},
    )

    cp = await get_latest_checkpoint(rpc_url)
    assert cp == 12345


@pytest.mark.asyncio
async def test_get_latest_checkpoint_failure(respx_mock):
    """Checkpoint failure returns 0."""
    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(500, text="down")

    cp = await get_latest_checkpoint(rpc_url)
    assert cp == 0


@pytest.mark.asyncio
async def test_rpc_call_network_error(respx_mock):
    """Network error returns None gracefully."""
    import httpx

    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).mock(side_effect=httpx.ConnectError("refused"))

    result = await _rpc_call(rpc_url, {"jsonrpc": "2.0", "id": 1, "method": "test", "params": []})
    assert result is None

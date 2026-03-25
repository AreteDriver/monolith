"""Additional tests for Warden Sui queries — coverage push."""

import pytest

from backend.warden.sui_queries import get_dynamic_fields, get_object_events


@pytest.mark.asyncio
async def test_get_object_events_success(respx_mock):
    """Object events query returns list."""
    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"data": [{"id": "evt-1"}, {"id": "evt-2"}]},
        },
    )

    events = await get_object_events(rpc_url, "0xabc")
    assert len(events) == 2


@pytest.mark.asyncio
async def test_get_object_events_empty(respx_mock):
    """Object events returns empty list on error."""
    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(500, text="down")

    events = await get_object_events(rpc_url, "0xabc")
    assert events == []


@pytest.mark.asyncio
async def test_get_dynamic_fields_success(respx_mock):
    """Dynamic fields query returns list."""
    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"data": [{"name": "field1"}]},
        },
    )

    fields = await get_dynamic_fields(rpc_url, "0xparent")
    assert len(fields) == 1


@pytest.mark.asyncio
async def test_get_dynamic_fields_empty(respx_mock):
    """Dynamic fields returns empty list on error."""
    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(500, text="down")

    fields = await get_dynamic_fields(rpc_url, "0xparent")
    assert fields == []


@pytest.mark.asyncio
async def test_rpc_call_with_provided_client(respx_mock):
    """RPC call works with a provided httpx client."""
    import httpx

    from backend.warden.sui_queries import _rpc_call

    rpc_url = "https://test-rpc.example.com"
    respx_mock.post(rpc_url).respond(
        200,
        json={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}},
    )

    async with httpx.AsyncClient() as client:
        result = await _rpc_call(
            rpc_url, {"jsonrpc": "2.0", "id": 1, "method": "test", "params": []}, client
        )
    assert result == {"ok": True}

"""Tests for POD verifier — verify and fetch POD objects."""

import httpx
import pytest
import respx

from backend.ingestion.pod_verifier import PodVerifier


@pytest.fixture
def verifier():
    return PodVerifier(base_url="https://world-api.example.com", timeout=5)


@pytest.fixture
def no_url_verifier():
    return PodVerifier(base_url="", timeout=5)


# --- verify ---


@pytest.mark.asyncio
@respx.mock
async def test_verify_success(verifier):
    respx.post("https://world-api.example.com/v2/pod/verify").mock(
        return_value=httpx.Response(200, json={"verified": True})
    )
    async with httpx.AsyncClient() as client:
        result = await verifier.verify({"data": "test"}, client)
    assert result["valid"] is True
    assert result["details"]["verified"] is True


@pytest.mark.asyncio
@respx.mock
async def test_verify_failure_status(verifier):
    respx.post("https://world-api.example.com/v2/pod/verify").mock(
        return_value=httpx.Response(400, text="bad request")
    )
    async with httpx.AsyncClient() as client:
        result = await verifier.verify({"data": "test"}, client)
    assert result["valid"] is False
    assert result["status_code"] == 400


@pytest.mark.asyncio
async def test_verify_no_base_url(no_url_verifier):
    async with httpx.AsyncClient() as client:
        result = await no_url_verifier.verify({"data": "test"}, client)
    assert result["valid"] is False
    assert "no base_url" in result["error"]


@pytest.mark.asyncio
@respx.mock
async def test_verify_network_error(verifier):
    respx.post("https://world-api.example.com/v2/pod/verify").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    async with httpx.AsyncClient() as client:
        result = await verifier.verify({"data": "test"}, client)
    assert result["valid"] is False
    assert "timeout" in result["error"]


# --- fetch_pod ---


@pytest.mark.asyncio
@respx.mock
async def test_fetch_pod_success(verifier):
    respx.get("https://world-api.example.com/v2/assemblies/123").mock(
        return_value=httpx.Response(200, json={"pod": "envelope", "data": "signed"})
    )
    async with httpx.AsyncClient() as client:
        result = await verifier.fetch_pod("/v2/assemblies/123", client)
    assert result is not None
    assert result["pod"] == "envelope"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_pod_with_params(verifier):
    respx.get("https://world-api.example.com/v2/assemblies/123").mock(
        return_value=httpx.Response(200, json={"data": "ok"})
    )
    async with httpx.AsyncClient() as client:
        result = await verifier.fetch_pod("/v2/assemblies/123", client, params={"extra": "val"})
    assert result is not None


@pytest.mark.asyncio
async def test_fetch_pod_no_base_url(no_url_verifier):
    async with httpx.AsyncClient() as client:
        result = await no_url_verifier.fetch_pod("/v2/test", client)
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_pod_error(verifier):
    respx.get("https://world-api.example.com/v2/test").mock(
        return_value=httpx.Response(404, text="not found")
    )
    async with httpx.AsyncClient() as client:
        result = await verifier.fetch_pod("/v2/test", client)
    assert result is None

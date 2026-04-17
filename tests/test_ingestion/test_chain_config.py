"""Tests for chain_config — config loading, caching, and parsing."""

import time

import httpx
import pytest

from backend.db.database import init_db
from backend.ingestion.chain_config import (
    _ensure_table,
    _load_cached,
    _save_cache,
    fetch_chain_config,
    parse_config,
)


@pytest.fixture
def config_conn():
    """In-memory DB with chain_config table."""
    conn = init_db(":memory:")
    _ensure_table(conn)
    yield conn
    conn.close()


# ── parse_config ─────────────────────────────────────────────────────────────


def test_parse_config_dict():
    """parse_config extracts fields from dict response."""
    raw = {
        "contracts": {"world": {"address": "0xpackage123"}},
        "rpcUrls": {"default": {"http": "https://rpc.example.com", "webSocket": "wss://rpc.example.com"}},
        "cycleStartDate": "2026-01-01",
        "indexerUrl": "https://indexer.example.com",
        "chainId": "sui:testnet",
    }
    config = parse_config(raw)
    assert config["package_id"] == "0xpackage123"
    assert config["rpc_http"] == "https://rpc.example.com"
    assert config["rpc_ws"] == "wss://rpc.example.com"
    assert config["cycle_start"] == "2026-01-01"
    assert config["chain_id"] == "sui:testnet"


def test_parse_config_list_format():
    """parse_config handles list response (new API format)."""
    raw = [
        {"contracts": {"world": {"address": "0xfromlist"}}, "rpcUrls": {"default": {}}},
        {"other": "data"},
    ]
    config = parse_config(raw)
    assert config["package_id"] == "0xfromlist"


def test_parse_config_empty_list():
    """parse_config handles empty list response."""
    config = parse_config([])
    assert config["package_id"] == ""
    assert config["rpc_http"] == ""


def test_parse_config_empty_dict():
    """parse_config handles empty dict response."""
    config = parse_config({})
    assert config["package_id"] == ""


# ── Cache operations ─────────────────────────────────────────────────────────


def test_save_and_load_cache(config_conn):
    """_save_cache stores and _load_cached retrieves config."""
    config = {"package_id": "0xcached", "rpc_http": "https://rpc.test"}
    _save_cache(config_conn, config)

    loaded = _load_cached(config_conn)
    assert loaded is not None
    assert loaded["package_id"] == "0xcached"
    assert loaded["_cached"] is True
    assert loaded["_fetched_at"] > 0


def test_load_cached_empty(config_conn):
    """_load_cached returns None when no cache exists."""
    assert _load_cached(config_conn) is None


def test_load_cached_bad_json(config_conn):
    """_load_cached returns None on corrupt JSON in cache."""
    config_conn.execute(
        "INSERT INTO chain_config (key, value, fetched_at) VALUES ('world_config', 'bad json', ?)",
        (int(time.time()),),
    )
    config_conn.commit()
    assert _load_cached(config_conn) is None


def test_save_cache_overwrites(config_conn):
    """_save_cache overwrites existing cache entry."""
    _save_cache(config_conn, {"package_id": "0xfirst"})
    _save_cache(config_conn, {"package_id": "0xsecond"})

    loaded = _load_cached(config_conn)
    assert loaded["package_id"] == "0xsecond"


# ── fetch_chain_config ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_chain_config_success(config_conn, respx_mock):
    """fetch_chain_config fetches from API and caches result."""
    url = "https://world-api.example.com"
    respx_mock.get(f"{url}/config").mock(
        return_value=httpx.Response(200, json={
            "contracts": {"world": {"address": "0xlivepkg"}},
            "rpcUrls": {"default": {"http": "https://rpc.live"}},
            "cycleStartDate": "2026-04-01",
        })
    )

    config = await fetch_chain_config(url, config_conn)
    assert config["package_id"] == "0xlivepkg"

    # Verify it was cached
    cached = _load_cached(config_conn)
    assert cached["package_id"] == "0xlivepkg"


@pytest.mark.asyncio
async def test_fetch_chain_config_empty_package_id(config_conn, respx_mock):
    """fetch_chain_config falls back to cache when API returns empty packageId."""
    url = "https://world-api.example.com"
    respx_mock.get(f"{url}/config").mock(
        return_value=httpx.Response(200, json={"contracts": {}, "rpcUrls": {}})
    )

    # Pre-seed cache
    _save_cache(config_conn, {"package_id": "0xcached-fallback"})

    config = await fetch_chain_config(url, config_conn)
    assert config["package_id"] == "0xcached-fallback"
    assert config.get("_cached") is True


@pytest.mark.asyncio
async def test_fetch_chain_config_api_error_uses_cache(config_conn, respx_mock):
    """fetch_chain_config falls back to cache on API error."""
    url = "https://world-api.example.com"
    respx_mock.get(f"{url}/config").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    _save_cache(config_conn, {"package_id": "0xcached-error"})

    config = await fetch_chain_config(url, config_conn)
    assert config["package_id"] == "0xcached-error"


@pytest.mark.asyncio
async def test_fetch_chain_config_no_cache_no_api(config_conn, respx_mock):
    """fetch_chain_config returns empty config when API fails and no cache."""
    url = "https://world-api.example.com"
    respx_mock.get(f"{url}/config").mock(
        return_value=httpx.Response(500, text="down")
    )

    config = await fetch_chain_config(url, config_conn)
    assert config["package_id"] == ""
    assert config["rpc_http"] == ""


@pytest.mark.asyncio
async def test_fetch_chain_config_trailing_slash(config_conn, respx_mock):
    """fetch_chain_config strips trailing slash from URL."""
    url = "https://world-api.example.com/"
    respx_mock.get("https://world-api.example.com/config").mock(
        return_value=httpx.Response(200, json={
            "contracts": {"world": {"address": "0xslash"}},
            "rpcUrls": {"default": {}},
        })
    )

    config = await fetch_chain_config(url, config_conn)
    assert config["package_id"] == "0xslash"

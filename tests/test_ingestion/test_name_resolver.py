"""Tests for NameResolver — entity name resolution replacing NEXUS dependency."""

import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.ingestion.name_resolver import NameResolver, truncate_hex

PACKAGE_ID = "0xpkg123"


@pytest.fixture
def resolver(db_conn):
    """NameResolver with in-memory DB."""
    return NameResolver(
        db_conn,
        PACKAGE_ID,
        graphql_url="https://test.graphql/graphql",
    )


def _seed_entity_names(conn, names: list[tuple[str, str, str]]):
    """Seed entity_names table: (entity_id, display_name, entity_type)."""
    now = int(time.time())
    for eid, name, etype in names:
        conn.execute(
            "INSERT OR REPLACE INTO entity_names "
            "(entity_id, display_name, entity_type, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (eid, name, etype, now),
        )
    conn.commit()


def _mock_graphql_response(data: dict):
    """Create a mock httpx response for GraphQL."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": data}
    return mock_resp


# ── truncate_hex ─────────────────────────────────────────────────────────────


def test_truncate_hex_long_address():
    """Long hex addresses are truncated to prefix...suffix."""
    result = truncate_hex("0xabcdef1234567890abcdef")
    assert result.startswith("0xabcd")
    assert result.endswith("cdef")
    assert "..." in result


def test_truncate_hex_short_address():
    """Short addresses are returned as-is."""
    assert truncate_hex("0xabc") == "0xabc"
    assert truncate_hex("") == ""


def test_truncate_hex_none():
    """None/empty input returns as-is."""
    assert truncate_hex("") == ""


# ── Cache operations ─────────────────────────────────────────────────────────


def test_resolve_cached_hit(resolver, db_conn):
    """Cache hit returns display_name."""
    _seed_entity_names(db_conn, [("0xwallet1", "Kai Sunder", "character")])
    assert resolver.resolve_cached("0xwallet1") == "Kai Sunder"


def test_resolve_cached_miss(resolver):
    """Cache miss returns None."""
    assert resolver.resolve_cached("0xnonexistent") is None


def test_resolve_cached_empty_id(resolver):
    """Empty entity_id returns None."""
    assert resolver.resolve_cached("") is None


def test_resolve_cached_batch_returns_all_hits(resolver, db_conn):
    """Batch lookup returns all matching entries."""
    _seed_entity_names(
        db_conn,
        [
            ("0xw1", "Pilot One", "character"),
            ("0xw2", "Pilot Two", "character"),
            ("0xw3", "Pilot Three", "character"),
        ],
    )
    results = resolver.resolve_cached_batch(["0xw1", "0xw2", "0xmissing"])
    assert results == {"0xw1": "Pilot One", "0xw2": "Pilot Two"}


def test_resolve_cached_batch_empty_list(resolver):
    """Empty list returns empty dict."""
    assert resolver.resolve_cached_batch([]) == {}


def test_resolve_cached_batch_large_list(resolver, db_conn):
    """Batch with >900 IDs works (chunking logic)."""
    names = [(f"0x{i:04x}", f"Pilot {i}", "character") for i in range(1000)]
    _seed_entity_names(db_conn, names)
    ids = [f"0x{i:04x}" for i in range(1000)]
    results = resolver.resolve_cached_batch(ids)
    assert len(results) == 1000


# ── resolve (async, single) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_returns_cached_name(resolver, db_conn):
    """resolve() returns cached name without hitting GraphQL."""
    _seed_entity_names(db_conn, [("0xwallet1", "Kai Sunder", "character")])
    name = await resolver.resolve("0xwallet1")
    assert name == "Kai Sunder"


@pytest.mark.asyncio
async def test_resolve_empty_id(resolver):
    """resolve('') returns empty string."""
    assert await resolver.resolve("") == ""


@pytest.mark.asyncio
async def test_resolve_falls_back_to_truncated_hex(resolver, monkeypatch):
    """When GraphQL returns nothing, falls back to truncated hex."""
    # Patch _fetch_characters to return 0 (no names found)
    monkeypatch.setattr(resolver, "_fetch_characters", AsyncMock(return_value=0))
    name = await resolver.resolve("0xabcdef1234567890abcdef1234567890")
    assert "..." in name
    assert name.startswith("0x")


@pytest.mark.asyncio
async def test_resolve_fetches_from_graphql_on_miss(resolver, db_conn, monkeypatch):
    """Cache miss triggers GraphQL fetch, then re-checks cache."""

    async def mock_fetch(client):
        # Simulate GraphQL populating the cache
        db_conn.execute(
            "INSERT INTO entity_names (entity_id, display_name, entity_type, updated_at) "
            "VALUES ('0xtarget', 'Found Name', 'character', ?)",
            (int(time.time()),),
        )
        db_conn.commit()
        return 1

    monkeypatch.setattr(resolver, "_fetch_characters", mock_fetch)
    name = await resolver.resolve("0xtarget")
    assert name == "Found Name"


# ── resolve_batch (async, multiple) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_batch_all_cached(resolver, db_conn):
    """All IDs in cache — no GraphQL call needed."""
    _seed_entity_names(
        db_conn,
        [("0xw1", "Pilot One", "character"), ("0xw2", "Pilot Two", "character")],
    )
    results = await resolver.resolve_batch(["0xw1", "0xw2"])
    assert results == {"0xw1": "Pilot One", "0xw2": "Pilot Two"}


@pytest.mark.asyncio
async def test_resolve_batch_mixed_cached_and_missing(resolver, db_conn, monkeypatch):
    """Mixed: some cached, some resolved via GraphQL, some fallback."""
    _seed_entity_names(db_conn, [("0xw1", "Pilot One", "character")])

    async def mock_fetch(client):
        db_conn.execute(
            "INSERT INTO entity_names (entity_id, display_name, entity_type, updated_at) "
            "VALUES ('0xw2', 'Pilot Two', 'character', ?)",
            (int(time.time()),),
        )
        db_conn.commit()
        return 1

    monkeypatch.setattr(resolver, "_fetch_characters", mock_fetch)

    results = await resolver.resolve_batch(["0xw1", "0xw2", "0xabcdef1234567890abcdef1234567890"])
    assert results["0xw1"] == "Pilot One"
    assert results["0xw2"] == "Pilot Two"
    # Third ID should be truncated hex
    third = results["0xabcdef1234567890abcdef1234567890"]
    assert "..." in third


@pytest.mark.asyncio
async def test_resolve_batch_empty(resolver):
    """Empty list returns empty dict."""
    assert await resolver.resolve_batch([]) == {}


@pytest.mark.asyncio
async def test_resolve_batch_deduplicates(resolver, db_conn):
    """Duplicate IDs in input don't cause issues."""
    _seed_entity_names(db_conn, [("0xw1", "Pilot One", "character")])
    results = await resolver.resolve_batch(["0xw1", "0xw1", "0xw1"])
    assert results == {"0xw1": "Pilot One"}


@pytest.mark.asyncio
async def test_resolve_batch_graphql_error_still_returns(resolver, monkeypatch):
    """GraphQL failure still returns truncated hex for all IDs."""
    monkeypatch.setattr(
        resolver,
        "_fetch_characters",
        AsyncMock(side_effect=httpx.ConnectError("timeout")),
    )
    results = await resolver.resolve_batch(["0xabcdef1234567890abcdef1234567890"])
    assert len(results) == 1
    val = list(results.values())[0]
    assert "..." in val


# ── cache_name ───────────────────────────────────────────────────────────────


def test_cache_name_inserts(resolver, db_conn):
    """cache_name stores a new entry."""
    resolver.cache_name("0xnew", "New Pilot", "character", "12345")
    row = db_conn.execute(
        "SELECT display_name, tribe_id FROM entity_names WHERE entity_id = ?",
        ("0xnew",),
    ).fetchone()
    assert row["display_name"] == "New Pilot"
    assert row["tribe_id"] == "12345"


def test_cache_name_updates_existing(resolver, db_conn):
    """cache_name upserts over existing entry."""
    _seed_entity_names(db_conn, [("0xold", "Old Name", "character")])
    resolver.cache_name("0xold", "Updated Name")
    row = db_conn.execute(
        "SELECT display_name FROM entity_names WHERE entity_id = ?",
        ("0xold",),
    ).fetchone()
    assert row["display_name"] == "Updated Name"


def test_cache_name_ignores_empty(resolver, db_conn):
    """Empty entity_id or display_name is a no-op."""
    resolver.cache_name("", "Name")
    resolver.cache_name("0xid", "")
    count = db_conn.execute("SELECT COUNT(*) FROM entity_names").fetchone()[0]
    assert count == 0


# ── cache_stats ──────────────────────────────────────────────────────────────


def test_cache_stats_empty(resolver):
    """Empty cache returns zero counts."""
    stats = resolver.cache_stats()
    assert stats == {"total": 0, "stale": 0, "fresh": 0}


def test_cache_stats_with_entries(resolver, db_conn):
    """Stats reflect cache state."""
    now = int(time.time())
    # Fresh entry
    db_conn.execute(
        "INSERT INTO entity_names (entity_id, display_name, entity_type, updated_at) "
        "VALUES ('0xfresh', 'Fresh', 'character', ?)",
        (now,),
    )
    # Stale entry (2 days old)
    db_conn.execute(
        "INSERT INTO entity_names (entity_id, display_name, entity_type, updated_at) "
        "VALUES ('0xstale', 'Stale', 'character', ?)",
        (now - 200_000,),
    )
    db_conn.commit()
    stats = resolver.cache_stats()
    assert stats["total"] == 2
    assert stats["stale"] == 1
    assert stats["fresh"] == 1


# ── get_stale_ids ────────────────────────────────────────────────────────────


def test_get_stale_ids(resolver, db_conn):
    """Stale entries are returned."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO entity_names (entity_id, display_name, entity_type, updated_at) "
        "VALUES ('0xfresh', 'Fresh', 'character', ?)",
        (now,),
    )
    db_conn.execute(
        "INSERT INTO entity_names (entity_id, display_name, entity_type, updated_at) "
        "VALUES ('0xstale', 'Stale', 'character', ?)",
        (now - 200_000,),
    )
    db_conn.commit()
    stale = resolver.get_stale_ids()
    assert "0xstale" in stale
    assert "0xfresh" not in stale


# ── _fetch_characters (internal GraphQL) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_characters_stores_names(resolver, db_conn):
    """GraphQL character fetch stores names in entity_names."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response(
        {
            "objects": {
                "nodes": [
                    {
                        "asMoveObject": {
                            "contents": {
                                "json": {
                                    "character_address": "0xwallet1",
                                    "metadata": {"name": "Kai Sunder"},
                                    "tribe_id": 98000430,
                                }
                            }
                        }
                    },
                ],
                "pageInfo": {"hasNextPage": False},
            }
        }
    )

    stored = await resolver._fetch_characters(mock_client)
    assert stored == 1

    row = db_conn.execute(
        "SELECT display_name, tribe_id FROM entity_names WHERE entity_id = ?",
        ("0xwallet1",),
    ).fetchone()
    assert row["display_name"] == "Kai Sunder"
    assert row["tribe_id"] == "98000430"


@pytest.mark.asyncio
async def test_fetch_characters_skips_empty_names(resolver, db_conn):
    """Characters without names are skipped."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response(
        {
            "objects": {
                "nodes": [
                    {
                        "asMoveObject": {
                            "contents": {
                                "json": {
                                    "character_address": "0xw1",
                                    "metadata": {"name": ""},
                                }
                            }
                        }
                    },
                ],
                "pageInfo": {"hasNextPage": False},
            }
        }
    )

    stored = await resolver._fetch_characters(mock_client)
    assert stored == 0


@pytest.mark.asyncio
async def test_fetch_characters_handles_error(resolver):
    """GraphQL errors return 0 without raising."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("timeout")

    stored = await resolver._fetch_characters(mock_client)
    assert stored == 0


@pytest.mark.asyncio
async def test_fetch_characters_paginates(resolver, db_conn):
    """Pagination is followed across multiple pages."""
    page1 = _mock_graphql_response(
        {
            "objects": {
                "nodes": [
                    {
                        "asMoveObject": {
                            "contents": {
                                "json": {
                                    "character_address": "0xw1",
                                    "metadata": {"name": "Pilot One"},
                                    "tribe_id": 0,
                                }
                            }
                        }
                    },
                ],
                "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
            }
        }
    )
    page2 = _mock_graphql_response(
        {
            "objects": {
                "nodes": [
                    {
                        "asMoveObject": {
                            "contents": {
                                "json": {
                                    "character_address": "0xw2",
                                    "metadata": {"name": "Pilot Two"},
                                    "tribe_id": 0,
                                }
                            }
                        }
                    },
                ],
                "pageInfo": {"hasNextPage": False},
            }
        }
    )

    mock_client = AsyncMock()
    mock_client.post.side_effect = [page1, page2]

    stored = await resolver._fetch_characters(mock_client)
    assert stored == 2


# ── _graphql_query ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graphql_query_raises_on_errors(resolver):
    """GraphQL errors in response raise ValueError."""
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "errors": [{"message": "Query too complex"}],
    }
    mock_client.post.return_value = mock_resp

    with pytest.raises(ValueError, match="Query too complex"):
        await resolver._graphql_query(mock_client, "query { test }")


@pytest.mark.asyncio
async def test_graphql_query_returns_data(resolver):
    """Successful query returns data dict."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response({"test": "value"})

    data = await resolver._graphql_query(mock_client, "query { test }")
    assert data == {"test": "value"}

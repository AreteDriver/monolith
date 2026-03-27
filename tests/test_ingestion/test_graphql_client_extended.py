"""Extended tests for SuiGraphQLClient — audit_object_versions, poll_config_singletons,
profile_wallet_activity, scan_owned_objects.

Covers the previously untested async methods (lines 303-541).
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.ingestion.graphql_client import SuiGraphQLClient

PACKAGE_ID = "0xpkg123"


@pytest.fixture
def gql_client(db_conn):
    """GraphQL client with in-memory DB."""
    return SuiGraphQLClient(db_conn, PACKAGE_ID, graphql_url="https://test.graphql/graphql")


def _mock_graphql_response(data: dict):
    """Create a mock httpx response for GraphQL."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": data}
    return mock_resp


def _seed_objects(conn, objects: list[tuple[str, str, int]]):
    """Insert objects with object_id, type, last_seen."""
    for obj_id, obj_type, last_seen in objects:
        conn.execute(
            "INSERT OR REPLACE INTO objects (object_id, object_type, last_seen) VALUES (?, ?, ?)",
            (obj_id, obj_type, last_seen),
        )
    conn.commit()


def _seed_chain_events(conn, events: list[dict]):
    """Insert chain events with sender in raw_json."""
    for i, evt in enumerate(events):
        conn.execute(
            "INSERT INTO chain_events (event_id, event_type, object_id,"
            " raw_json, timestamp, processed) VALUES (?, 'test', 'obj', ?, ?, 1)",
            (f"evt-{i}", json.dumps(evt), evt.get("_ts", int(time.time()))),
        )
    conn.commit()


# ── audit_object_versions ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_object_versions_stores_versions(gql_client, db_conn):
    """audit_object_versions stores version snapshots for tracked objects."""
    now = int(time.time())
    _seed_objects(db_conn, [("0xobj1", "assembly", now), ("0xobj2", "gate", now)])

    mock_client = AsyncMock()
    # obj1 has 2 versions
    resp1 = _mock_graphql_response(
        {
            "objectVersions": {
                "nodes": [
                    {
                        "version": 1,
                        "digest": "d1",
                        "asMoveObject": {"contents": {"json": {"fuel": 100}}},
                    },
                    {
                        "version": 2,
                        "digest": "d2",
                        "asMoveObject": {"contents": {"json": {"fuel": 50}}},
                    },
                ]
            }
        }
    )
    # obj2 has 1 version
    resp2 = _mock_graphql_response(
        {
            "objectVersions": {
                "nodes": [
                    {
                        "version": 1,
                        "digest": "d3",
                        "asMoveObject": {"contents": {"json": {"state": "open"}}},
                    },
                ]
            }
        }
    )
    mock_client.post.side_effect = [resp1, resp2]

    stored = await gql_client.audit_object_versions(mock_client)
    assert stored == 3

    rows = db_conn.execute("SELECT * FROM object_versions ORDER BY version").fetchall()
    assert len(rows) == 3
    assert rows[0]["object_id"] == "0xobj1"
    assert rows[0]["version"] == 1
    assert rows[0]["digest"] == "d1"


@pytest.mark.asyncio
async def test_audit_object_versions_skips_non_sui(gql_client, db_conn):
    """Objects not starting with 0x are skipped."""
    now = int(time.time())
    _seed_objects(db_conn, [("legacy-obj-1", "assembly", now)])

    mock_client = AsyncMock()
    stored = await gql_client.audit_object_versions(mock_client)
    assert stored == 0
    # No GraphQL calls made
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_audit_object_versions_handles_error(gql_client, db_conn):
    """Gracefully continues on GraphQL error for individual objects."""
    now = int(time.time())
    _seed_objects(db_conn, [("0xobj1", "assembly", now), ("0xobj2", "gate", now)])

    mock_client = AsyncMock()
    # First object errors, second succeeds
    mock_client.post.side_effect = [
        httpx.ConnectError("timeout"),
        _mock_graphql_response(
            {
                "objectVersions": {
                    "nodes": [
                        {"version": 1, "digest": "d1", "asMoveObject": {"contents": {"json": {}}}}
                    ]
                }
            }
        ),
    ]

    stored = await gql_client.audit_object_versions(mock_client)
    assert stored == 1


@pytest.mark.asyncio
async def test_audit_object_versions_no_recent_objects(gql_client, db_conn):
    """No objects with recent activity means no queries."""
    # Seed objects with old last_seen (> 24h ago)
    old_time = int(time.time()) - 200000
    _seed_objects(db_conn, [("0xobj1", "assembly", old_time)])

    mock_client = AsyncMock()
    stored = await gql_client.audit_object_versions(mock_client)
    assert stored == 0
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_audit_object_versions_ignores_duplicates(gql_client, db_conn):
    """INSERT OR IGNORE prevents duplicate version entries."""
    now = int(time.time())
    _seed_objects(db_conn, [("0xobj1", "assembly", now)])

    mock_client = AsyncMock()
    resp = _mock_graphql_response(
        {
            "objectVersions": {
                "nodes": [
                    {
                        "version": 1,
                        "digest": "d1",
                        "asMoveObject": {"contents": {"json": {"fuel": 100}}},
                    }
                ]
            }
        }
    )
    mock_client.post.return_value = resp

    # First call stores
    await gql_client.audit_object_versions(mock_client)
    # Second call — same version, should be ignored
    stored = await gql_client.audit_object_versions(mock_client)
    # Still counted but INSERT OR IGNORE doesn't fail
    assert stored >= 0

    rows = db_conn.execute(
        "SELECT COUNT(*) FROM object_versions WHERE object_id = '0xobj1'"
    ).fetchone()
    assert rows[0] == 1


# ── poll_config_singletons ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_config_singletons_stores_snapshots(gql_client, db_conn):
    """Polls energy, fuel, gate configs and stores version snapshots."""
    mock_client = AsyncMock()

    # All three config objects return data
    for _ in range(3):
        mock_client.post.side_effect = None

    responses = [
        _mock_graphql_response(
            {"object": {"version": 5, "asMoveObject": {"contents": {"json": {"rate": 0.001}}}}}
        ),
        _mock_graphql_response(
            {"object": {"version": 3, "asMoveObject": {"contents": {"json": {"burn_rate": 10}}}}}
        ),
        _mock_graphql_response(
            {"object": {"version": 7, "asMoveObject": {"contents": {"json": {"toll": 100}}}}}
        ),
    ]
    mock_client.post.side_effect = responses

    stored = await gql_client.poll_config_singletons(mock_client)
    assert stored == 3

    rows = db_conn.execute("SELECT * FROM config_snapshots ORDER BY config_type").fetchall()
    assert len(rows) == 3
    types = {row["config_type"] for row in rows}
    assert types == {"energy", "fuel", "gate"}


@pytest.mark.asyncio
async def test_poll_config_singletons_skips_not_found(gql_client, db_conn):
    """Skips config objects that return null."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = [
        _mock_graphql_response({"object": None}),  # energy not found
        _mock_graphql_response(
            {"object": {"version": 1, "asMoveObject": {"contents": {"json": {}}}}}
        ),
        _mock_graphql_response({"object": None}),  # gate not found
    ]

    stored = await gql_client.poll_config_singletons(mock_client)
    assert stored == 1


@pytest.mark.asyncio
async def test_poll_config_singletons_handles_error(gql_client, db_conn):
    """Continues on error for individual configs."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = [
        httpx.ConnectError("timeout"),  # energy fails
        _mock_graphql_response(
            {"object": {"version": 2, "asMoveObject": {"contents": {"json": {"x": 1}}}}}
        ),
        _mock_graphql_response(
            {"object": {"version": 3, "asMoveObject": {"contents": {"json": {"y": 2}}}}}
        ),
    ]

    stored = await gql_client.poll_config_singletons(mock_client)
    assert stored == 2


# ── profile_wallet_activity ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_profile_wallet_activity_computes_stats(gql_client, db_conn):
    """Profiles wallet with transaction intervals for bot detection."""
    now = int(time.time())
    _seed_chain_events(
        db_conn,
        [
            {"sender": "0xwallet1", "_ts": now},
        ],
    )

    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response(
        {
            "transactions": {
                "nodes": [
                    {"effects": {"timestamp": str(now * 1000 - 30000)}},
                    {"effects": {"timestamp": str(now * 1000 - 20000)}},
                    {"effects": {"timestamp": str(now * 1000 - 10000)}},
                    {"effects": {"timestamp": str(now * 1000)}},
                ]
            }
        }
    )

    updated = await gql_client.profile_wallet_activity(mock_client)
    assert updated == 1

    row = db_conn.execute(
        "SELECT * FROM wallet_activity WHERE wallet_address = '0xwallet1'"
    ).fetchone()
    assert row is not None
    assert row["tx_count"] == 4
    assert row["avg_interval_seconds"] > 0


@pytest.mark.asyncio
async def test_profile_wallet_activity_skips_few_txs(gql_client, db_conn):
    """Wallets with fewer than 3 transactions are skipped."""
    now = int(time.time())
    _seed_chain_events(db_conn, [{"sender": "0xwallet1", "_ts": now}])

    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response(
        {
            "transactions": {
                "nodes": [
                    {"effects": {"timestamp": str(now * 1000)}},
                    {"effects": {"timestamp": str(now * 1000 - 10000)}},
                ]
            }
        }
    )

    updated = await gql_client.profile_wallet_activity(mock_client)
    assert updated == 0


@pytest.mark.asyncio
async def test_profile_wallet_activity_skips_non_sui_wallets(gql_client, db_conn):
    """Non-0x wallets are skipped."""
    now = int(time.time())
    _seed_chain_events(db_conn, [{"sender": "not-a-wallet", "_ts": now}])

    mock_client = AsyncMock()
    updated = await gql_client.profile_wallet_activity(mock_client)
    assert updated == 0
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_profile_wallet_activity_handles_error(gql_client, db_conn):
    """Gracefully handles query errors per wallet."""
    now = int(time.time())
    _seed_chain_events(db_conn, [{"sender": "0xwallet1", "_ts": now}])

    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("timeout")

    updated = await gql_client.profile_wallet_activity(mock_client)
    assert updated == 0


@pytest.mark.asyncio
async def test_profile_wallet_activity_no_recent_events(gql_client, db_conn):
    """No recent chain events means no wallets to profile."""
    # No events seeded
    mock_client = AsyncMock()
    updated = await gql_client.profile_wallet_activity(mock_client)
    assert updated == 0
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_profile_wallet_activity_timestamps_epoch_seconds(gql_client, db_conn):
    """Handles timestamps already in epoch seconds (< 1e12)."""
    now = int(time.time())
    _seed_chain_events(db_conn, [{"sender": "0xwallet1", "_ts": now}])

    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response(
        {
            "transactions": {
                "nodes": [
                    {"effects": {"timestamp": str(now - 30)}},
                    {"effects": {"timestamp": str(now - 20)}},
                    {"effects": {"timestamp": str(now - 10)}},
                ]
            }
        }
    )

    updated = await gql_client.profile_wallet_activity(mock_client)
    assert updated == 1

    row = db_conn.execute(
        "SELECT avg_interval_seconds FROM wallet_activity WHERE wallet_address = '0xwallet1'"
    ).fetchone()
    assert row["avg_interval_seconds"] == 10.0


# ── scan_owned_objects ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_owned_objects_returns_counts(gql_client, db_conn):
    """Scans owned objects and returns wallet→count map."""
    now = int(time.time())
    _seed_chain_events(
        db_conn,
        [
            {"sender": "0xwallet1", "_ts": now},
            {"sender": "0xwallet2", "_ts": now},
        ],
    )

    mock_client = AsyncMock()
    mock_client.post.side_effect = [
        _mock_graphql_response(
            {"objects": {"nodes": [{"address": "0xa"}, {"address": "0xb"}, {"address": "0xc"}]}}
        ),
        _mock_graphql_response({"objects": {"nodes": [{"address": "0xd"}]}}),
    ]

    ownership = await gql_client.scan_owned_objects(mock_client)
    assert ownership["0xwallet1"] == 3
    assert ownership["0xwallet2"] == 1


@pytest.mark.asyncio
async def test_scan_owned_objects_skips_empty(gql_client, db_conn):
    """Wallets with 0 objects are excluded from results."""
    now = int(time.time())
    _seed_chain_events(db_conn, [{"sender": "0xwallet1", "_ts": now}])

    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response({"objects": {"nodes": []}})

    ownership = await gql_client.scan_owned_objects(mock_client)
    assert ownership == {}


@pytest.mark.asyncio
async def test_scan_owned_objects_handles_error(gql_client, db_conn):
    """Gracefully handles per-wallet query errors."""
    now = int(time.time())
    _seed_chain_events(db_conn, [{"sender": "0xwallet1", "_ts": now}])

    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("timeout")

    ownership = await gql_client.scan_owned_objects(mock_client)
    assert ownership == {}


# ── _query internals ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_sends_variables(gql_client):
    """_query sends variables in payload when provided."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response({"test": True})

    await gql_client._query(mock_client, "query { test }", {"foo": "bar"})

    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert payload["variables"] == {"foo": "bar"}


@pytest.mark.asyncio
async def test_query_no_variables(gql_client):
    """_query omits variables key when None."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response({"test": True})

    await gql_client._query(mock_client, "query { test }")

    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert "variables" not in payload

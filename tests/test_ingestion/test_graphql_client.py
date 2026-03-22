"""Tests for Sui GraphQL client — location enrichment from on-chain data."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.ingestion.graphql_client import SuiGraphQLClient

PACKAGE_ID = "0xpkg123"


@pytest.fixture
def gql_client(db_conn):
    """GraphQL client with in-memory DB."""
    return SuiGraphQLClient(db_conn, PACKAGE_ID, graphql_url="https://test.graphql/graphql")


def _seed_objects(conn, objects: list[tuple[str, str]]):
    """Insert objects with optional system_id (empty string = needs enrichment)."""
    for obj_id, sys_id in objects:
        conn.execute(
            "INSERT OR REPLACE INTO objects (object_id, object_type, system_id, last_seen) "
            "VALUES (?, 'assembly', ?, 1)",
            (obj_id, sys_id),
        )
    conn.commit()


def _seed_anomalies(conn, anomalies: list[tuple[str, str]]):
    """Insert anomalies with optional system_id."""
    for i, (obj_id, sys_id) in enumerate(anomalies):
        conn.execute(
            "INSERT INTO anomalies "
            "(anomaly_id, anomaly_type, severity, object_id, system_id, detected_at) "
            "VALUES (?, 'TEST', 'LOW', ?, ?, ?)",
            (f"anom-{i}", obj_id, sys_id, 1000 + i),
        )
    conn.commit()


def _mock_graphql_response(data: dict):
    """Create a mock httpx response for GraphQL."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": data}
    return mock_resp


# ── Location Registry Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_location_registry_returns_mappings(gql_client):
    """Location Registry dynamic fields are parsed into object→system mappings."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response(
        {
            "object": {
                "address": "0xregistry",
                "version": 1,
                "asMoveObject": {
                    "contents": {"type": {"repr": "LocationRegistry"}, "json": {}},
                    "dynamicFields": {
                        "nodes": [
                            {
                                "name": {"json": "0xobj1", "type": {"repr": "address"}},
                                "value": {"json": {"solar_system_id": "30012602"}},
                            },
                            {
                                "name": {"json": "0xobj2", "type": {"repr": "address"}},
                                "value": {"json": {"solar_system_id": "30012603"}},
                            },
                        ]
                    },
                },
            }
        }
    )

    mappings = await gql_client.query_location_registry(mock_client)
    assert mappings == {"0xobj1": "30012602", "0xobj2": "30012603"}


@pytest.mark.asyncio
async def test_location_registry_empty_on_not_found(gql_client):
    """Returns empty dict when registry object is not found (pruned)."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response({"object": None})

    mappings = await gql_client.query_location_registry(mock_client)
    assert mappings == {}


@pytest.mark.asyncio
async def test_location_registry_handles_error(gql_client):
    """Returns empty dict on HTTP error."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    mappings = await gql_client.query_location_registry(mock_client)
    assert mappings == {}


@pytest.mark.asyncio
async def test_location_registry_skips_missing_system_id(gql_client):
    """Dynamic fields without solar_system_id are skipped."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response(
        {
            "object": {
                "address": "0xregistry",
                "version": 1,
                "asMoveObject": {
                    "contents": {"type": {"repr": "LocationRegistry"}, "json": {}},
                    "dynamicFields": {
                        "nodes": [
                            {
                                "name": {"json": "0xobj1", "type": {"repr": "address"}},
                                "value": {"json": {"some_field": "no_system"}},
                            },
                        ]
                    },
                },
            }
        }
    )

    mappings = await gql_client.query_location_registry(mock_client)
    assert mappings == {}


# ── Killmail Object Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_killmail_locations_returns_mappings(gql_client):
    """Killmail objects map both victim and killer to system_id."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response(
        {
            "objects": {
                "nodes": [
                    {
                        "address": "0xkm1",
                        "version": 1,
                        "asMoveObject": {
                            "contents": {
                                "json": {
                                    "victim_id": "0xvictim1",
                                    "killer_id": "0xkiller1",
                                    "solar_system_id": "30012602",
                                }
                            }
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    )

    mappings = await gql_client.query_killmail_locations(mock_client)
    assert mappings["0xvictim1"] == "30012602"
    assert mappings["0xkiller1"] == "30012602"


@pytest.mark.asyncio
async def test_killmail_locations_paginates(gql_client):
    """Killmail query follows pagination cursors."""
    page1 = _mock_graphql_response(
        {
            "objects": {
                "nodes": [
                    {
                        "address": "0xkm1",
                        "version": 1,
                        "asMoveObject": {
                            "contents": {
                                "json": {
                                    "victim_id": "0xv1",
                                    "killer_id": "0xk1",
                                    "solar_system_id": "30012602",
                                }
                            }
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
            }
        }
    )
    page2 = _mock_graphql_response(
        {
            "objects": {
                "nodes": [
                    {
                        "address": "0xkm2",
                        "version": 1,
                        "asMoveObject": {
                            "contents": {
                                "json": {
                                    "victim_id": "0xv2",
                                    "killer_id": "0xk2",
                                    "solar_system_id": "30012603",
                                }
                            }
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    )

    mock_client = AsyncMock()
    mock_client.post.side_effect = [page1, page2]

    mappings = await gql_client.query_killmail_locations(mock_client)
    assert len(mappings) == 4  # 2 per killmail
    assert mappings["0xv2"] == "30012603"


@pytest.mark.asyncio
async def test_killmail_locations_skips_no_system(gql_client):
    """Killmails without solar_system_id are skipped."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response(
        {
            "objects": {
                "nodes": [
                    {
                        "address": "0xkm1",
                        "version": 1,
                        "asMoveObject": {
                            "contents": {"json": {"victim_id": "0xv1", "killer_id": "0xk1"}}
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False},
            }
        }
    )

    mappings = await gql_client.query_killmail_locations(mock_client)
    assert mappings == {}


# ── Location Events Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_location_events_returns_mappings(gql_client):
    """Location module events are parsed into object→system mappings."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response(
        {
            "events": {
                "nodes": [
                    {
                        "contents": {
                            "json": {"object_id": "0xobj1", "solar_system_id": "30012602"},
                            "type": {"repr": "LocationRevealedEvent"},
                        },
                        "timestamp": "1710000000",
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    )

    mappings = await gql_client.query_location_events(mock_client)
    assert mappings == {"0xobj1": "30012602"}


@pytest.mark.asyncio
async def test_location_events_handles_error(gql_client):
    """Returns empty dict on GraphQL error."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_graphql_response({})
    # events key missing → should handle gracefully
    mappings = await gql_client.query_location_events(mock_client)
    assert mappings == {}


# ── Enrichment Integration Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enrich_locations_updates_objects(gql_client, db_conn):
    """Enrichment updates objects missing system_id."""
    _seed_objects(db_conn, [("0xobj1", ""), ("0xobj2", "existing_system")])

    mock_client = AsyncMock()

    # Registry returns mapping for obj1
    registry_resp = _mock_graphql_response(
        {
            "object": {
                "address": "0xregistry",
                "version": 1,
                "asMoveObject": {
                    "contents": {"type": {"repr": "LocationRegistry"}, "json": {}},
                    "dynamicFields": {
                        "nodes": [
                            {
                                "name": {"json": "0xobj1", "type": {"repr": "address"}},
                                "value": {"json": {"solar_system_id": "30012602"}},
                            },
                        ]
                    },
                },
            }
        }
    )
    # Location events return nothing
    events_resp = _mock_graphql_response(
        {
            "events": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        }
    )
    # Killmails return nothing
    killmails_resp = _mock_graphql_response(
        {
            "objects": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        }
    )

    mock_client.post.side_effect = [registry_resp, events_resp, killmails_resp]

    updated = await gql_client.enrich_locations(mock_client)
    assert updated == 1

    # obj1 now has system_id
    row = db_conn.execute(
        "SELECT system_id FROM objects WHERE object_id = ?", ("0xobj1",)
    ).fetchone()
    assert row["system_id"] == "30012602"

    # obj2 unchanged (already had a system_id)
    row = db_conn.execute(
        "SELECT system_id FROM objects WHERE object_id = ?", ("0xobj2",)
    ).fetchone()
    assert row["system_id"] == "existing_system"


@pytest.mark.asyncio
async def test_enrich_locations_updates_anomalies(gql_client, db_conn):
    """Enrichment also backfills anomalies missing system_id."""
    _seed_objects(db_conn, [("0xobj1", "")])
    _seed_anomalies(db_conn, [("0xobj1", "")])

    mock_client = AsyncMock()
    registry_resp = _mock_graphql_response(
        {
            "object": {
                "address": "0xregistry",
                "version": 1,
                "asMoveObject": {
                    "contents": {"type": {"repr": "LocationRegistry"}, "json": {}},
                    "dynamicFields": {
                        "nodes": [
                            {
                                "name": {"json": "0xobj1", "type": {"repr": "address"}},
                                "value": {"json": {"solar_system_id": "30012602"}},
                            },
                        ]
                    },
                },
            }
        }
    )
    events_resp = _mock_graphql_response(
        {
            "events": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        }
    )
    killmails_resp = _mock_graphql_response(
        {
            "objects": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        }
    )
    mock_client.post.side_effect = [registry_resp, events_resp, killmails_resp]

    await gql_client.enrich_locations(mock_client)

    row = db_conn.execute(
        "SELECT system_id FROM anomalies WHERE object_id = ?", ("0xobj1",)
    ).fetchone()
    assert row["system_id"] == "30012602"


@pytest.mark.asyncio
async def test_enrich_locations_registry_priority(gql_client, db_conn):
    """Registry data takes priority over events and killmails."""
    _seed_objects(db_conn, [("0xobj1", "")])

    mock_client = AsyncMock()

    # Registry says system 100
    registry_resp = _mock_graphql_response(
        {
            "object": {
                "address": "0xregistry",
                "version": 1,
                "asMoveObject": {
                    "contents": {"type": {"repr": "LocationRegistry"}, "json": {}},
                    "dynamicFields": {
                        "nodes": [
                            {
                                "name": {"json": "0xobj1", "type": {"repr": "address"}},
                                "value": {"json": {"solar_system_id": "100"}},
                            },
                        ]
                    },
                },
            }
        }
    )
    # Events say system 200
    events_resp = _mock_graphql_response(
        {
            "events": {
                "nodes": [
                    {
                        "contents": {
                            "json": {"object_id": "0xobj1", "solar_system_id": "200"},
                            "type": {"repr": "LocationRevealedEvent"},
                        },
                        "timestamp": "1",
                    }
                ],
                "pageInfo": {"hasNextPage": False},
            },
        }
    )
    killmails_resp = _mock_graphql_response(
        {
            "objects": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        }
    )
    mock_client.post.side_effect = [registry_resp, events_resp, killmails_resp]

    await gql_client.enrich_locations(mock_client)

    row = db_conn.execute(
        "SELECT system_id FROM objects WHERE object_id = ?", ("0xobj1",)
    ).fetchone()
    assert row["system_id"] == "100"  # Registry wins


@pytest.mark.asyncio
async def test_enrich_locations_no_mappings(gql_client, db_conn):
    """No updates when all sources return empty."""
    _seed_objects(db_conn, [("0xobj1", "")])

    mock_client = AsyncMock()
    empty_registry = _mock_graphql_response({"object": None})
    empty_events = _mock_graphql_response(
        {
            "events": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        }
    )
    empty_killmails = _mock_graphql_response(
        {
            "objects": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        }
    )
    mock_client.post.side_effect = [empty_registry, empty_events, empty_killmails]

    updated = await gql_client.enrich_locations(mock_client)
    assert updated == 0


@pytest.mark.asyncio
async def test_enrich_locations_all_sources_combine(gql_client, db_conn):
    """All three sources contribute unique mappings."""
    _seed_objects(db_conn, [("0xobj1", ""), ("0xobj2", ""), ("0xobj3", "")])

    mock_client = AsyncMock()

    # Registry has obj1
    registry_resp = _mock_graphql_response(
        {
            "object": {
                "address": "0xregistry",
                "version": 1,
                "asMoveObject": {
                    "contents": {"type": {"repr": "LocationRegistry"}, "json": {}},
                    "dynamicFields": {
                        "nodes": [
                            {
                                "name": {"json": "0xobj1", "type": {"repr": "address"}},
                                "value": {"json": {"solar_system_id": "100"}},
                            },
                        ]
                    },
                },
            }
        }
    )
    # Events have obj2
    events_resp = _mock_graphql_response(
        {
            "events": {
                "nodes": [
                    {
                        "contents": {
                            "json": {"object_id": "0xobj2", "solar_system_id": "200"},
                            "type": {"repr": "LocationRevealedEvent"},
                        },
                        "timestamp": "1",
                    }
                ],
                "pageInfo": {"hasNextPage": False},
            },
        }
    )
    # Killmails have obj3 (as victim)
    killmails_resp = _mock_graphql_response(
        {
            "objects": {
                "nodes": [
                    {
                        "address": "0xkm1",
                        "version": 1,
                        "asMoveObject": {
                            "contents": {
                                "json": {
                                    "victim_id": "0xobj3",
                                    "killer_id": "0xunknown",
                                    "solar_system_id": "300",
                                }
                            }
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False},
            },
        }
    )
    mock_client.post.side_effect = [registry_resp, events_resp, killmails_resp]

    updated = await gql_client.enrich_locations(mock_client)
    assert updated == 3

    for obj_id, expected_sys in [("0xobj1", "100"), ("0xobj2", "200"), ("0xobj3", "300")]:
        row = db_conn.execute(
            "SELECT system_id FROM objects WHERE object_id = ?", (obj_id,)
        ).fetchone()
        assert row["system_id"] == expected_sys


# ── GraphQL Query Error Handling ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_handles_graphql_errors(gql_client):
    """GraphQL errors in response raise ValueError."""
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "errors": [{"message": "Query too complex"}],
    }
    mock_client.post.return_value = mock_resp

    with pytest.raises(ValueError, match="Query too complex"):
        await gql_client._query(mock_client, "query { test }")


@pytest.mark.asyncio
async def test_query_handles_http_error(gql_client):
    """HTTP errors propagate correctly."""
    import httpx

    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )

    with pytest.raises(httpx.HTTPStatusError):
        await gql_client._query(mock_client, "query { test }")


# ── Character Name Resolution Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_character_names_stores_names(gql_client, db_conn):
    """Character names are stored in entity_names table."""
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
                    {
                        "asMoveObject": {
                            "contents": {
                                "json": {
                                    "character_address": "0xwallet2",
                                    "metadata": {"name": "Ghost Protocol"},
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

    stored = await gql_client.fetch_character_names(mock_client)
    assert stored == 2

    row = db_conn.execute(
        "SELECT display_name, tribe_id FROM entity_names WHERE entity_id = ?",
        ("0xwallet1",),
    ).fetchone()
    assert row["display_name"] == "Kai Sunder"
    assert row["tribe_id"] == "98000430"


@pytest.mark.asyncio
async def test_fetch_character_names_skips_empty(gql_client, db_conn):
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
                                    "character_address": "0xwallet1",
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

    stored = await gql_client.fetch_character_names(mock_client)
    assert stored == 0


@pytest.mark.asyncio
async def test_fetch_character_names_upserts(gql_client, db_conn):
    """Existing names are updated on re-fetch."""
    # Seed an existing name
    db_conn.execute(
        "INSERT INTO entity_names (entity_id, display_name, entity_type, updated_at) "
        "VALUES ('0xwallet1', 'Old Name', 'character', 1)",
    )
    db_conn.commit()

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
                                    "metadata": {"name": "New Name"},
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

    stored = await gql_client.fetch_character_names(mock_client)
    assert stored == 1

    row = db_conn.execute(
        "SELECT display_name FROM entity_names WHERE entity_id = ?",
        ("0xwallet1",),
    ).fetchone()
    assert row["display_name"] == "New Name"


@pytest.mark.asyncio
async def test_fetch_character_names_paginates(gql_client, db_conn):
    """Name fetch follows pagination."""
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

    stored = await gql_client.fetch_character_names(mock_client)
    assert stored == 2


@pytest.mark.asyncio
async def test_fetch_character_names_handles_error(gql_client, db_conn):
    """Gracefully handles API errors."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("timeout")

    stored = await gql_client.fetch_character_names(mock_client)
    assert stored == 0

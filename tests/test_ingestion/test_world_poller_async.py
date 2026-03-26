"""Async tests for WorldPoller — poll_static_data, poll_tribes, poll_orbital_zones, check_health.

Uses respx to mock httpx calls with realistic World API responses.
"""

import httpx
import pytest
import respx

from backend.ingestion.world_poller import WorldPoller

BASE_URL = "http://test-world-api"


@pytest.fixture
def poller(db_conn):
    """WorldPoller with test base URL."""
    return WorldPoller(db_conn, base_url=BASE_URL, timeout=5)


# ── poll_static_data ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_static_data_fetches_all_endpoints(poller, db_conn):
    """poll_static_data fetches solarsystems, types, tribes, ships, constellations."""
    with respx.mock:
        # Each endpoint returns a small data set (no pagination needed)
        for endpoint in ["solarsystems", "types", "tribes", "ships", "constellations"]:
            respx.get(f"{BASE_URL}/v2/{endpoint}").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "data": [
                            {"id": f"{endpoint}-1", "name": f"Test {endpoint} 1"},
                            {"id": f"{endpoint}-2", "name": f"Test {endpoint} 2"},
                        ],
                        "metadata": {"total": 2},
                    },
                )
            )

        async with httpx.AsyncClient() as client:
            counts = await poller.poll_static_data(client)

    assert counts["solarsystems"] == 2
    assert counts["types"] == 2
    assert counts["tribes"] == 2
    assert counts["ships"] == 2
    assert counts["constellations"] == 2
    assert sum(counts.values()) == 10

    # Verify data was stored in reference_data
    row = db_conn.execute(
        "SELECT name FROM reference_data WHERE data_type = 'solarsystems' AND data_id = 'solarsystems-1'"
    ).fetchone()
    assert row["name"] == "Test solarsystems 1"


@pytest.mark.asyncio
async def test_poll_static_data_handles_partial_failure(poller, db_conn):
    """poll_static_data continues on failure of individual endpoints."""
    with respx.mock:
        respx.get(f"{BASE_URL}/v2/solarsystems").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "sys-1", "name": "Alpha"}], "metadata": {"total": 1}},
            )
        )
        # types endpoint fails
        respx.get(f"{BASE_URL}/v2/types").mock(
            return_value=httpx.Response(500)
        )
        respx.get(f"{BASE_URL}/v2/tribes").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "t-1", "name": "Tribe 1"}], "metadata": {"total": 1}},
            )
        )
        respx.get(f"{BASE_URL}/v2/ships").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "s-1", "name": "Ship 1"}], "metadata": {"total": 1}},
            )
        )
        respx.get(f"{BASE_URL}/v2/constellations").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "c-1", "name": "Const 1"}], "metadata": {"total": 1}},
            )
        )

        async with httpx.AsyncClient() as client:
            counts = await poller.poll_static_data(client)

    assert counts["solarsystems"] == 1
    assert counts["types"] == 0  # failed
    assert counts["tribes"] == 1


@pytest.mark.asyncio
async def test_poll_static_data_empty_base_url(db_conn):
    """poll_static_data returns {} when no base_url."""
    poller = WorldPoller(db_conn, base_url="")
    result = await poller.poll_static_data(None)
    assert result == {}


# ── _fetch_paginated ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_paginated_follows_pagination(poller, db_conn):
    """_fetch_paginated follows pagination when total > PAGE_LIMIT."""
    with respx.mock:
        # Page 1: total=3, offset=0
        respx.get(f"{BASE_URL}/v2/types").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "data": [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}],
                        "metadata": {"total": 3},
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "data": [{"id": "3", "name": "C"}],
                        "metadata": {"total": 3},
                    },
                ),
            ]
        )

        async with httpx.AsyncClient() as client:
            # Use PAGE_LIMIT=2 to force pagination
            from backend.ingestion import world_poller
            original_limit = world_poller.PAGE_LIMIT
            world_poller.PAGE_LIMIT = 2
            try:
                count = await poller._fetch_paginated(client, "types", "/v2/types")
            finally:
                world_poller.PAGE_LIMIT = original_limit

    assert count == 3

    # Verify all items stored
    rows = db_conn.execute(
        "SELECT COUNT(*) FROM reference_data WHERE data_type = 'types'"
    ).fetchone()
    assert rows[0] == 3


@pytest.mark.asyncio
async def test_fetch_paginated_non_dict_body(poller, db_conn):
    """_fetch_paginated handles non-dict response body (raw list)."""
    with respx.mock:
        respx.get(f"{BASE_URL}/v2/types").mock(
            return_value=httpx.Response(
                200,
                json=[{"id": "1", "name": "Alpha"}, {"id": "2", "name": "Beta"}],
            )
        )

        async with httpx.AsyncClient() as client:
            count = await poller._fetch_paginated(client, "types", "/v2/types")

    assert count == 2


@pytest.mark.asyncio
async def test_fetch_paginated_non_list_data(poller, db_conn):
    """_fetch_paginated wraps non-list data in a list."""
    with respx.mock:
        respx.get(f"{BASE_URL}/v2/types").mock(
            return_value=httpx.Response(
                200,
                json={"id": "single", "name": "Singleton"},
            )
        )

        async with httpx.AsyncClient() as client:
            count = await poller._fetch_paginated(client, "types", "/v2/types")

    assert count == 1


# ── poll_tribes ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_tribes_stores_and_marks_stale(poller, db_conn):
    """poll_tribes stores tribes and marks unseen ones as stale."""
    # Pre-seed a tribe that won't appear in the API response
    poller.store_tribe({"id": "old-tribe", "name": "Gone", "nameShort": "GN", "memberCount": 1, "taxRate": 0.0})
    db_conn.execute(
        "UPDATE tribe_cache SET last_confirmed_at = 0 WHERE tribe_id = 'old-tribe'"
    )
    db_conn.commit()

    with respx.mock:
        respx.get(f"{BASE_URL}/v2/tribes").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "tribe-1", "name": "Raiders", "nameShort": "RDR", "memberCount": 42, "taxRate": 0.1},
                        {"id": "tribe-2", "name": "Nomads", "nameShort": "NMD", "memberCount": 15, "taxRate": 0.0},
                    ],
                    "metadata": {"total": 2},
                },
            )
        )

        async with httpx.AsyncClient() as client:
            count = await poller.poll_tribes(client)

    assert count == 2

    # Verify stored
    row = db_conn.execute("SELECT * FROM tribe_cache WHERE tribe_id = 'tribe-1'").fetchone()
    assert row["name"] == "Raiders"
    assert row["member_count"] == 42

    # old-tribe should be stale (last_confirmed_at=0, well over 1 hour ago)
    old = db_conn.execute("SELECT is_stale FROM tribe_cache WHERE tribe_id = 'old-tribe'").fetchone()
    assert old["is_stale"] == 1


@pytest.mark.asyncio
async def test_poll_tribes_pagination(poller, db_conn):
    """poll_tribes follows pagination."""
    with respx.mock:
        from backend.ingestion import world_poller
        original_limit = world_poller.PAGE_LIMIT
        world_poller.PAGE_LIMIT = 1

        try:
            respx.get(f"{BASE_URL}/v2/tribes").mock(
                side_effect=[
                    httpx.Response(
                        200,
                        json={
                            "data": [{"id": "t1", "name": "A", "nameShort": "A", "memberCount": 1, "taxRate": 0}],
                            "metadata": {"total": 2},
                        },
                    ),
                    httpx.Response(
                        200,
                        json={
                            "data": [{"id": "t2", "name": "B", "nameShort": "B", "memberCount": 2, "taxRate": 0}],
                            "metadata": {"total": 2},
                        },
                    ),
                ]
            )

            async with httpx.AsyncClient() as client:
                count = await poller.poll_tribes(client)
        finally:
            world_poller.PAGE_LIMIT = original_limit

    assert count == 2


@pytest.mark.asyncio
async def test_poll_tribes_http_error(poller, db_conn):
    """poll_tribes raises on HTTP error."""
    with respx.mock:
        respx.get(f"{BASE_URL}/v2/tribes").mock(
            return_value=httpx.Response(500)
        )

        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.HTTPStatusError):
                await poller.poll_tribes(client)


# ── poll_orbital_zones ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_orbital_zones_stores_zones(poller, db_conn):
    """poll_orbital_zones upserts zones into orbital_zones table."""
    with respx.mock:
        respx.get(f"{BASE_URL}/v2/orbitalzones").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "zone-1",
                            "name": "Danger Zone",
                            "solarSystemId": "30012602",
                            "feralAiTier": 3,
                            "threatLevel": "high",
                        },
                        {
                            "id": "zone-2",
                            "name": "Safe Haven",
                            "solarSystemId": "30012603",
                            "feralAiTier": 0,
                            "threatLevel": "low",
                        },
                    ],
                    "metadata": {"total": 2},
                },
            )
        )

        async with httpx.AsyncClient() as client:
            count = await poller.poll_orbital_zones(client)

    assert count == 2

    row = db_conn.execute("SELECT * FROM orbital_zones WHERE zone_id = 'zone-1'").fetchone()
    assert row["zone_name"] == "Danger Zone"
    assert row["system_id"] == "30012602"
    assert row["feral_ai_tier"] == 3
    assert row["threat_level"] == "high"


@pytest.mark.asyncio
async def test_poll_orbital_zones_skips_no_id(poller, db_conn):
    """Zones without an id are skipped."""
    with respx.mock:
        respx.get(f"{BASE_URL}/v2/orbitalzones").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"name": "NoID Zone"},  # no id field
                        {"id": "zone-ok", "name": "Has ID"},
                    ],
                    "metadata": {"total": 2},
                },
            )
        )

        async with httpx.AsyncClient() as client:
            count = await poller.poll_orbital_zones(client)

    # Only the zone with id is counted
    assert count == 1


@pytest.mark.asyncio
async def test_poll_orbital_zones_http_error(poller, db_conn):
    """poll_orbital_zones handles HTTP error gracefully (breaks loop, returns 0)."""
    with respx.mock:
        respx.get(f"{BASE_URL}/v2/orbitalzones").mock(
            return_value=httpx.Response(500)
        )

        async with httpx.AsyncClient() as client:
            count = await poller.poll_orbital_zones(client)

    assert count == 0


@pytest.mark.asyncio
async def test_poll_orbital_zones_upsert(poller, db_conn):
    """poll_orbital_zones updates existing zones on conflict."""
    # First poll
    with respx.mock:
        respx.get(f"{BASE_URL}/v2/orbitalzones").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [{"id": "z1", "name": "Old Name", "solarSystemId": "sys1", "feralAiTier": 1, "threatLevel": "low"}],
                    "metadata": {"total": 1},
                },
            )
        )
        async with httpx.AsyncClient() as client:
            await poller.poll_orbital_zones(client)

    # Second poll with updated data
    with respx.mock:
        respx.get(f"{BASE_URL}/v2/orbitalzones").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [{"id": "z1", "name": "New Name", "solarSystemId": "sys1", "feralAiTier": 5, "threatLevel": "critical"}],
                    "metadata": {"total": 1},
                },
            )
        )
        async with httpx.AsyncClient() as client:
            await poller.poll_orbital_zones(client)

    row = db_conn.execute("SELECT * FROM orbital_zones WHERE zone_id = 'z1'").fetchone()
    assert row["zone_name"] == "New Name"
    assert row["feral_ai_tier"] == 5
    assert row["threat_level"] == "critical"


# ── check_health ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_health_available(poller):
    """check_health returns available=True on 200."""
    with respx.mock:
        respx.get(f"{BASE_URL}/health").mock(
            return_value=httpx.Response(200)
        )

        async with httpx.AsyncClient() as client:
            result = await poller.check_health(client)

    assert result["available"] is True
    assert result["status_code"] == 200


@pytest.mark.asyncio
async def test_check_health_server_error(poller):
    """check_health returns available=False on non-200."""
    with respx.mock:
        respx.get(f"{BASE_URL}/health").mock(
            return_value=httpx.Response(503)
        )

        async with httpx.AsyncClient() as client:
            result = await poller.check_health(client)

    assert result["available"] is False
    assert result["status_code"] == 503


@pytest.mark.asyncio
async def test_check_health_connection_error(poller):
    """check_health returns available=False with error on connection failure."""
    with respx.mock:
        respx.get(f"{BASE_URL}/health").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        async with httpx.AsyncClient() as client:
            result = await poller.check_health(client)

    assert result["available"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_check_health_no_base_url(db_conn):
    """check_health returns unavailable when no base_url configured."""
    poller = WorldPoller(db_conn, base_url="")
    result = await poller.check_health(None)
    assert result["available"] is False
    assert "no base_url" in result["reason"]


# ── _store_reference ─────────────────────────────────────────────────────────


def test_store_reference_uses_solarSystemId(poller, db_conn):
    """_store_reference extracts solarSystemId for id."""
    poller._store_reference("solarsystems", {"solarSystemId": "30012602", "solarSystemName": "Alpha"})
    db_conn.commit()

    row = db_conn.execute(
        "SELECT * FROM reference_data WHERE data_type = 'solarsystems' AND data_id = '30012602'"
    ).fetchone()
    assert row is not None
    assert row["name"] == "Alpha"


def test_store_reference_uses_typeId(poller, db_conn):
    """_store_reference extracts typeId for id."""
    poller._store_reference("types", {"typeId": "123", "name": "Frigate"})
    db_conn.commit()

    row = db_conn.execute(
        "SELECT * FROM reference_data WHERE data_type = 'types' AND data_id = '123'"
    ).fetchone()
    assert row["name"] == "Frigate"


def test_store_reference_upsert(poller, db_conn):
    """_store_reference updates existing entries on conflict."""
    poller._store_reference("types", {"id": "1", "name": "Old"})
    db_conn.commit()
    poller._store_reference("types", {"id": "1", "name": "New"})
    db_conn.commit()

    row = db_conn.execute(
        "SELECT name FROM reference_data WHERE data_type = 'types' AND data_id = '1'"
    ).fetchone()
    assert row["name"] == "New"

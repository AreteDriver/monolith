"""Tests for main.py background loops and helper functions.

Tests the async loop functions that run in the background during the
application lifespan. Each loop is tested for one iteration (cancelled
after first sleep) to verify correct behavior.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.main import (
    chain_poll_loop,
    detection_loop,
    graphql_enrichment_loop,
    snapshot_loop,
    static_data_loop,
    table_prune_loop,
    warden_loop,
)

# ── chain_poll_loop ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chain_poll_loop_polls_and_processes():
    """chain_poll_loop calls reader.poll() then processor.process_unprocessed()."""
    reader = MagicMock()
    reader.poll = AsyncMock(return_value=5)
    processor = MagicMock()
    processor.process_unprocessed.return_value = 3

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await chain_poll_loop(reader, processor, interval=30, client=None)

    reader.poll.assert_called()
    processor.process_unprocessed.assert_called()


@pytest.mark.asyncio
async def test_chain_poll_loop_handles_exception():
    """chain_poll_loop catches exceptions and continues."""
    reader = MagicMock()
    reader.poll = AsyncMock(side_effect=[RuntimeError("chain error"), 0])
    processor = MagicMock()
    processor.process_unprocessed.return_value = 0

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await chain_poll_loop(reader, processor, interval=30)

    # Should have been called at least once despite error
    assert reader.poll.call_count >= 1


@pytest.mark.asyncio
async def test_chain_poll_loop_zero_stored():
    """chain_poll_loop runs quietly when no new events."""
    reader = MagicMock()
    reader.poll = AsyncMock(return_value=0)
    processor = MagicMock()
    processor.process_unprocessed.return_value = 0

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await chain_poll_loop(reader, processor, interval=30)


# ── snapshot_loop ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_loop_processes():
    """snapshot_loop calls snapshotter.process_all_objects()."""
    snapshotter = MagicMock()
    snapshotter.process_all_objects.return_value = 2

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await snapshot_loop(snapshotter, interval=900)

    snapshotter.process_all_objects.assert_called_once()


@pytest.mark.asyncio
async def test_snapshot_loop_handles_exception():
    """snapshot_loop catches exceptions."""
    snapshotter = MagicMock()
    snapshotter.process_all_objects.side_effect = RuntimeError("db locked")

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await snapshot_loop(snapshotter, interval=900)


# ── detection_loop ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detection_loop_runs_cycle():
    """detection_loop calls engine.run_cycle() and processes anomalies."""
    engine = MagicMock()
    engine.run_cycle.return_value = [
        {
            "severity": "CRITICAL",
            "anomaly_type": "OWNERSHIP_TRANSFER",
            "object_id": "0xabc123456789",
            "evidence": {"description": "Suspicious transfer detected"},
        }
    ]

    settings = MagicMock()
    settings.discord_webhook_url = ""
    settings.discord_rate_limit = 5
    settings.github_repo = ""
    settings.github_token = ""

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # First sleep is the 30s startup delay, second is the loop interval
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await detection_loop(engine, interval=300, settings=settings, conn=None)

    engine.run_cycle.assert_called_once()


@pytest.mark.asyncio
async def test_detection_loop_no_anomalies():
    """detection_loop handles empty result from run_cycle."""
    engine = MagicMock()
    engine.run_cycle.return_value = []

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await detection_loop(engine, interval=300)


@pytest.mark.asyncio
async def test_detection_loop_handles_exception():
    """detection_loop catches exceptions."""
    engine = MagicMock()
    engine.run_cycle.side_effect = RuntimeError("db error")

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await detection_loop(engine, interval=300)


@pytest.mark.asyncio
async def test_detection_loop_discord_alert():
    """detection_loop sends Discord alert for CRITICAL/HIGH anomalies."""
    engine = MagicMock()
    engine.run_cycle.return_value = [
        {
            "severity": "HIGH",
            "anomaly_type": "FUEL_DRAIN",
            "object_id": "0xabc123456789",
            "evidence": {"description": "Rapid fuel drain"},
        }
    ]

    settings = MagicMock()
    settings.discord_webhook_url = "https://discord.com/api/webhooks/test"
    settings.discord_rate_limit = 5
    settings.github_repo = ""
    settings.github_token = ""

    with (
        patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("backend.main.send_alert", new_callable=AsyncMock) as mock_alert,
        patch("backend.main.dispatch_to_subscribers", new_callable=AsyncMock),
    ):
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await detection_loop(engine, interval=300, settings=settings, conn=None)

    mock_alert.assert_called_once()


# ── graphql_enrichment_loop ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graphql_enrichment_loop_runs_all():
    """graphql_enrichment_loop calls all enrichment methods."""
    gql_client = MagicMock()
    gql_client.enrich_locations = AsyncMock(return_value=5)
    gql_client.audit_object_versions = AsyncMock(return_value=3)
    gql_client.poll_config_singletons = AsyncMock(return_value=2)
    gql_client.profile_wallet_activity = AsyncMock(return_value=1)

    name_resolver = MagicMock()
    name_resolver._fetch_characters = AsyncMock(return_value=10)

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # First sleep is the 120s startup delay, second is the loop interval
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await graphql_enrichment_loop(gql_client, name_resolver, interval=3600, client=None)

    gql_client.enrich_locations.assert_called_once()
    gql_client.audit_object_versions.assert_called_once()
    gql_client.poll_config_singletons.assert_called_once()
    gql_client.profile_wallet_activity.assert_called_once()
    name_resolver._fetch_characters.assert_called_once()


@pytest.mark.asyncio
async def test_graphql_enrichment_loop_handles_exception():
    """graphql_enrichment_loop catches exceptions."""
    gql_client = MagicMock()
    gql_client.enrich_locations = AsyncMock(side_effect=RuntimeError("graphql down"))

    name_resolver = MagicMock()

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await graphql_enrichment_loop(gql_client, name_resolver, interval=3600)


# ── warden_loop ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_warden_loop_completed():
    """warden_loop processes completed results."""
    warden = MagicMock()
    warden.run_cycle = AsyncMock(return_value={"status": "completed", "verified": 2, "dismissed": 1})

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await warden_loop(warden, interval=300)

    warden.run_cycle.assert_called_once()


@pytest.mark.asyncio
async def test_warden_loop_paused():
    """warden_loop waits longer when paused."""
    warden = MagicMock()
    warden.run_cycle = AsyncMock(return_value={"status": "paused"})

    sleep_calls = []

    async def track_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError()

    with patch("backend.main.asyncio.sleep", side_effect=track_sleep):
        with pytest.raises(asyncio.CancelledError):
            await warden_loop(warden, interval=300)

    # First sleep is startup delay (120), second should be interval*10 (3000)
    assert sleep_calls[0] == 120  # startup delay
    assert sleep_calls[1] == 3000  # paused → longer wait


@pytest.mark.asyncio
async def test_warden_loop_handles_exception():
    """warden_loop catches exceptions."""
    warden = MagicMock()
    warden.run_cycle = AsyncMock(side_effect=RuntimeError("sui rpc down"))

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await warden_loop(warden, interval=300)


# ── table_prune_loop ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_table_prune_loop_prunes_old_data(db_conn):
    """table_prune_loop deletes old world_states and state_transitions."""
    now = int(time.time())

    # Seed objects to satisfy foreign key constraints
    for i in range(6):
        db_conn.execute(
            "INSERT OR IGNORE INTO objects (object_id, object_type, last_seen) VALUES (?, 'gate', ?)",
            (f"obj-{i}", now),
        )
    db_conn.execute(
        "INSERT OR IGNORE INTO objects (object_id, object_type, last_seen) VALUES ('obj-recent', 'gate', ?)",
        (now,),
    )
    db_conn.commit()

    # Insert old world_states (older than 7 days)
    old_time = now - (8 * 86400)
    for i in range(5):
        db_conn.execute(
            "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
            "VALUES (?, 'gate', '{}', ?, 'world_api')",
            (f"obj-{i}", old_time + i),
        )
    # Insert recent world_states (should be kept)
    db_conn.execute(
        "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
        "VALUES ('obj-recent', 'gate', '{}', ?, 'world_api')",
        (now,),
    )
    # Insert old state_transitions (older than 30 days)
    old_transition_time = now - (31 * 86400)
    db_conn.execute(
        "INSERT INTO state_transitions (object_id, from_state, to_state, timestamp) "
        "VALUES ('obj-1', 'a', 'b', ?)",
        (old_transition_time,),
    )
    # Insert recent state_transition
    db_conn.execute(
        "INSERT INTO state_transitions (object_id, from_state, to_state, timestamp) "
        "VALUES ('obj-1', 'b', 'c', ?)",
        (now,),
    )
    db_conn.commit()

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # First sleep is the 300s startup delay, second is after first prune
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await table_prune_loop(db_conn, interval=21600)

    # Recent world_state should remain
    recent = db_conn.execute(
        "SELECT COUNT(*) FROM world_states WHERE object_id = 'obj-recent'"
    ).fetchone()
    assert recent[0] == 1

    # Old state_transition should be pruned
    old_transitions = db_conn.execute(
        "SELECT COUNT(*) FROM state_transitions WHERE timestamp < ?",
        (now - 30 * 86400,),
    ).fetchone()
    assert old_transitions[0] == 0

    # Recent state_transition should remain
    recent_transitions = db_conn.execute(
        "SELECT COUNT(*) FROM state_transitions WHERE timestamp >= ?",
        (now - 30 * 86400,),
    ).fetchone()
    assert recent_transitions[0] == 1


@pytest.mark.asyncio
async def test_table_prune_loop_handles_exception(db_conn):
    """table_prune_loop catches exceptions."""
    # Close connection to force an error
    conn = MagicMock()
    conn.execute.side_effect = RuntimeError("db locked")

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await table_prune_loop(conn, interval=21600)


@pytest.mark.asyncio
async def test_table_prune_loop_no_old_data(db_conn):
    """table_prune_loop does nothing when there's no old data."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO world_states (object_id, object_type, state_data, snapshot_time, source) "
        "VALUES ('obj-1', 'gate', '{}', ?, 'world_api')",
        (now,),
    )
    db_conn.commit()

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await table_prune_loop(db_conn, interval=21600)

    # Recent data untouched
    count = db_conn.execute("SELECT COUNT(*) FROM world_states").fetchone()
    assert count[0] == 1


# ── static_data_loop ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_static_data_loop_calls_all_pollers():
    """static_data_loop calls poll_static_data, poll_tribes, poll_orbital_zones."""
    poller = MagicMock()
    poller.poll_static_data = AsyncMock(return_value={"solarsystems": 10, "types": 5})
    poller.poll_tribes = AsyncMock(return_value=3)
    poller.poll_orbital_zones = AsyncMock(return_value=2)

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # Sleeps: 15s startup, 2s per endpoint inside poll_static_data (mocked),
        # 5s pause, tribes, 5s pause, orbital zones, then interval sleep -> cancel
        mock_sleep.side_effect = [
            None,   # 15s startup
            None,   # 5s pause before tribes
            None,   # 5s pause before orbital zones
            asyncio.CancelledError(),  # interval sleep
        ]
        with pytest.raises(asyncio.CancelledError):
            await static_data_loop(poller, interval=3600, client=None)

    poller.poll_static_data.assert_called_once()
    poller.poll_tribes.assert_called_once()
    poller.poll_orbital_zones.assert_called_once()


@pytest.mark.asyncio
async def test_static_data_loop_handles_exception():
    """static_data_loop catches exceptions from each poller."""
    poller = MagicMock()
    poller.poll_static_data = AsyncMock(side_effect=RuntimeError("api down"))
    poller.poll_tribes = AsyncMock(side_effect=RuntimeError("api down"))
    poller.poll_orbital_zones = AsyncMock(side_effect=RuntimeError("api down"))

    with patch("backend.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, None, None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await static_data_loop(poller, interval=3600)

    # All three pollers were attempted despite errors
    poller.poll_static_data.assert_called()
    poller.poll_tribes.assert_called()
    poller.poll_orbital_zones.assert_called()


# ── _check_sui_rpc ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_sui_rpc_ok():
    """_check_sui_rpc returns 'ok' on successful response."""
    import httpx as _httpx
    import respx

    from backend.main import _check_sui_rpc

    with respx.mock:
        respx.post("https://test-rpc.io").mock(
            return_value=_httpx.Response(200, json={"jsonrpc": "2.0", "result": "100"})
        )
        result = await _check_sui_rpc("https://test-rpc.io")

    assert result == "ok"


@pytest.mark.asyncio
async def test_check_sui_rpc_error():
    """_check_sui_rpc returns 'unreachable' on connection error."""
    import respx

    from backend.main import _check_sui_rpc

    with respx.mock:
        respx.post("https://test-rpc.io").mock(
            side_effect=httpx.ConnectError("timeout")
        )
        result = await _check_sui_rpc("https://test-rpc.io")

    assert result == "unreachable"


@pytest.mark.asyncio
async def test_check_sui_rpc_non_200():
    """_check_sui_rpc returns http_STATUS on non-200."""
    import httpx as _httpx
    import respx

    from backend.main import _check_sui_rpc

    with respx.mock:
        respx.post("https://test-rpc.io").mock(
            return_value=_httpx.Response(503)
        )
        result = await _check_sui_rpc("https://test-rpc.io")

    assert result == "http_503"

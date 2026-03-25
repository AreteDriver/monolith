"""Tests for subscription_dispatch — build embeds, filter matching, dispatch."""

import json
import time

import httpx
import pytest
import respx

from backend.alerts.subscription_dispatch import (
    _build_embed,
    _matches_filters,
    _truncate,
    dispatch_to_subscribers,
)
from backend.db.database import init_db


@pytest.fixture
def db_conn():
    conn = init_db(":memory:")
    yield conn
    conn.close()


def _make_anomaly(**overrides):
    base = {
        "anomaly_id": "MNLT-001",
        "anomaly_type": "ORPHAN_OBJECT",
        "severity": "HIGH",
        "object_id": "0xabcdef1234567890abcdef1234567890abcdef12",
        "detector": "continuity_checker",
        "rule_id": "C1",
        "evidence": {"description": "Ghost object found"},
    }
    base.update(overrides)
    return base


def _insert_subscription(conn, sub_id, webhook_url, severity_filter=None, event_types=None):
    now = int(time.time())
    conn.execute(
        "INSERT INTO subscriptions (sub_id, webhook_url, severity_filter, event_types, "
        "created_at, active) VALUES (?, ?, ?, ?, ?, 1)",
        (
            sub_id,
            webhook_url,
            json.dumps(severity_filter or []),
            json.dumps(event_types or []),
            now,
        ),
    )
    conn.commit()


# --- _truncate ---


def test_truncate_short():
    assert _truncate("hello", 10) == "hello"


def test_truncate_long():
    assert _truncate("a" * 20, 10) == "aaaaaaa..."
    assert len(_truncate("a" * 20, 10)) == 10


# --- _build_embed ---


def test_build_embed_critical():
    embed = _build_embed(_make_anomaly(severity="CRITICAL"))
    assert "CRITICAL" in embed["title"]
    assert embed["color"] == 0xFF0000


def test_build_embed_fields():
    embed = _build_embed(_make_anomaly())
    field_names = [f["name"] for f in embed["fields"]]
    assert "Anomaly ID" in field_names
    assert "Object" in field_names
    assert "Detector" in field_names
    assert "Rule" in field_names


def test_build_embed_missing_fields():
    embed = _build_embed({})
    assert "LOW" in embed["title"]
    assert embed["color"] == 0x808080


# --- _matches_filters ---


def test_matches_no_filters():
    assert _matches_filters(_make_anomaly(), [], []) is True


def test_matches_severity_filter_pass():
    assert _matches_filters(_make_anomaly(severity="HIGH"), ["HIGH", "CRITICAL"], []) is True


def test_matches_severity_filter_fail():
    assert _matches_filters(_make_anomaly(severity="LOW"), ["HIGH", "CRITICAL"], []) is False


def test_matches_event_type_filter_pass():
    assert _matches_filters(_make_anomaly(anomaly_type="ORPHAN_OBJECT"), [], ["ORPHAN_OBJECT"])


def test_matches_event_type_filter_fail():
    assert not _matches_filters(_make_anomaly(anomaly_type="ORPHAN_OBJECT"), [], ["RESURRECTION"])


def test_matches_both_filters():
    anomaly = _make_anomaly(severity="CRITICAL", anomaly_type="RESURRECTION")
    assert _matches_filters(anomaly, ["CRITICAL"], ["RESURRECTION"]) is True
    assert _matches_filters(anomaly, ["LOW"], ["RESURRECTION"]) is False


# --- dispatch_to_subscribers ---


@pytest.mark.asyncio
async def test_dispatch_no_subscriptions(db_conn):
    result = await dispatch_to_subscribers(db_conn, _make_anomaly())
    assert result == 0


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_sends_to_matching_subscriber(db_conn):
    url = "https://hooks.example.com/webhook1"
    _insert_subscription(db_conn, "sub-1", url)
    respx.post(url).mock(return_value=httpx.Response(204))
    result = await dispatch_to_subscribers(db_conn, _make_anomaly())
    assert result == 1


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_skips_filtered_out_subscriber(db_conn):
    url = "https://hooks.example.com/webhook2"
    _insert_subscription(db_conn, "sub-2", url, severity_filter=["CRITICAL"])
    respx.post(url).mock(return_value=httpx.Response(204))
    result = await dispatch_to_subscribers(db_conn, _make_anomaly(severity="LOW"))
    assert result == 0


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_handles_webhook_failure(db_conn):
    url = "https://hooks.example.com/webhook3"
    _insert_subscription(db_conn, "sub-3", url)
    respx.post(url).mock(return_value=httpx.Response(500))
    result = await dispatch_to_subscribers(db_conn, _make_anomaly())
    assert result == 0


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_handles_network_error(db_conn):
    url = "https://hooks.example.com/webhook4"
    _insert_subscription(db_conn, "sub-4", url)
    respx.post(url).mock(side_effect=httpx.ConnectError("down"))
    result = await dispatch_to_subscribers(db_conn, _make_anomaly())
    assert result == 0


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_invalid_json_filters(db_conn):
    """Malformed JSON in filter columns should not crash dispatch."""
    now = int(time.time())
    db_conn.execute(
        "INSERT INTO subscriptions (sub_id, webhook_url, severity_filter, event_types, "
        "created_at, active) VALUES (?, ?, ?, ?, ?, 1)",
        ("sub-5", "https://hooks.example.com/wh5", "not-json", "{bad}", now),
    )
    db_conn.commit()
    respx.post("https://hooks.example.com/wh5").mock(return_value=httpx.Response(200))
    result = await dispatch_to_subscribers(db_conn, _make_anomaly())
    assert result == 1

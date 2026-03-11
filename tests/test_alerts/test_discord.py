"""Tests for Discord alerter."""

import pytest

from backend.alerts.discord import _last_sent, send_alert


def _sample_anomaly(severity="CRITICAL"):
    return {
        "anomaly_id": "MNL-20260311-0001",
        "anomaly_type": "RESURRECTION",
        "severity": severity,
        "object_id": "0xabcdef1234567890",
        "detector": "continuity_checker",
        "rule_id": "C2",
        "evidence": {"description": "Destroyed object reappeared"},
    }


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    _last_sent.clear()
    yield
    _last_sent.clear()


@pytest.mark.asyncio
async def test_no_webhook_url():
    """Returns False when no webhook URL configured."""
    result = await send_alert("", _sample_anomaly())
    assert result is False


@pytest.mark.asyncio
async def test_low_severity_skipped():
    """LOW severity anomalies are not sent."""
    result = await send_alert("https://discord.com/api/webhooks/fake", _sample_anomaly("LOW"))
    assert result is False


@pytest.mark.asyncio
async def test_medium_severity_skipped():
    """MEDIUM severity anomalies are not sent."""
    result = await send_alert("https://discord.com/api/webhooks/fake", _sample_anomaly("MEDIUM"))
    assert result is False


@pytest.mark.asyncio
async def test_successful_send(respx_mock):
    """CRITICAL anomaly sends Discord embed."""
    url = "https://discord.com/api/webhooks/test/token"
    respx_mock.post(url).respond(204)

    result = await send_alert(url, _sample_anomaly())
    assert result is True


@pytest.mark.asyncio
async def test_rate_limit_enforced(respx_mock):
    """Rate limit prevents excessive sends."""
    import time

    url = "https://discord.com/api/webhooks/test/token"
    respx_mock.post(url).respond(204)

    # Fill rate limit
    now = time.time()
    _last_sent.extend([now] * 5)

    result = await send_alert(url, _sample_anomaly(), rate_limit=5)
    assert result is False


@pytest.mark.asyncio
async def test_webhook_error_returns_false(respx_mock):
    """Non-200 response returns False."""
    url = "https://discord.com/api/webhooks/test/token"
    respx_mock.post(url).respond(429, text="Rate limited")

    result = await send_alert(url, _sample_anomaly())
    assert result is False


@pytest.mark.asyncio
async def test_high_severity_sent(respx_mock):
    """HIGH severity anomalies are sent."""
    url = "https://discord.com/api/webhooks/test/token"
    respx_mock.post(url).respond(204)

    result = await send_alert(url, _sample_anomaly("HIGH"))
    assert result is True

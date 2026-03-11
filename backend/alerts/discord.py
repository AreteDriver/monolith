"""Discord alerter — sends CRITICAL/HIGH anomaly alerts via webhook."""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

# Severity → Discord embed color (decimal)
SEVERITY_COLORS = {
    "CRITICAL": 0xFF0000,  # Red
    "HIGH": 0xFF8C00,  # Dark orange
    "MEDIUM": 0xFFD700,  # Gold
    "LOW": 0x808080,  # Gray
}

# Rate limit tracking
_last_sent: list[float] = []


async def send_alert(
    webhook_url: str,
    anomaly: dict,
    rate_limit: int = 5,
) -> bool:
    """Send a Discord embed for a detected anomaly.

    Returns True if sent, False if rate-limited or failed.
    Only sends for CRITICAL and HIGH severity by default.
    """
    if not webhook_url:
        return False

    severity = anomaly.get("severity", "LOW")
    if severity not in ("CRITICAL", "HIGH"):
        return False

    # Rate limit: max N messages per 60 seconds
    now = time.time()
    _last_sent[:] = [t for t in _last_sent if now - t < 60]
    if len(_last_sent) >= rate_limit:
        logger.warning("Discord rate limit reached (%d/min), skipping alert", rate_limit)
        return False

    evidence = anomaly.get("evidence", {})
    description = evidence.get("description", anomaly.get("anomaly_type", "Unknown"))

    embed = {
        "title": f"🚨 {severity}: {anomaly['anomaly_type']}",
        "description": description[:200],
        "color": SEVERITY_COLORS.get(severity, 0x808080),
        "fields": [
            {
                "name": "Anomaly ID",
                "value": f"`{anomaly.get('anomaly_id', 'N/A')}`",
                "inline": True,
            },
            {
                "name": "Object",
                "value": f"`{_truncate(anomaly.get('object_id', 'N/A'), 20)}`",
                "inline": True,
            },
            {
                "name": "Detector",
                "value": anomaly.get("detector", "unknown"),
                "inline": True,
            },
            {
                "name": "Rule",
                "value": anomaly.get("rule_id", "N/A"),
                "inline": True,
            },
        ],
        "footer": {"text": "MONOLITH v0.1.0 — EVE Frontier Blockchain Integrity Monitor"},
    }

    payload = {"embeds": [embed]}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=10)
            if resp.status_code in (200, 204):
                _last_sent.append(now)
                logger.info("Discord alert sent: %s %s", severity, anomaly["anomaly_type"])
                return True
            logger.warning("Discord webhook returned %d: %s", resp.status_code, resp.text[:200])
            return False
    except Exception:
        logger.exception("Discord alert failed")
        return False


def _truncate(val: str, max_len: int) -> str:
    if len(val) <= max_len:
        return val
    return val[: max_len - 3] + "..."

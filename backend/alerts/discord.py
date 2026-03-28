"""Discord alerter — sends anomaly intercepts via webhook."""

import logging
import time

import httpx

from backend.detection.anomaly_scorer import RULE_DISPLAY

logger = logging.getLogger(__name__)

# Severity → Discord embed color (decimal)
SEVERITY_COLORS = {
    "CRITICAL": 0xFF0000,  # Red — hostile contact
    "HIGH": 0xFF8C00,  # Amber — threat detected
    "MEDIUM": 0xFFD700,  # Gold — anomaly flagged
    "LOW": 0x808080,  # Gray — noise
}

# Severity → prefix for Discord titles
SEVERITY_PREFIX = {
    "CRITICAL": "PRIORITY INTERCEPT",
    "HIGH": "SIGNAL FLAGGED",
    "MEDIUM": "ANOMALY LOGGED",
    "LOW": "NOISE",
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
    Sends for all severity levels (demo mode).
    """
    if not webhook_url:
        return False

    severity = anomaly.get("severity", "LOW")
    if severity not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        return False

    # Rate limit: max N messages per 60 seconds
    now = time.time()
    _last_sent[:] = [t for t in _last_sent if now - t < 60]
    if len(_last_sent) >= rate_limit:
        logger.warning("Discord rate limit reached (%d/min), skipping alert", rate_limit)
        return False

    evidence = anomaly.get("evidence", {})
    rule_id = anomaly.get("rule_id", "")
    rule_entry = RULE_DISPLAY.get(rule_id)
    frontier_name = rule_entry[0] if rule_entry else anomaly["anomaly_type"]
    tagline = rule_entry[1] if rule_entry else ""

    description = tagline or evidence.get("description", anomaly.get("anomaly_type", "Unknown"))
    prefix = SEVERITY_PREFIX.get(severity, "SIGNAL")

    embed = {
        "title": f"{prefix}: {frontier_name}",
        "description": description[:200],
        "color": SEVERITY_COLORS.get(severity, 0x808080),
        "fields": [
            {
                "name": "Intercept ID",
                "value": f"`{anomaly.get('anomaly_id', 'N/A')}`",
                "inline": True,
            },
            {
                "name": "Target",
                "value": f"`{_truncate(anomaly.get('object_id', 'N/A'), 20)}`",
                "inline": True,
            },
            {
                "name": "Source",
                "value": anomaly.get("detector", "unknown"),
                "inline": True,
            },
            {
                "name": "Classification",
                "value": f"{rule_id} — {severity}",
                "inline": True,
            },
        ],
        "footer": {"text": "MONOLITH — Frontier Chain Intelligence"},
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
    except (httpx.HTTPError, OSError):
        logger.exception("Discord alert failed")
        return False


def _truncate(val: str, max_len: int) -> str:
    if len(val) <= max_len:
        return val
    return val[: max_len - 3] + "..."

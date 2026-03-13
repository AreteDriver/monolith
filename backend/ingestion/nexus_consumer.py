"""NEXUS webhook consumer — receives enriched events from WatchTower.

Ingests killmail and gate transit events pre-enriched with entity names
and system names, reducing duplicate Sui indexing.
"""

import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, Header, Request

router = APIRouter()
logger = logging.getLogger(__name__)

# Set via MONOLITH_NEXUS_SECRET env var (from NEXUS subscription response)
_nexus_secret: str = ""


def configure(secret: str) -> None:
    """Set the NEXUS webhook secret for signature verification."""
    global _nexus_secret
    _nexus_secret = secret


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from NEXUS."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/nexus/webhook")
async def receive_nexus_event(
    request: Request,
    x_nexus_signature: str = Header(""),
    x_nexus_event: str = Header(""),
):
    """Receive and store enriched events from WatchTower NEXUS."""
    body = await request.body()

    # Verify signature if secret configured
    if _nexus_secret and not _verify_signature(body, x_nexus_signature, _nexus_secret):
        logger.warning("NEXUS webhook signature verification failed")
        return {"status": "rejected", "reason": "invalid signature"}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "rejected", "reason": "invalid JSON"}

    event_type = x_nexus_event or payload.get("event_type", "")

    if event_type == "killmail":
        _store_nexus_killmail(request.state.db, payload)
    elif event_type == "gate_transit":
        _store_nexus_gate_transit(request.state.db, payload)
    elif event_type == "gate_permit":
        _store_nexus_gate_permit(request.state.db, payload)
    else:
        logger.debug("Ignoring NEXUS event type: %s", event_type)
        return {"status": "ignored", "event_type": event_type}

    return {"status": "accepted", "event_type": event_type}


def _store_nexus_killmail(db, payload: dict) -> None:
    """Store a killmail from NEXUS into nexus_events table."""
    now = int(time.time())
    db.execute(
        """INSERT OR IGNORE INTO nexus_events
           (event_type, event_id, solar_system_id, payload, received_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            "killmail",
            payload.get("killmail_id", ""),
            payload.get("solar_system_id", ""),
            json.dumps(payload),
            now,
        ),
    )
    db.commit()
    logger.info("NEXUS killmail: %s", payload.get("killmail_id", "?"))


def _store_nexus_gate_transit(db, payload: dict) -> None:
    """Store a gate transit from NEXUS into nexus_events table."""
    now = int(time.time())
    db.execute(
        """INSERT OR IGNORE INTO nexus_events
           (event_type, event_id, solar_system_id, payload, received_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            "gate_transit",
            f"{payload.get('gate_id', '')}-{payload.get('timestamp', '')}",
            payload.get("solar_system_id", ""),
            json.dumps(payload),
            now,
        ),
    )
    db.commit()
    logger.debug("NEXUS gate transit: gate %s", payload.get("gate_id", "?"))


def _store_nexus_gate_permit(db, payload: dict) -> None:
    """Store a gate permit event from NEXUS."""
    now = int(time.time())
    db.execute(
        """INSERT OR IGNORE INTO nexus_events
           (event_type, event_id, solar_system_id, payload, received_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            "gate_permit",
            payload.get("permit_id", ""),
            payload.get("solar_system_id", ""),
            json.dumps(payload),
            now,
        ),
    )
    db.commit()
    logger.debug("NEXUS gate permit: %s", payload.get("permit_id", "?"))

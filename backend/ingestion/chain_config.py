"""Chain config bootstrap — fetches live packageId and rpcUrls from World API /config.

The packageId changes each EVE Frontier cycle. This module fetches it
dynamically on startup and caches the result in SQLite so the app can
survive transient World API outages.
"""

import json
import logging
import sqlite3
import time

import httpx

logger = logging.getLogger(__name__)


def _ensure_table(conn: sqlite3.Connection) -> None:
    """Create chain_config cache table if it doesn't exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chain_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            fetched_at INTEGER NOT NULL
        )"""
    )
    conn.commit()


def _load_cached(conn: sqlite3.Connection) -> dict | None:
    """Load cached config from SQLite. Returns None if no cache."""
    row = conn.execute(
        "SELECT value, fetched_at FROM chain_config WHERE key = 'world_config'"
    ).fetchone()
    if row:
        try:
            config = json.loads(row["value"])
            config["_cached"] = True
            config["_fetched_at"] = row["fetched_at"]
            return config
        except json.JSONDecodeError:
            return None
    return None


def _save_cache(conn: sqlite3.Connection, config: dict) -> None:
    """Cache config in SQLite."""
    now = int(time.time())
    conn.execute(
        """INSERT INTO chain_config (key, value, fetched_at)
           VALUES ('world_config', ?, ?)
           ON CONFLICT(key) DO UPDATE SET
               value = excluded.value,
               fetched_at = excluded.fetched_at""",
        (json.dumps(config), now),
    )
    conn.commit()


def parse_config(raw: dict) -> dict:
    """Extract the fields Monolith needs from the raw /config response."""
    contracts = raw.get("contracts", {})
    world = contracts.get("world", {})
    rpc_urls = raw.get("rpcUrls", {}).get("default", {})

    return {
        "package_id": world.get("address", ""),
        "rpc_http": rpc_urls.get("http", ""),
        "rpc_ws": rpc_urls.get("webSocket", ""),
        "cycle_start": raw.get("cycleStartDate", ""),
        "indexer_url": raw.get("indexerUrl", ""),
        "chain_id": raw.get("chainId", ""),
    }


async def fetch_chain_config(
    world_api_url: str,
    conn: sqlite3.Connection,
    timeout: int = 10,
) -> dict:
    """Fetch /config from World API, fall back to SQLite cache.

    Returns parsed config dict with keys:
        package_id, rpc_http, rpc_ws, cycle_start, indexer_url, chain_id
    """
    _ensure_table(conn)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{world_api_url.rstrip('/')}/config",
                timeout=timeout,
            )
            resp.raise_for_status()
            raw = resp.json()
            config = parse_config(raw)

            if config["package_id"]:
                _save_cache(conn, config)
                logger.info(
                    "Fetched chain config — packageId: %s...  cycle: %s",
                    config["package_id"][:20],
                    config["cycle_start"],
                )
                return config
            else:
                logger.warning("World API /config returned empty packageId")
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("Failed to fetch /config from %s: %s", world_api_url, e)

    # Fall back to cached config
    cached = _load_cached(conn)
    if cached:
        age = int(time.time()) - cached.get("_fetched_at", 0)
        logger.info(
            "Using cached chain config (age: %ds) — packageId: %s...",
            age,
            cached.get("package_id", "")[:20],
        )
        return cached

    logger.error(
        "No chain config available — /config unreachable and no cache. "
        "Set MONOLITH_SUI_PACKAGE_ID manually."
    )
    return {
        "package_id": "",
        "rpc_http": "",
        "rpc_ws": "",
        "cycle_start": "",
        "indexer_url": "",
        "chain_id": "",
    }

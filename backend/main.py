"""Monolith — EVE Frontier Blockchain Anomaly Detector.

FastAPI application entry point with background polling tasks.
"""

import asyncio
import contextlib
import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.alerts.discord import send_alert
from backend.alerts.github_issues import file_github_issue
from backend.alerts.subscription_dispatch import dispatch_to_subscribers
from backend.api.anomalies import router as anomalies_router
from backend.api.error_tracker import capture_error
from backend.api.error_tracker import router as error_tracker_router
from backend.api.objects import router as objects_router
from backend.api.orbital_zones import router as orbital_zones_router
from backend.api.public import limiter
from backend.api.public import router as public_router
from backend.api.reports import router as reports_router
from backend.api.stats import router as stats_router
from backend.api.submit import router as submit_router
from backend.api.subscriptions import router as subscriptions_router
from backend.api.systems import router as systems_router
from backend.config import get_settings
from backend.db.database import get_connection, get_row_counts, init_db
from backend.detection.engine import DetectionEngine
from backend.ingestion.chain_config import fetch_chain_config
from backend.ingestion.chain_reader import ChainReader
from backend.ingestion.event_processor import EventProcessor
from backend.ingestion.graphql_client import SuiGraphQLClient
from backend.ingestion.name_resolver import NameResolver
from backend.ingestion.nexus_consumer import configure as configure_nexus
from backend.ingestion.nexus_consumer import router as nexus_router
from backend.ingestion.pod_verifier import PodVerifier
from backend.ingestion.state_snapshotter import StateSnapshotter
from backend.ingestion.world_poller import WorldPoller
from backend.warden.warden import Warden

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

START_TIME = time.time()


async def chain_poll_loop(
    reader: ChainReader,
    processor: EventProcessor,
    interval: int,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Background task: poll chain events, then process into object state."""
    while True:
        try:
            stored = await reader.poll(client)
            if stored > 0:
                logger.info("Chain poll: %d new events", stored)
            # Process any unprocessed events into object state
            processed = processor.process_unprocessed()
            if processed > 0:
                logger.info("Event processor: %d events → object state", processed)
        except Exception:
            logger.exception("Chain poll error")
        await asyncio.sleep(interval)


async def snapshot_loop(snapshotter: StateSnapshotter, interval: int) -> None:
    """Background task: compute state deltas on interval."""
    while True:
        try:
            deltas = snapshotter.process_all_objects()
            if deltas > 0:
                logger.info("Snapshotter: %d state deltas", deltas)
        except Exception:
            logger.exception("Snapshotter error")
        await asyncio.sleep(interval)


async def detection_loop(
    engine: DetectionEngine,
    interval: int,
    settings=None,
    conn=None,
) -> None:
    """Background task: run detection engine on interval."""
    # Wait for initial data ingestion before first detection run
    await asyncio.sleep(30)
    webhook_url = settings.discord_webhook_url if settings else ""
    rate_limit = settings.discord_rate_limit if settings else 5
    github_repo = settings.github_repo if settings else ""
    github_token = settings.github_token if settings else ""
    while True:
        try:
            new_anomalies = engine.run_cycle()
            if new_anomalies:
                for a in new_anomalies:
                    logger.warning(
                        "ANOMALY [%s] %s — %s: %s",
                        a["severity"],
                        a["anomaly_type"],
                        a["object_id"][:20],
                        a["evidence"].get("description", "")[:80],
                    )
                    # Fire Discord alert for all severities (demo mode)
                    if webhook_url:
                        await send_alert(webhook_url, a, rate_limit)
                    # File GitHub issue for CRITICAL only
                    if github_repo and github_token and a["severity"] == "CRITICAL":
                        await file_github_issue(github_repo, github_token, a, conn)
                    # Dispatch to subscriber webhooks (filters applied inside)
                    await dispatch_to_subscribers(conn, a)
        except Exception:
            logger.exception("Detection engine error")
        await asyncio.sleep(interval)


async def pod_check_loop(
    conn,
    pod_verifier: PodVerifier,
    engine: DetectionEngine,
    interval: int,
    settings=None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Background task: run async POD verification checks on interval."""
    from backend.detection.killmail_checker import KillmailChecker
    from backend.detection.pod_checker import PodChecker

    # Wait for initial data before first POD check
    await asyncio.sleep(60)
    webhook_url = settings.discord_webhook_url if settings else ""
    rate_limit = settings.discord_rate_limit if settings else 5
    github_repo = settings.github_repo if settings else ""
    github_token = settings.github_token if settings else ""

    while True:
        try:
            checker = PodChecker(conn)
            anomalies = await checker.run_async(client)
            for anomaly in anomalies:
                if engine._is_duplicate(anomaly):
                    continue
                if engine._store_anomaly(anomaly):
                    conn.commit()
                    a = anomaly.to_dict()
                    logger.warning(
                        "POD ANOMALY [%s] %s — %s: %s",
                        a["severity"],
                        a["anomaly_type"],
                        a["object_id"][:20],
                        a["evidence"].get("description", "")[:80],
                    )
                    if webhook_url:
                        await send_alert(webhook_url, a, rate_limit)
                    if github_repo and github_token and a["severity"] == "CRITICAL":
                        await file_github_issue(github_repo, github_token, a, conn)
                    # Dispatch to subscriber webhooks (filters applied inside)
                    await dispatch_to_subscribers(conn, a)
            if anomalies:
                logger.info("POD check: %d anomalies found", len(anomalies))

            # Killmail reconciliation — now chain-internal (no World API needed)
            try:
                km_checker = KillmailChecker(conn)
                km_anomalies = km_checker.check()
                for anomaly in km_anomalies:
                    if engine._is_duplicate(anomaly):
                        continue
                    if engine._store_anomaly(anomaly):
                        conn.commit()
                        a = anomaly.to_dict()
                        logger.warning(
                            "KILLMAIL ANOMALY [%s] %s — %s: %s",
                            a["severity"],
                            a["anomaly_type"],
                            a["object_id"][:20],
                            a["evidence"].get("description", "")[:80],
                        )
                        if webhook_url:
                            await send_alert(webhook_url, a, rate_limit)
                        if github_repo and github_token and a["severity"] == "CRITICAL":
                            await file_github_issue(github_repo, github_token, a, conn)
                        await dispatch_to_subscribers(conn, a)
                if km_anomalies:
                    logger.info(
                        "Killmail check: %d anomalies found",
                        len(km_anomalies),
                    )
            except Exception:
                logger.exception("Killmail reconciliation error")
        except Exception:
            logger.exception("POD check error")
        await asyncio.sleep(interval)


async def graphql_enrichment_loop(
    gql_client: SuiGraphQLClient,
    name_resolver: NameResolver,
    interval: int,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Background task: enrich locations + entity names via Sui GraphQL."""
    # Wait for initial chain data + static data to finish before enrichment
    await asyncio.sleep(120)
    while True:
        try:
            updated = await gql_client.enrich_locations(client)
            if updated > 0:
                logger.info("GraphQL enrichment: %d objects updated", updated)

            # Refresh character name cache via NameResolver (replaces NEXUS)
            names = await name_resolver._fetch_characters(client, max_pages=10)
            if names > 0:
                logger.info("NameResolver: %d characters resolved", names)

            # Audit object versions for state change detection
            versions = await gql_client.audit_object_versions(client)
            if versions > 0:
                logger.info("GraphQL versions: %d snapshots stored", versions)

            # Poll config singletons for change detection
            configs = await gql_client.poll_config_singletons(client)
            if configs > 0:
                logger.info("GraphQL configs: %d config versions stored", configs)

            # Profile wallet activity for bot detection
            profiles = await gql_client.profile_wallet_activity(client, max_wallets=10)
            if profiles > 0:
                logger.info("GraphQL profiles: %d wallets profiled", profiles)
        except Exception:
            logger.exception("GraphQL enrichment error")
        await asyncio.sleep(interval)


async def warden_loop(
    warden: Warden,
    interval: int,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Background task: run Warden autonomous verification on interval."""
    # Delay to let detection engine populate anomalies first
    await asyncio.sleep(120)
    while True:
        try:
            results = await warden.run_cycle(client)
            if results.get("status") == "completed":
                logger.info(
                    "Warden: %d verified, %d dismissed",
                    results["verified"],
                    results["dismissed"],
                )
            elif results.get("status") == "paused":
                logger.info("Warden paused — max cycles reached, awaiting reset")
                # Wait longer before checking again
                await asyncio.sleep(interval * 10)
                continue
        except Exception:
            logger.exception("Warden error")
        await asyncio.sleep(interval)


async def table_prune_loop(conn: sqlite3.Connection, interval: int = 21600) -> None:
    """Background task: prune stale rows from world_states and state_transitions.

    Runs every 6 hours (default). Keeps the 2 most recent world_states per
    object_id, deletes anything older than 7 days. Prunes state_transitions
    older than 30 days.
    """
    # Delay to avoid competing with startup I/O
    await asyncio.sleep(300)
    while True:
        try:
            now = int(time.time())

            # Prune world_states older than 7 days, keeping 2 most recent per object_id
            seven_days_ago = now - (7 * 86400)
            result = conn.execute(
                """DELETE FROM world_states
                   WHERE snapshot_time < ?
                     AND rowid NOT IN (
                       SELECT rowid FROM (
                         SELECT rowid, ROW_NUMBER() OVER (
                           PARTITION BY object_id ORDER BY snapshot_time DESC
                         ) as rn
                         FROM world_states
                       ) WHERE rn <= 2
                     )""",
                (seven_days_ago,),
            )
            ws_pruned = result.rowcount
            if ws_pruned > 0:
                conn.commit()
                logger.info("Table pruning: deleted %d stale world_states rows", ws_pruned)

            # Prune state_transitions older than 30 days
            thirty_days_ago = now - (30 * 86400)
            result = conn.execute(
                "DELETE FROM state_transitions WHERE timestamp < ?",
                (thirty_days_ago,),
            )
            st_pruned = result.rowcount
            if st_pruned > 0:
                conn.commit()
                logger.info("Table pruning: deleted %d stale state_transitions rows", st_pruned)

            if ws_pruned > 0 or st_pruned > 0:
                logger.info(
                    "Table pruning complete — world_states: %d, state_transitions: %d",
                    ws_pruned,
                    st_pruned,
                )
        except Exception:
            logger.exception("Table pruning error")
        await asyncio.sleep(interval)


async def _fetch_static(poller: WorldPoller, client: httpx.AsyncClient | None) -> None:
    """Fetch a single static data source, logging errors without propagating."""
    try:
        counts = await poller.poll_static_data(client)
        if counts:
            logger.info("Static data fetch: %s", counts)
    except Exception:
        logger.exception("Static data fetch failed")


async def _fetch_tribes(poller: WorldPoller, client: httpx.AsyncClient | None) -> None:
    try:
        tribe_count = await poller.poll_tribes(client)
        if tribe_count > 0:
            logger.info("Tribe cache refreshed: %d tribes", tribe_count)
    except Exception:
        logger.exception("Tribe cache fetch failed")


async def _fetch_orbital_zones(poller: WorldPoller, client: httpx.AsyncClient | None) -> None:
    try:
        oz_count = await poller.poll_orbital_zones(client)
        if oz_count > 0:
            logger.info("Orbital zones refreshed: %d zones", oz_count)
    except Exception:
        logger.exception("Orbital zone fetch failed")


async def static_data_loop(
    poller: WorldPoller,
    interval: int,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Background task: refresh static reference data periodically.

    Initial fetch runs all sources in parallel to cut startup time from ~90s to ~30s.
    """
    # Delay so HTTP server starts first, and chain_poll_loop gets priority
    await asyncio.sleep(15)
    # Initial fetch — all sources in parallel
    await asyncio.gather(
        _fetch_static(poller, client),
        _fetch_tribes(poller, client),
        _fetch_orbital_zones(poller, client),
    )

    while True:
        await asyncio.sleep(interval)
        await asyncio.gather(
            _fetch_static(poller, client),
            _fetch_tribes(poller, client),
            _fetch_orbital_zones(poller, client),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — bootstrap config, init DB, start pollers.

    Yields quickly so the HTTP server starts accepting health checks before
    background loops finish their initial data fetches.
    """
    settings = get_settings()
    conn = init_db(settings.database_path)
    app.state.db = conn
    app.state.settings = settings

    # Configure NEXUS webhook consumer
    configure_nexus(settings.nexus_secret)

    # Read packageId/rpcUrl from settings (chain config fetch deferred to background)
    sui_rpc_url = settings.sui_rpc_url
    package_id = settings.sui_package_id

    if not package_id:
        # Try a fast fetch with short timeout — if it fails, background loop will retry
        try:
            chain_config = await asyncio.wait_for(
                fetch_chain_config(settings.world_api_url, conn), timeout=5.0
            )
            if chain_config.get("package_id"):
                package_id = chain_config["package_id"]
                logger.info("Resolved packageId: %s...", package_id[:20])
            if chain_config.get("rpc_http") and not settings.sui_rpc_url:
                sui_rpc_url = chain_config["rpc_http"]
                logger.info("Resolved Sui RPC URL: %s", sui_rpc_url)
        except (TimeoutError, Exception):
            logger.warning(
                "Chain config fetch timed out — will retry in background. "
                "Set MONOLITH_SUI_PACKAGE_ID to skip auto-discovery."
            )

    if not package_id:
        logger.warning(
            "No packageId available — chain polling disabled. "
            "Set MONOLITH_SUI_PACKAGE_ID or ensure World API /config is reachable."
        )

    # Per-task connections — WAL mode allows concurrent writers from separate
    # connections but Python sqlite3 serializes all access through a single
    # connection object.  Giving each background loop its own connection
    # eliminates "database is locked" contention.
    db_path = settings.database_path
    conn_chain = get_connection(db_path)  # chain_poll_loop
    conn_detection = get_connection(db_path)  # detection_loop
    conn_pod = get_connection(db_path)  # pod_check_loop
    conn_snapshot = get_connection(db_path)  # snapshot_loop
    conn_world = get_connection(db_path)  # static_data_loop
    conn_gql = get_connection(db_path)  # graphql_enrichment_loop
    conn_prune = get_connection(db_path)  # table_prune_loop
    conn_warden = get_connection(db_path)  # warden_loop
    bg_conns = [
        conn_chain,
        conn_detection,
        conn_pod,
        conn_snapshot,
        conn_world,
        conn_gql,
        conn_prune,
        conn_warden,
    ]

    # Initialize components — each gets its own connection
    world_poller = WorldPoller(conn_world, settings.world_api_url, settings.world_api_timeout)
    chain_reader = ChainReader(conn_chain, sui_rpc_url, package_id, settings.sui_rpc_timeout)
    event_processor = EventProcessor(conn_chain)
    snapshotter = StateSnapshotter(conn_snapshot)
    detection_engine = DetectionEngine(conn_detection)

    pod_verifier = PodVerifier(base_url=settings.world_api_url, timeout=settings.world_api_timeout)
    app.state.pod_verifier = pod_verifier

    warden = Warden(conn_warden, sui_rpc_url)

    gql_client = SuiGraphQLClient(conn_gql, package_id)
    name_resolver = NameResolver(conn_gql, package_id)
    app.state.gql_client = gql_client
    app.state.name_resolver = name_resolver
    app.state.warden = warden
    app.state.world_poller = world_poller
    app.state.chain_reader = chain_reader
    app.state.event_processor = event_processor
    app.state.snapshotter = snapshotter
    app.state.detection_engine = detection_engine

    # Shared HTTP client for all background tasks — bounded connection pool
    http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        timeout=httpx.Timeout(30.0, connect=10.0),
    )
    app.state.http_client = http_client

    # Schedule background tasks — create_task is non-blocking; the tasks only
    # start executing at their first await point (after yield lets the server up).
    app.state.background_tasks = [
        asyncio.create_task(
            chain_poll_loop(
                chain_reader, event_processor, settings.chain_poll_interval, client=http_client
            )
        ),
        asyncio.create_task(snapshot_loop(snapshotter, settings.snapshot_interval)),
        asyncio.create_task(
            detection_loop(detection_engine, settings.detection_interval, settings, conn_detection)
        ),
        asyncio.create_task(
            static_data_loop(world_poller, settings.static_data_interval, client=http_client)
        ),
        asyncio.create_task(
            graphql_enrichment_loop(
                gql_client, name_resolver, settings.static_data_interval, client=http_client
            )
        ),
        asyncio.create_task(
            pod_check_loop(
                conn_pod,
                pod_verifier,
                detection_engine,
                settings.detection_interval,
                settings,
                client=http_client,
            )
        ),
        asyncio.create_task(table_prune_loop(conn_prune)),
        asyncio.create_task(warden_loop(warden, settings.detection_interval, client=http_client)),
    ]

    logger.info(
        "Monolith started — chain: %s  db: %s  package: %s...",
        settings.chain,
        settings.database_path,
        package_id[:16] if package_id else "NONE",
    )
    yield

    # --- Shutdown: cancel background tasks ---
    for task in app.state.background_tasks:
        task.cancel()
    for task in app.state.background_tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task

    await http_client.aclose()
    for bg_conn in bg_conns:
        bg_conn.close()
    conn.close()
    logger.info("Monolith shutdown")


app = FastAPI(
    title="Monolith",
    description="EVE Frontier Blockchain Anomaly Detector & Bug Report Engine",
    version="0.5.0",
    lifespan=lifespan,
)

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


try:
    from slowapi.errors import RateLimitExceeded
except ImportError:
    from slowapi._rate_limit_decorator import RateLimitExceeded


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Return 429 when a client exceeds the rate limit."""
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Capture unhandled exceptions into the error ring buffer, then re-raise."""
    capture_error(request, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


@app.middleware("http")
async def inject_db(request: Request, call_next):
    """Inject database connection into request state for route handlers."""
    request.state.db = request.app.state.db
    response = await call_next(request)
    return response


app.include_router(anomalies_router)
app.include_router(reports_router)
app.include_router(objects_router)
app.include_router(stats_router)
app.include_router(submit_router)
app.include_router(systems_router)
app.include_router(subscriptions_router)
app.include_router(public_router)
app.include_router(nexus_router, prefix="/api")
app.include_router(orbital_zones_router)
app.include_router(error_tracker_router, prefix="/api")


async def _check_sui_rpc(rpc_url: str) -> str:
    """Non-blocking connectivity check to Sui RPC endpoint (2s timeout)."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "suix_getLatestCheckpointSequenceNumber",
                    "params": [],
                },
                timeout=10.0,
            )
            if r.status_code == 200:
                return "ok"
            return f"http_{r.status_code}"
    except (httpx.HTTPError, OSError):
        return "unreachable"


@app.get("/api/ready")
async def ready() -> dict:
    """Lightweight readiness probe for Fly.io health checks.

    Returns immediately — no DB queries, no external calls.
    """
    return {"status": "ok", "uptime_seconds": int(time.time() - START_TIME)}


@app.get("/api/health")
async def health() -> dict:
    """System health — uptime, row counts, chain info (heavy, not for health checks)."""
    conn = app.state.db
    settings = app.state.settings
    counts = get_row_counts(conn)

    last_event_row = conn.execute("SELECT MAX(timestamp) FROM chain_events").fetchone()
    last_event_time = last_event_row[0] if last_event_row and last_event_row[0] else 0

    unprocessed = conn.execute("SELECT COUNT(*) FROM chain_events WHERE processed = 0").fetchone()

    sui_rpc = await _check_sui_rpc(settings.sui_rpc_url)

    # NEXUS event stats by type
    nexus_stats = {}
    try:
        for row in conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM nexus_events GROUP BY event_type"
        ).fetchall():
            nexus_stats[row["event_type"]] = row["cnt"]
    except sqlite3.OperationalError:
        nexus_stats = {"error": "nexus_events table not available"}

    # Tribe cache stats
    tribe_cache_stats = {}
    try:
        tribe_total = conn.execute("SELECT COUNT(*) FROM tribe_cache").fetchone()
        tribe_stale = conn.execute("SELECT COUNT(*) FROM tribe_cache WHERE is_stale = 1").fetchone()
        tribe_cache_stats = {
            "total": tribe_total[0] if tribe_total else 0,
            "stale": tribe_stale[0] if tribe_stale else 0,
        }
    except sqlite3.OperationalError:
        tribe_cache_stats = {"total": 0, "stale": 0}

    return {
        "status": "ok",
        "version": "0.4.0",
        "chain": settings.chain,
        "uptime_seconds": int(time.time() - START_TIME),
        "last_event_time": last_event_time,
        "unprocessed_events": unprocessed[0] if unprocessed else 0,
        "sui_rpc": sui_rpc,
        "row_counts": counts,
        "nexus_stats": nexus_stats,
        "unknown_event_types": (
            app.state.event_processor.unknown_type_counts
            if hasattr(app.state, "event_processor")
            else {}
        ),
        "tribe_cache": tribe_cache_stats,
    }


# Serve frontend static files (production build)
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    # Mount static assets (JS, CSS, images) under /assets
    _assets_dir = _frontend_dist / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    # SPA catch-all: serve index.html for any non-API path not matched above.
    # This must be registered LAST so API routes and static assets take priority.
    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Serve index.html for client-side routing (SPA fallback)."""
        # Never intercept API routes
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        # Serve actual static files if they exist (e.g. vite.svg, favicon)
        file_path = _frontend_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_dist / "index.html"))

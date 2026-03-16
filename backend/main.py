"""Monolith — EVE Frontier Blockchain Anomaly Detector.

FastAPI application entry point with background polling tasks.
"""

import asyncio
import contextlib
import logging
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
from backend.api.error_tracker import capture_error
from backend.api.error_tracker import router as error_tracker_router
from backend.api.anomalies import router as anomalies_router
from backend.api.objects import router as objects_router
from backend.api.public import router as public_router
from backend.api.reports import router as reports_router
from backend.api.stats import router as stats_router
from backend.api.submit import router as submit_router
from backend.api.subscriptions import router as subscriptions_router
from backend.api.systems import router as systems_router
from backend.config import get_settings
from backend.db.database import get_row_counts, init_db
from backend.detection.engine import DetectionEngine
from backend.ingestion.chain_config import fetch_chain_config
from backend.ingestion.chain_reader import ChainReader
from backend.ingestion.graphql_client import SuiGraphQLClient
from backend.ingestion.event_processor import EventProcessor
from backend.ingestion.nexus_consumer import configure as configure_nexus
from backend.ingestion.nexus_consumer import router as nexus_router
from backend.ingestion.pod_verifier import PodVerifier
from backend.ingestion.state_snapshotter import StateSnapshotter
from backend.ingestion.world_poller import WorldPoller

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
) -> None:
    """Background task: poll chain events, then process into object state."""
    async with httpx.AsyncClient() as client:
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
                    # Fire Discord alert for CRITICAL/HIGH
                    if webhook_url and a["severity"] in ("CRITICAL", "HIGH"):
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
            async with httpx.AsyncClient() as client:
                checker = PodChecker(conn, pod_verifier, client)
                anomalies = await checker.run_async()
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
                        if webhook_url and a["severity"] in ("CRITICAL", "HIGH"):
                            await send_alert(webhook_url, a, rate_limit)
                        if github_repo and github_token and a["severity"] == "CRITICAL":
                            await file_github_issue(github_repo, github_token, a, conn)
                        # Dispatch to subscriber webhooks (filters applied inside)
                        await dispatch_to_subscribers(conn, a)
                if anomalies:
                    logger.info("POD check: %d anomalies found", len(anomalies))

                # Killmail reconciliation — same client, same loop
                try:
                    world_api_url = settings.world_api_url if settings else ""
                    if world_api_url:
                        km_checker = KillmailChecker(conn, client, world_api_url)
                        km_anomalies = await km_checker.run_async()
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
                                if webhook_url and a["severity"] in (
                                    "CRITICAL",
                                    "HIGH",
                                ):
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
    interval: int,
) -> None:
    """Background task: enrich object locations via Sui GraphQL queries."""
    # Wait for initial chain data before first enrichment pass
    await asyncio.sleep(90)
    while True:
        try:
            async with httpx.AsyncClient() as client:
                updated = await gql_client.enrich_locations(client)
                if updated > 0:
                    logger.info("GraphQL enrichment: %d objects updated", updated)
        except Exception:
            logger.exception("GraphQL enrichment error")
        await asyncio.sleep(interval)


async def static_data_loop(
    poller: WorldPoller,
    interval: int,
) -> None:
    """Background task: refresh static reference data periodically."""
    # Initial fetch on startup
    async with httpx.AsyncClient() as client:
        try:
            counts = await poller.poll_static_data(client)
            if counts:
                logger.info("Initial static data fetch: %s", counts)
        except Exception:
            logger.exception("Initial static data fetch failed")
        try:
            tribe_count = await poller.poll_tribes(client)
            if tribe_count > 0:
                logger.info("Tribe cache refreshed: %d tribes", tribe_count)
        except Exception:
            logger.exception("Initial tribe cache fetch failed")

    while True:
        await asyncio.sleep(interval)
        async with httpx.AsyncClient() as client:
            try:
                await poller.poll_static_data(client)
            except Exception:
                logger.exception("Static data refresh failed")
            try:
                tribe_count = await poller.poll_tribes(client)
                if tribe_count > 0:
                    logger.info("Tribe cache refreshed: %d tribes", tribe_count)
            except Exception:
                logger.exception("Tribe cache refresh failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — bootstrap config, init DB, start pollers."""
    settings = get_settings()
    conn = init_db(settings.database_path)
    app.state.db = conn
    app.state.settings = settings

    # Configure NEXUS webhook consumer
    configure_nexus(settings.nexus_secret)

    # Bootstrap: fetch chain config for dynamic packageId/rpcUrls
    sui_rpc_url = settings.sui_rpc_url
    package_id = settings.sui_package_id

    if not package_id:
        logger.info("Fetching chain config from %s/config...", settings.world_api_url)
        chain_config = await fetch_chain_config(settings.world_api_url, conn)
        if chain_config.get("package_id"):
            package_id = chain_config["package_id"]
            logger.info("Resolved packageId: %s...", package_id[:20])
        if chain_config.get("rpc_http") and not settings.sui_rpc_url:
            sui_rpc_url = chain_config["rpc_http"]
            logger.info("Resolved Sui RPC URL: %s", sui_rpc_url)

    if not package_id:
        logger.warning(
            "No packageId available — chain polling disabled. "
            "Set MONOLITH_SUI_PACKAGE_ID or ensure World API /config is reachable."
        )

    # Initialize components
    world_poller = WorldPoller(conn, settings.world_api_url, settings.world_api_timeout)
    chain_reader = ChainReader(conn, sui_rpc_url, package_id, settings.sui_rpc_timeout)
    event_processor = EventProcessor(conn)
    snapshotter = StateSnapshotter(conn)
    detection_engine = DetectionEngine(conn)

    pod_verifier = PodVerifier(base_url=settings.world_api_url, timeout=settings.world_api_timeout)
    app.state.pod_verifier = pod_verifier

    gql_client = SuiGraphQLClient(conn, package_id)
    app.state.gql_client = gql_client
    app.state.world_poller = world_poller
    app.state.chain_reader = chain_reader
    app.state.event_processor = event_processor
    app.state.snapshotter = snapshotter
    app.state.detection_engine = detection_engine

    # Start background tasks
    tasks = [
        asyncio.create_task(
            chain_poll_loop(chain_reader, event_processor, settings.chain_poll_interval)
        ),
        asyncio.create_task(snapshot_loop(snapshotter, settings.snapshot_interval)),
        asyncio.create_task(
            detection_loop(detection_engine, settings.detection_interval, settings, conn)
        ),
        asyncio.create_task(static_data_loop(world_poller, settings.static_data_interval)),
        asyncio.create_task(graphql_enrichment_loop(gql_client, settings.static_data_interval)),
        asyncio.create_task(
            pod_check_loop(
                conn,
                pod_verifier,
                detection_engine,
                settings.detection_interval,
                settings,
            )
        ),
    ]

    logger.info(
        "Monolith started — chain: %s  db: %s  package: %s...",
        settings.chain,
        settings.database_path,
        package_id[:16] if package_id else "NONE",
    )
    yield

    # Cancel background tasks on shutdown
    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task

    conn.close()
    logger.info("Monolith shutdown")


app = FastAPI(
    title="Monolith",
    description="EVE Frontier Blockchain Anomaly Detector & Bug Report Engine",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    except Exception:
        return "unreachable"


@app.get("/api/health")
async def health() -> dict:
    """System health — uptime, row counts, chain info."""
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
    except Exception:
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
    except Exception:
        tribe_cache_stats = {"total": 0, "stale": 0}

    return {
        "status": "ok",
        "version": "0.2.0",
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

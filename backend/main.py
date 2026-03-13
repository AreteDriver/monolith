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
from fastapi.staticfiles import StaticFiles

from backend.alerts.discord import send_alert
from backend.alerts.github_issues import file_github_issue
from backend.api.anomalies import router as anomalies_router
from backend.api.objects import router as objects_router
from backend.api.reports import router as reports_router
from backend.api.stats import router as stats_router
from backend.api.submit import router as submit_router
from backend.config import get_settings
from backend.db.database import get_row_counts, init_db
from backend.detection.engine import DetectionEngine
from backend.ingestion.chain_config import fetch_chain_config
from backend.ingestion.chain_reader import ChainReader
from backend.ingestion.event_processor import EventProcessor
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
        except Exception:
            logger.exception("Detection engine error")
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

    while True:
        await asyncio.sleep(interval)
        async with httpx.AsyncClient() as client:
            try:
                await poller.poll_static_data(client)
            except Exception:
                logger.exception("Static data refresh failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — bootstrap config, init DB, start pollers."""
    settings = get_settings()
    conn = init_db(settings.database_path)
    app.state.db = conn
    app.state.settings = settings

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
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/api/health")
def health() -> dict:
    """System health — uptime, row counts, chain info."""
    conn = app.state.db
    settings = app.state.settings
    counts = get_row_counts(conn)

    last_event_row = conn.execute("SELECT MAX(timestamp) FROM chain_events").fetchone()
    last_event_time = last_event_row[0] if last_event_row and last_event_row[0] else 0

    unprocessed = conn.execute("SELECT COUNT(*) FROM chain_events WHERE processed = 0").fetchone()

    return {
        "status": "ok",
        "version": "0.1.0",
        "chain": settings.chain,
        "uptime_seconds": int(time.time() - START_TIME),
        "last_event_time": last_event_time,
        "unprocessed_events": unprocessed[0] if unprocessed else 0,
        "row_counts": counts,
    }


# Serve frontend static files (production build)
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")

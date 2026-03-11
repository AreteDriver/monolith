"""Monolith — EVE Frontier Blockchain Anomaly Detector.

FastAPI application entry point.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.api.anomalies import router as anomalies_router
from backend.api.objects import router as objects_router
from backend.api.reports import router as reports_router
from backend.api.stats import router as stats_router
from backend.api.submit import router as submit_router
from backend.config import get_settings
from backend.db.database import get_row_counts, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — init DB on startup, close on shutdown."""
    settings = get_settings()
    conn = init_db(settings.database_path)
    app.state.db = conn
    app.state.settings = settings
    logger.info("Monolith started — database: %s", settings.database_path)
    yield
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
    """System health — uptime, row counts, last block processed."""
    conn = app.state.db
    counts = get_row_counts(conn)

    last_block_row = conn.execute("SELECT MAX(block_number) FROM chain_events").fetchone()
    last_block = last_block_row[0] if last_block_row and last_block_row[0] else 0

    last_event_row = conn.execute("SELECT MAX(timestamp) FROM chain_events").fetchone()
    last_event_time = last_event_row[0] if last_event_row and last_event_row[0] else 0

    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": int(time.time() - START_TIME),
        "last_block_processed": last_block,
        "last_event_time": last_event_time,
        "row_counts": counts,
    }

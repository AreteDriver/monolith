"""SQLite database setup with WAL mode and FTS5."""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
-- Raw chain events as they arrive
CREATE TABLE IF NOT EXISTS chain_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE,
    event_type TEXT,
    object_id TEXT,
    object_type TEXT,
    system_id TEXT,
    block_number INTEGER,
    transaction_hash TEXT,
    timestamp INTEGER,
    raw_json TEXT,
    processed INTEGER DEFAULT 0
);

-- World API state snapshots
CREATE TABLE IF NOT EXISTS world_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id TEXT,
    object_type TEXT,
    state_data TEXT,
    snapshot_time INTEGER,
    source TEXT
);

-- Tracked objects and their current known state
CREATE TABLE IF NOT EXISTS objects (
    object_id TEXT PRIMARY KEY,
    object_type TEXT,
    created_at INTEGER,
    destroyed_at INTEGER,
    current_state TEXT,
    current_owner TEXT,
    system_id TEXT,
    last_event_id TEXT,
    last_seen INTEGER,
    anomaly_count INTEGER DEFAULT 0
);

-- Full state transition history per object
CREATE TABLE IF NOT EXISTS state_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id TEXT,
    from_state TEXT,
    to_state TEXT,
    event_id TEXT,
    transaction_hash TEXT,
    block_number INTEGER,
    timestamp INTEGER,
    is_valid INTEGER DEFAULT 1,
    FOREIGN KEY (object_id) REFERENCES objects(object_id)
);

-- Detected anomalies
CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_id TEXT UNIQUE,
    anomaly_type TEXT,
    severity TEXT,
    category TEXT,
    detector TEXT,
    rule_id TEXT,
    object_id TEXT,
    system_id TEXT,
    detected_at INTEGER,
    evidence_json TEXT,
    status TEXT DEFAULT 'UNVERIFIED',
    report_id TEXT,
    discord_alerted INTEGER DEFAULT 0
);

-- Sui event cursor persistence for resumable polling
CREATE TABLE IF NOT EXISTS sui_cursors (
    event_filter TEXT PRIMARY KEY,
    tx_digest TEXT NOT NULL,
    event_seq TEXT NOT NULL,
    updated_at INTEGER
);

-- Cached chain config (packageId, rpcUrls, etc.)
CREATE TABLE IF NOT EXISTS chain_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    fetched_at INTEGER NOT NULL
);

-- Reference data from World API (solarsystems, types, tribes)
CREATE TABLE IF NOT EXISTS reference_data (
    data_type TEXT NOT NULL,
    data_id TEXT NOT NULL,
    name TEXT,
    data_json TEXT,
    updated_at INTEGER,
    PRIMARY KEY (data_type, data_id)
);

-- Tracked GitHub issues filed by the auto-filer
CREATE TABLE IF NOT EXISTS filed_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_id TEXT,
    issue_url TEXT,
    filed_at INTEGER
);

-- NEXUS: enriched events from WatchTower
CREATE TABLE IF NOT EXISTS nexus_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    event_id TEXT NOT NULL,
    solar_system_id TEXT,
    payload TEXT NOT NULL,
    received_at INTEGER NOT NULL,
    UNIQUE(event_type, event_id)
);

-- Item inventory ledger for economic tracking
CREATE TABLE IF NOT EXISTS item_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assembly_id TEXT NOT NULL,
    item_type_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    transaction_hash TEXT NOT NULL,
    timestamp INTEGER NOT NULL
);

-- Webhook subscriptions for Discord alerts
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sub_id TEXT UNIQUE NOT NULL,
    webhook_url TEXT NOT NULL,
    severity_filter TEXT NOT NULL DEFAULT '[]',
    event_types TEXT NOT NULL DEFAULT '[]',
    created_at INTEGER NOT NULL,
    active INTEGER DEFAULT 1
);

-- Tribe/corp cache with staleness tracking
CREATE TABLE IF NOT EXISTS tribe_cache (
    tribe_id TEXT PRIMARY KEY,
    name TEXT,
    name_short TEXT,
    member_count INTEGER DEFAULT 0,
    tax_rate REAL DEFAULT 0.0,
    data_json TEXT,
    first_seen_at INTEGER NOT NULL,
    last_confirmed_at INTEGER NOT NULL,
    last_changed_at INTEGER,
    is_stale INTEGER DEFAULT 0
);

-- Entity name cache (replaces NEXUS name enrichment)
CREATE TABLE IF NOT EXISTS entity_names (
    entity_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    entity_type TEXT,
    tribe_id TEXT,
    updated_at INTEGER
);

-- Object version snapshots for auditing state changes
CREATE TABLE IF NOT EXISTS object_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    digest TEXT,
    state_json TEXT,
    fetched_at INTEGER NOT NULL,
    UNIQUE(object_id, version)
);

-- Config singleton version tracking
CREATE TABLE IF NOT EXISTS config_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_type TEXT NOT NULL,
    config_address TEXT NOT NULL,
    version INTEGER NOT NULL,
    state_json TEXT,
    fetched_at INTEGER NOT NULL,
    UNIQUE(config_type, version)
);

-- Wallet activity profiles for bot detection
CREATE TABLE IF NOT EXISTS wallet_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_address TEXT NOT NULL,
    tx_count INTEGER DEFAULT 0,
    avg_interval_seconds REAL,
    interval_stddev REAL,
    first_tx INTEGER,
    last_tx INTEGER,
    updated_at INTEGER NOT NULL,
    UNIQUE(wallet_address)
);

-- Generated bug reports
CREATE TABLE IF NOT EXISTS bug_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT UNIQUE,
    anomaly_id TEXT,
    title TEXT,
    severity TEXT,
    category TEXT,
    summary TEXT,
    evidence_json TEXT,
    plain_english TEXT,
    chain_references TEXT,
    reproduction_context TEXT,
    recommended_investigation TEXT,
    generated_at INTEGER,
    format_markdown TEXT,
    format_json TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    FOREIGN KEY (anomaly_id) REFERENCES anomalies(anomaly_id)
);

-- Detection cycle timing for eval/system_metrics.py
CREATE TABLE IF NOT EXISTS detection_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL,
    finished_at REAL,
    anomalies_found INTEGER DEFAULT 0,
    events_processed INTEGER DEFAULT 0,
    error TEXT
);

-- Orbital zones with feral AI threat tracking
CREATE TABLE IF NOT EXISTS orbital_zones (
    zone_id TEXT PRIMARY KEY,
    zone_name TEXT,
    system_id TEXT,
    feral_ai_tier INTEGER DEFAULT 0,
    threat_level TEXT DEFAULT 'UNKNOWN',
    zone_data TEXT,
    discovered_at INTEGER,
    last_polled INTEGER
);

-- Feral AI events from chain + webhooks
CREATE TABLE IF NOT EXISTS feral_ai_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE,
    ai_entity_id TEXT,
    event_type TEXT,
    zone_id TEXT,
    system_id TEXT,
    action_json TEXT,
    detected_at INTEGER,
    severity TEXT DEFAULT 'MEDIUM'
);

-- Service health check history
CREATE TABLE IF NOT EXISTS service_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT NOT NULL,
    status TEXT NOT NULL,
    response_time_ms INTEGER,
    error_message TEXT,
    checked_at INTEGER NOT NULL
);

-- Service current state for transition detection
CREATE TABLE IF NOT EXISTS service_state (
    service_name TEXT PRIMARY KEY,
    current_status TEXT NOT NULL DEFAULT 'unknown',
    last_change_at INTEGER,
    consecutive_failures INTEGER DEFAULT 0,
    last_checked_at INTEGER
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_chain_events_object ON chain_events(object_id);
CREATE INDEX IF NOT EXISTS idx_chain_events_type ON chain_events(event_type);
CREATE INDEX IF NOT EXISTS idx_chain_events_block ON chain_events(block_number);
CREATE INDEX IF NOT EXISTS idx_chain_events_timestamp ON chain_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_chain_events_processed ON chain_events(processed);
CREATE INDEX IF NOT EXISTS idx_world_states_object ON world_states(object_id);
CREATE INDEX IF NOT EXISTS idx_world_states_time ON world_states(snapshot_time);
CREATE INDEX IF NOT EXISTS idx_state_transitions_object ON state_transitions(object_id);
CREATE INDEX IF NOT EXISTS idx_state_transitions_timestamp ON state_transitions(timestamp);
CREATE INDEX IF NOT EXISTS idx_anomalies_severity ON anomalies(severity);
CREATE INDEX IF NOT EXISTS idx_anomalies_type ON anomalies(anomaly_type);
CREATE INDEX IF NOT EXISTS idx_anomalies_detected ON anomalies(detected_at);
CREATE INDEX IF NOT EXISTS idx_anomalies_object ON anomalies(object_id);
CREATE INDEX IF NOT EXISTS idx_anomalies_status ON anomalies(status);
CREATE INDEX IF NOT EXISTS idx_anomalies_status_detected ON anomalies(status, detected_at);
CREATE INDEX IF NOT EXISTS idx_bug_reports_anomaly ON bug_reports(anomaly_id);
CREATE INDEX IF NOT EXISTS idx_reference_data_type ON reference_data(data_type);
CREATE INDEX IF NOT EXISTS idx_nexus_events_type ON nexus_events(event_type, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_item_ledger_assembly ON item_ledger(assembly_id);
CREATE INDEX IF NOT EXISTS idx_item_ledger_type ON item_ledger(item_type_id);
CREATE INDEX IF NOT EXISTS idx_item_ledger_timestamp ON item_ledger(timestamp);
CREATE INDEX IF NOT EXISTS idx_subscriptions_active ON subscriptions(active);
CREATE INDEX IF NOT EXISTS idx_tribe_cache_stale ON tribe_cache(is_stale);
CREATE INDEX IF NOT EXISTS idx_tribe_cache_confirmed ON tribe_cache(last_confirmed_at);
CREATE INDEX IF NOT EXISTS idx_object_versions_object ON object_versions(object_id);
CREATE INDEX IF NOT EXISTS idx_config_snapshots_type ON config_snapshots(config_type);
CREATE INDEX IF NOT EXISTS idx_wallet_activity_wallet ON wallet_activity(wallet_address);
CREATE INDEX IF NOT EXISTS idx_detection_cycles_started ON detection_cycles(started_at);
CREATE INDEX IF NOT EXISTS idx_orbital_zones_system ON orbital_zones(system_id);
CREATE INDEX IF NOT EXISTS idx_orbital_zones_threat ON orbital_zones(threat_level);
CREATE INDEX IF NOT EXISTS idx_feral_ai_entity ON feral_ai_events(ai_entity_id);
CREATE INDEX IF NOT EXISTS idx_feral_ai_type ON feral_ai_events(event_type);
CREATE INDEX IF NOT EXISTS idx_feral_ai_zone ON feral_ai_events(zone_id);
CREATE INDEX IF NOT EXISTS idx_feral_ai_detected ON feral_ai_events(detected_at);
CREATE INDEX IF NOT EXISTS idx_service_checks_svc ON service_checks(service_name, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_checks_checked ON service_checks(checked_at);
"""

FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS anomalies_fts USING fts5(
    anomaly_type, object_id, system_id, evidence_json,
    content=anomalies,
    content_rowid=id
);
"""


def get_connection(db_path: str = "monolith.db") -> sqlite3.Connection:
    """Create a new database connection with WAL mode and optimized settings."""
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")  # 8MB cache
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")  # 30s — generous for WAL contention
    return conn


def init_db(db_path: str = "monolith.db") -> sqlite3.Connection:
    """Initialize database with full schema, indexes, and FTS."""
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.executescript(INDEXES)
    try:
        conn.executescript(FTS)
    except sqlite3.OperationalError as e:
        if "fts5" in str(e).lower():
            logger.warning("FTS5 not available — full-text search disabled: %s", e)
        else:
            raise
    # Migrations: add columns to existing tables (safe to run repeatedly)
    _migrate_add_column(conn, "bug_reports", "input_tokens", "INTEGER")
    _migrate_add_column(conn, "bug_reports", "output_tokens", "INTEGER")
    # Cycle 5: add cycle tracking to core tables
    _migrate_add_column(conn, "chain_events", "cycle", "INTEGER DEFAULT 5")
    _migrate_add_column(conn, "anomalies", "cycle", "INTEGER DEFAULT 5")
    # Provenance chains: auditable derivation trail per anomaly
    _migrate_add_column(conn, "anomalies", "provenance_json", "TEXT")
    # Enriched intel context: who/what/when/where behind the anomaly
    _migrate_add_column(conn, "anomalies", "context_json", "TEXT")
    # Enforce 1 bug report per anomaly — upgrade non-unique index to unique
    _migrate_unique_index(conn, "bug_reports", "anomaly_id", "idx_bug_reports_anomaly")
    # Fix system_id stored as Python dict repr: "{'item_id': '30013131', ...}" → "30013131"
    _fix_dict_system_ids(conn)
    conn.commit()
    logger.info("Database initialized: %s", db_path)
    return conn


def _fix_dict_system_ids(conn: sqlite3.Connection) -> None:
    """Fix system_id fields stored as Python dict repr strings."""
    import re

    pattern = re.compile(r"'item_id':\s*'(\d+)'")
    fixed = 0
    for table in ("chain_events", "anomalies", "objects"):
        try:
            rows = conn.execute(
                f"SELECT rowid, system_id FROM {table} WHERE system_id LIKE '%item_id%'"  # noqa: S608
            ).fetchall()
            for row in rows:
                sid = row[1]  # use index, not key — row_factory may vary
                match = pattern.search(str(sid))
                if match:
                    conn.execute(
                        f"UPDATE {table} SET system_id = ? WHERE rowid = ?",  # noqa: S608
                        (match.group(1), row[0]),
                    )
                    fixed += 1
        except sqlite3.OperationalError:
            continue
    if fixed:
        conn.commit()
        logger.info("Fixed %d dict-format system_id values", fixed)


def _migrate_add_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    """Add a column if it doesn't already exist (idempotent migration)."""
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")  # noqa: S608
        logger.info("Migration: added %s.%s (%s)", table, column, col_type)


def _migrate_unique_index(
    conn: sqlite3.Connection, table: str, column: str, index_name: str
) -> None:
    """Replace a non-unique index with a unique one (idempotent).

    Deduplicates existing rows first — keeps the row with the highest rowid.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (index_name,)
    ).fetchone()
    if row and "UNIQUE" not in (row[0] or "").upper():
        # Remove duplicates before creating unique index (keep latest rowid)
        deleted = conn.execute(
            f"DELETE FROM {table} WHERE rowid NOT IN "  # noqa: S608
            f"(SELECT MAX(rowid) FROM {table} GROUP BY {column})"
        ).rowcount
        if deleted > 0:
            logger.info("Migration: removed %d duplicate %s rows from %s", deleted, column, table)
        conn.execute(f"DROP INDEX IF EXISTS {index_name}")  # noqa: S608
        conn.execute(
            f"CREATE UNIQUE INDEX {index_name} ON {table}({column})"  # noqa: S608
        )
        logger.info("Migration: upgraded %s to UNIQUE on %s.%s", index_name, table, column)


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists on a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")  # noqa: S608
    return any(row[1] == column for row in cursor.fetchall())


def get_row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Get row counts for all tables — used in health endpoint."""
    tables = [
        "chain_events",
        "world_states",
        "objects",
        "state_transitions",
        "anomalies",
        "bug_reports",
        "filed_issues",
        "nexus_events",
        "item_ledger",
        "tribe_cache",
        "detection_cycles",
        "orbital_zones",
        "feral_ai_events",
        "service_checks",
        "service_state",
    ]
    counts = {}
    for table in tables:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
        counts[table] = row[0]
    return counts

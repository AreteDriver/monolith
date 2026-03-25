"""
eval/system_metrics.py

System Health & Operational Metrics for Monolith.

Pulls from SQLite to answer: "Is the system running right?"

Metrics produced:
  - Detection cycle latency (P50, P95) — requires detection_cycles table (see NOTE)
  - Anomaly rate per hour (baseline vs. active window)
  - Cost per report (Anthropic tokens × price)
  - Poll interval drift (did the 300s interval hold?)
  - DB row counts and health

NOTE on detection_cycles table:
  This script expects a `detection_cycles` table that your detection engine
  should write to on each run. If it doesn't exist yet, add this to database.py:

    CREATE TABLE IF NOT EXISTS detection_cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at REAL,      -- unix timestamp (time.time())
        finished_at REAL,     -- unix timestamp
        anomalies_found INTEGER DEFAULT 0,
        events_processed INTEGER DEFAULT 0,
        error TEXT            -- NULL if clean run
    );

  And in your detection engine, wrap each cycle:
    start = time.time()
    ... run detection ...
    db.execute(INSERT INTO detection_cycles ...)

Usage:
    python eval/system_metrics.py
    python eval/system_metrics.py --db path/to/monolith.db --hours 24
    python eval/system_metrics.py --json
"""

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Anthropic pricing (update if model changes)
# ---------------------------------------------------------------------------
# claude-sonnet-4-5 as of early 2026
INPUT_TOKEN_COST_PER_1K = 0.003  # $0.003 per 1K input tokens
OUTPUT_TOKEN_COST_PER_1K = 0.015  # $0.015 per 1K output tokens

# Target thresholds (used for pass/fail coloring)
TARGET_LATENCY_P95_MS = 500.0
TARGET_COST_PER_REPORT_USD = 0.01
TARGET_POLL_DRIFT_PCT = 10.0  # allow 10% drift from 300s target
TARGET_ANOMALY_RATE_MAX = 50.0  # anomalies/hour — above this flags runaway detection

# ANSI color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class LatencyMetrics:
    p50_ms: float | None
    p95_ms: float | None
    sample_count: int
    available: bool = True
    unavailable_reason: str = ""


@dataclass
class CostMetrics:
    total_reports: int
    reports_with_token_data: int
    avg_input_tokens: float | None
    avg_output_tokens: float | None
    estimated_cost_per_report_usd: float | None
    total_estimated_cost_usd: float | None


@dataclass
class AnomalyRateMetrics:
    window_hours: int
    anomalies_in_window: int
    rate_per_hour: float
    severity_breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class PollDriftMetrics:
    target_interval_s: int
    avg_actual_interval_s: float | None
    drift_pct: float | None
    sample_count: int
    available: bool = True
    unavailable_reason: str = ""


@dataclass
class DBHealthMetrics:
    chain_events: int
    world_states: int
    objects: int
    anomalies: int
    bug_reports: int
    detection_cycles: int | None


@dataclass
class SystemMetricsSummary:
    db_path: str
    generated_at: float
    window_hours: int
    latency: LatencyMetrics
    cost: CostMetrics
    anomaly_rate: AnomalyRateMetrics
    poll_drift: PollDriftMetrics
    db_health: DBHealthMetrics


# ---------------------------------------------------------------------------
# DB Helpers
# ---------------------------------------------------------------------------
def get_conn(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return any(row["name"] == column for row in cursor.fetchall())


# ---------------------------------------------------------------------------
# Metric Collectors
# ---------------------------------------------------------------------------
def collect_latency(conn: sqlite3.Connection) -> LatencyMetrics:
    if not table_exists(conn, "detection_cycles"):
        return LatencyMetrics(
            p50_ms=None,
            p95_ms=None,
            sample_count=0,
            available=False,
            unavailable_reason=(
                "detection_cycles table not found. "
                "See NOTE in system_metrics.py to instrument your detection engine."
            ),
        )

    cursor = conn.execute(
        """
        SELECT (finished_at - started_at) * 1000 AS duration_ms
        FROM detection_cycles
        WHERE finished_at IS NOT NULL AND started_at IS NOT NULL
        ORDER BY duration_ms
        """
    )
    durations = [row["duration_ms"] for row in cursor.fetchall()]

    if not durations:
        return LatencyMetrics(
            p50_ms=None,
            p95_ms=None,
            sample_count=0,
            available=False,
            unavailable_reason="No completed detection cycles recorded yet.",
        )

    def percentile(data: list[float], p: float) -> float:
        idx = int(len(data) * p / 100)
        return data[min(idx, len(data) - 1)]

    return LatencyMetrics(
        p50_ms=round(percentile(durations, 50), 2),
        p95_ms=round(percentile(durations, 95), 2),
        sample_count=len(durations),
    )


def collect_cost(conn: sqlite3.Connection) -> CostMetrics:
    total_cursor = conn.execute("SELECT COUNT(*) as cnt FROM bug_reports")
    total_reports = total_cursor.fetchone()["cnt"]

    # Check if token columns exist (they may not be in the original schema)
    has_input_tokens = column_exists(conn, "bug_reports", "input_tokens")
    has_output_tokens = column_exists(conn, "bug_reports", "output_tokens")

    if not has_input_tokens or not has_output_tokens:
        return CostMetrics(
            total_reports=total_reports,
            reports_with_token_data=0,
            avg_input_tokens=None,
            avg_output_tokens=None,
            estimated_cost_per_report_usd=None,
            total_estimated_cost_usd=None,
        )

    cursor = conn.execute(
        """
        SELECT
            COUNT(*) as cnt,
            AVG(input_tokens) as avg_in,
            AVG(output_tokens) as avg_out
        FROM bug_reports
        WHERE input_tokens IS NOT NULL AND output_tokens IS NOT NULL
        """
    )
    row = cursor.fetchone()

    if not row or row["cnt"] == 0:
        return CostMetrics(
            total_reports=total_reports,
            reports_with_token_data=0,
            avg_input_tokens=None,
            avg_output_tokens=None,
            estimated_cost_per_report_usd=None,
            total_estimated_cost_usd=None,
        )

    avg_in = row["avg_in"] or 0
    avg_out = row["avg_out"] or 0
    cost_per_report = (avg_in / 1000 * INPUT_TOKEN_COST_PER_1K) + (
        avg_out / 1000 * OUTPUT_TOKEN_COST_PER_1K
    )

    return CostMetrics(
        total_reports=total_reports,
        reports_with_token_data=row["cnt"],
        avg_input_tokens=round(avg_in, 1),
        avg_output_tokens=round(avg_out, 1),
        estimated_cost_per_report_usd=round(cost_per_report, 5),
        total_estimated_cost_usd=round(cost_per_report * total_reports, 4),
    )


def collect_anomaly_rate(conn: sqlite3.Connection, window_hours: int) -> AnomalyRateMetrics:
    since = time.time() - (window_hours * 3600)

    cursor = conn.execute("SELECT COUNT(*) as cnt FROM anomalies WHERE detected_at >= ?", (since,))
    count = cursor.fetchone()["cnt"]

    severity_cursor = conn.execute(
        """
        SELECT severity, COUNT(*) as cnt
        FROM anomalies
        WHERE detected_at >= ?
        GROUP BY severity
        """,
        (since,),
    )
    breakdown = {row["severity"]: row["cnt"] for row in severity_cursor.fetchall()}

    return AnomalyRateMetrics(
        window_hours=window_hours,
        anomalies_in_window=count,
        rate_per_hour=round(count / window_hours, 2),
        severity_breakdown=breakdown,
    )


def collect_poll_drift(conn: sqlite3.Connection, target_interval_s: int = 300) -> PollDriftMetrics:
    if not table_exists(conn, "detection_cycles"):
        return PollDriftMetrics(
            target_interval_s=target_interval_s,
            avg_actual_interval_s=None,
            drift_pct=None,
            sample_count=0,
            available=False,
            unavailable_reason="detection_cycles table not found.",
        )

    cursor = conn.execute("SELECT started_at FROM detection_cycles ORDER BY started_at ASC")
    starts = [row["started_at"] for row in cursor.fetchall()]

    if len(starts) < 2:
        return PollDriftMetrics(
            target_interval_s=target_interval_s,
            avg_actual_interval_s=None,
            drift_pct=None,
            sample_count=len(starts),
            available=False,
            unavailable_reason="Not enough cycles to compute drift (need >= 2).",
        )

    intervals = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
    avg_interval = sum(intervals) / len(intervals)
    drift_pct = abs(avg_interval - target_interval_s) / target_interval_s * 100

    return PollDriftMetrics(
        target_interval_s=target_interval_s,
        avg_actual_interval_s=round(avg_interval, 2),
        drift_pct=round(drift_pct, 2),
        sample_count=len(starts),
    )


def collect_db_health(conn: sqlite3.Connection) -> DBHealthMetrics:
    def count(table: str) -> int:
        if not table_exists(conn, table):
            return -1
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608

    return DBHealthMetrics(
        chain_events=count("chain_events"),
        world_states=count("world_states"),
        objects=count("objects"),
        anomalies=count("anomalies"),
        bug_reports=count("bug_reports"),
        detection_cycles=(
            count("detection_cycles") if table_exists(conn, "detection_cycles") else None
        ),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run_metrics(db_path: str, window_hours: int = 24) -> SystemMetricsSummary:
    conn = get_conn(db_path)
    try:
        return SystemMetricsSummary(
            db_path=db_path,
            generated_at=time.time(),
            window_hours=window_hours,
            latency=collect_latency(conn),
            cost=collect_cost(conn),
            anomaly_rate=collect_anomaly_rate(conn, window_hours),
            poll_drift=collect_poll_drift(conn),
            db_health=collect_db_health(conn),
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def fmt(val, unit="", precision=2, threshold=None, invert=False) -> str:
    """Format a value with optional color based on threshold."""

    if val is None:
        return f"{YELLOW}N/A{RESET}"

    formatted = f"{val:.{precision}f}{unit}" if isinstance(val, float) else f"{val}{unit}"

    if threshold is None:
        return formatted

    passed = val <= threshold if not invert else val >= threshold
    color = GREEN if passed else RED
    return f"{color}{formatted}{RESET}"


def print_report(summary: SystemMetricsSummary) -> None:
    import datetime

    ts = datetime.datetime.fromtimestamp(summary.generated_at).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'=' * 60}")
    print(f"  MONOLITH SYSTEM METRICS  |  {ts}")
    print(f"  DB: {summary.db_path}  |  Window: {summary.window_hours}h")
    print(f"{'=' * 60}")

    # Latency
    print("\n  DETECTION LATENCY")
    if not summary.latency.available:
        print(f"    ⚠  {summary.latency.unavailable_reason}")
    else:
        print(f"    P50:     {fmt(summary.latency.p50_ms, 'ms')}")
        print(
            f"    P95:     {fmt(summary.latency.p95_ms, 'ms', threshold=TARGET_LATENCY_P95_MS)}"
            f"  (target: <{TARGET_LATENCY_P95_MS:.0f}ms)"
        )
        print(f"    Samples: {summary.latency.sample_count}")

    # Anomaly Rate
    print(f"\n  ANOMALY RATE  ({summary.window_hours}h window)")
    print(f"    Count:   {summary.anomaly_rate.anomalies_in_window}")
    rate = fmt(
        summary.anomaly_rate.rate_per_hour,
        "/hr",
        threshold=TARGET_ANOMALY_RATE_MAX,
    )
    print(f"    Rate:    {rate}")
    if summary.anomaly_rate.severity_breakdown:
        for sev, cnt in sorted(summary.anomaly_rate.severity_breakdown.items()):
            print(f"    {sev:<12} {cnt}")

    # Cost
    print("\n  COST PER REPORT  (Anthropic API)")
    if summary.cost.estimated_cost_per_report_usd is None:
        if summary.cost.reports_with_token_data == 0 and summary.cost.total_reports > 0:
            print(f"    ⚠  No reports have token data yet ({summary.cost.total_reports} total).")
            print("       Token counts are logged when narration uses the Anthropic API.")
        else:
            print("    ⚠  Token columns not found in bug_reports.")
            print("       Add input_tokens / output_tokens columns to track costs.")
    else:
        print(f"    Avg input tokens:  {fmt(summary.cost.avg_input_tokens, '', 0)}")
        print(f"    Avg output tokens: {fmt(summary.cost.avg_output_tokens, '', 0)}")
        cost_val = fmt(
            summary.cost.estimated_cost_per_report_usd,
            "$",
            5,
            TARGET_COST_PER_REPORT_USD,
        )
        print(f"    Cost/report:       {cost_val}  (target: <${TARGET_COST_PER_REPORT_USD})")
        print(
            f"    Total estimated:   ${summary.cost.total_estimated_cost_usd:.4f}"
            f" across {summary.cost.total_reports} reports"
        )

    # Poll Drift
    print("\n  POLL INTERVAL DRIFT")
    if not summary.poll_drift.available:
        print(f"    ⚠  {summary.poll_drift.unavailable_reason}")
    else:
        print(f"    Target:   {summary.poll_drift.target_interval_s}s")
        print(f"    Actual:   {fmt(summary.poll_drift.avg_actual_interval_s, 's')}")
        drift_val = fmt(
            summary.poll_drift.drift_pct,
            "%",
            threshold=TARGET_POLL_DRIFT_PCT,
        )
        print(f"    Drift:    {drift_val}  (target: <{TARGET_POLL_DRIFT_PCT:.0f}%)")
        print(f"    Samples:  {summary.poll_drift.sample_count}")

    # DB Health
    print("\n  DATABASE HEALTH")
    h = summary.db_health
    print(f"    chain_events:     {h.chain_events:>8}")
    print(f"    world_states:     {h.world_states:>8}")
    print(f"    objects:          {h.objects:>8}")
    print(f"    anomalies:        {h.anomalies:>8}")
    print(f"    bug_reports:      {h.bug_reports:>8}")
    if h.detection_cycles is not None:
        print(f"    detection_cycles: {h.detection_cycles:>8}")

    print(f"\n{'=' * 60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Monolith System Metrics")
    parser.add_argument("--db", default="monolith.db")
    parser.add_argument("--hours", type=int, default=24, help="Anomaly rate window in hours")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        summary = run_metrics(args.db, args.hours)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(asdict(summary), indent=2))
    else:
        print_report(summary)


if __name__ == "__main__":
    main()

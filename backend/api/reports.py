"""Reports API — generate, list, and view bug reports."""

import contextlib
import json
import sqlite3

from fastapi import APIRouter, Query, Request

from backend.reports.formatter import format_json, format_markdown, format_text
from backend.reports.llm_narrator import narrate_anomaly
from backend.reports.report_builder import build_report, store_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


@router.get("")
def list_reports(
    request: Request,
    severity: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List generated bug reports with optional filters."""
    conn = _get_db(request)
    query = "SELECT * FROM bug_reports WHERE 1=1"
    params: list = []

    if severity:
        query += " AND severity = ?"
        params.append(severity)

    query += " ORDER BY generated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return {
        "data": [_row_to_dict(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


@router.get("/{report_id}")
def get_report(
    request: Request,
    report_id: str,
    fmt: str = Query(default="json", pattern="^(json|markdown|text)$"),
) -> dict:
    """Get a single bug report by ID in the requested format."""
    conn = _get_db(request)
    row = conn.execute("SELECT * FROM bug_reports WHERE report_id = ?", (report_id,)).fetchone()
    if not row:
        return {"error": "not_found"}

    report = _row_to_dict(row)

    if fmt == "markdown":
        return {"report_id": report_id, "format": "markdown", "content": format_markdown(report)}
    if fmt == "text":
        return {"report_id": report_id, "format": "text", "content": format_text(report)}
    return format_json(report)


@router.post("/generate")
async def generate_report(request: Request, anomaly_id: str) -> dict:
    """Generate a bug report from an anomaly ID."""
    conn = _get_db(request)
    settings = request.app.state.settings

    # Fetch anomaly
    row = conn.execute("SELECT * FROM anomalies WHERE anomaly_id = ?", (anomaly_id,)).fetchone()
    if not row:
        return {"error": "anomaly_not_found"}

    anomaly = dict(row)

    # Check if report already exists
    existing = conn.execute(
        "SELECT report_id FROM bug_reports WHERE anomaly_id = ?", (anomaly_id,)
    ).fetchone()
    if existing:
        return {"error": "report_exists", "report_id": existing["report_id"]}

    # Build report
    report = build_report(anomaly, conn)

    # Generate LLM narration
    evidence = {}
    if anomaly.get("evidence_json"):
        try:
            evidence = json.loads(anomaly["evidence_json"])
        except json.JSONDecodeError:
            evidence = {}

    narration_result = await narrate_anomaly(
        anomaly_type=anomaly["anomaly_type"],
        evidence=evidence,
        rule_id=anomaly.get("rule_id", ""),
        severity=anomaly["severity"],
        api_key=settings.anthropic_api_key,
    )
    report["plain_english"] = narration_result["narration"]
    report["input_tokens"] = narration_result["input_tokens"]
    report["output_tokens"] = narration_result["output_tokens"]

    # Store formatted outputs
    report["format_markdown"] = format_markdown(report)
    report["format_json"] = json.dumps(format_json(report))

    # Persist
    stored = store_report(report, conn)
    if not stored:
        return {"error": "store_failed"}

    return {
        "report_id": report["report_id"],
        "anomaly_id": anomaly_id,
        "severity": report["severity"],
        "title": report["title"],
        "generated": True,
    }


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a Row to a dict, parsing JSON fields."""
    d = dict(row)
    json_fields = (
        "evidence_json",
        "chain_references",
        "reproduction_context",
        "recommended_investigation",
    )
    for field in json_fields:
        if d.get(field) and isinstance(d[field], str):
            with contextlib.suppress(json.JSONDecodeError):
                d[field] = json.loads(d[field])
    return d

"""Report formatter — renders bug reports to markdown, JSON, and plain text.

Produces the exact format specified in the Build Bible.
"""

import json
from datetime import UTC, datetime


def format_markdown(report: dict) -> str:
    """Render a report as formatted markdown."""
    evidence = _parse_json(report.get("evidence_json", "{}"))
    chain_refs = _parse_json(report.get("chain_references", "[]"))
    reproduction = _parse_json(report.get("reproduction_context", "{}"))
    investigation = _parse_json(report.get("recommended_investigation", "[]"))

    generated_at = _format_timestamp(report.get("generated_at", 0))

    lines = [
        "# MONOLITH — FIELD DISPATCH",
        "",
        f"**Intercept ID:** {report['report_id']}",
        f"**Timestamp:** {generated_at}",
        f"**Threat Level:** {report['severity']}",
        f"**Classification:** {report['category']}",
        f"**Source:** {report.get('anomaly_id', '')} / {reproduction.get('rule_id', '')}",
        "**Status:** UNVERIFIED",
        "",
        "---",
        "",
        "## Situation",
        "",
        report.get("summary", "No intel available."),
        "",
        "---",
        "",
        "## Affected Assets",
        "",
    ]

    affected = _parse_json(json.dumps(report.get("affected_entities", {})))
    if isinstance(affected, str):
        affected = _parse_json(affected)
    for key, val in (affected if isinstance(affected, dict) else {}).items():
        lines.append(f"- **{key}:** `{val}`")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Raw Evidence",
            "",
            "```json",
            json.dumps(evidence, indent=2),
            "```",
            "",
            "---",
            "",
            "## Chain Trail",
            "",
        ]
    )

    if chain_refs and isinstance(chain_refs, list):
        for ref in chain_refs:
            label = ref.get("label", ref.get("type", "reference"))
            url = ref.get("explorer_url", "")
            hash_val = ref.get("hash", ref.get("number", ""))
            lines.append(f"- **{label}:** `{hash_val}` — [Trace on Explorer]({url})")
    else:
        lines.append("No chain trail recovered.")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Detection Context",
            "",
            "```json",
            json.dumps(reproduction, indent=2),
            "```",
            "",
            "---",
            "",
            "## Field Orders",
            "",
        ]
    )

    if isinstance(investigation, list):
        for i, step in enumerate(investigation, 1):
            lines.append(f"{i}. {step}")
    else:
        lines.append("No standing orders for this anomaly type.")

    # Plain English section
    plain = report.get("plain_english", "")
    if plain:
        lines.extend(
            [
                "",
                "---",
                "",
                "## Intel Brief",
                "",
                plain,
            ]
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "*MONOLITH — Frontier Chain Intelligence*",
        ]
    )

    return "\n".join(lines)


def format_json(report: dict) -> dict:
    """Render a report as a machine-readable JSON dict."""
    return {
        "report_id": report["report_id"],
        "anomaly_id": report.get("anomaly_id", ""),
        "title": report.get("title", ""),
        "severity": report["severity"],
        "category": report["category"],
        "summary": report.get("summary", ""),
        "affected_entities": report.get("affected_entities", {}),
        "evidence": _parse_json(report.get("evidence_json", "{}")),
        "chain_references": _parse_json(report.get("chain_references", "[]")),
        "reproduction_context": _parse_json(report.get("reproduction_context", "{}")),
        "recommended_investigation": _parse_json(report.get("recommended_investigation", "[]")),
        "plain_english": report.get("plain_english", ""),
        "generated_at": report.get("generated_at", 0),
        "generated_at_iso": _format_timestamp(report.get("generated_at", 0)),
        "version": "0.4.0",
    }


def format_text(report: dict) -> str:
    """Render a report as plain text (for Discord/forum posting)."""
    evidence = _parse_json(report.get("evidence_json", "{}"))
    investigation = _parse_json(report.get("recommended_investigation", "[]"))
    generated_at = _format_timestamp(report.get("generated_at", 0))

    lines = [
        "MONOLITH — FIELD DISPATCH",
        "=" * 50,
        f"Intercept:  {report['report_id']}",
        f"Timestamp:  {generated_at}",
        f"Threat:     {report['severity']}",
        f"Class:      {report['category']}",
        "",
        "SITUATION",
        "-" * 50,
        report.get("summary", "No intel."),
        "",
        "RAW EVIDENCE",
        "-" * 50,
        json.dumps(evidence, indent=2),
        "",
    ]

    plain = report.get("plain_english", "")
    if plain:
        lines.extend(
            [
                "INTEL BRIEF",
                "-" * 50,
                plain,
                "",
            ]
        )

    if isinstance(investigation, list) and investigation:
        lines.append("FIELD ORDERS")
        lines.append("-" * 50)
        for i, step in enumerate(investigation, 1):
            lines.append(f"  {i}. {step}")
        lines.append("")

    lines.extend(
        [
            "=" * 50,
            "MONOLITH — Frontier Chain Intelligence",
        ]
    )

    return "\n".join(lines)


def _parse_json(val) -> dict | list:
    """Safely parse a JSON string, returning empty dict on failure."""
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


def _format_timestamp(ts: int) -> str:
    """Format a Unix timestamp as ISO 8601."""
    if not ts:
        return "unknown"
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

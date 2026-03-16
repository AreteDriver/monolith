"""Tests for report formatter — markdown, JSON, and plain text output."""

import json

from backend.reports.formatter import format_json, format_markdown, format_text


def _sample_report():
    return {
        "report_id": "MNL-20260311-0001",
        "anomaly_id": "ANM-001",
        "title": "Orphan Object — Object 0xabcd...ef12",
        "severity": "MEDIUM",
        "category": "CONTINUITY",
        "summary": "Event recorded for unknown object.",
        "affected_entities": {"object_id": "0xabcdef12", "system_id": "30012602"},
        "evidence_json": json.dumps({"description": "Orphan event detected"}),
        "plain_english": "An event was found for an object not in the database.",
        "chain_references": json.dumps(
            [
                {
                    "type": "transaction",
                    "hash": "0xdeadbeef",
                    "explorer_url": "https://sepolia-optimism.etherscan.io/tx/0xdeadbeef",
                },
            ]
        ),
        "reproduction_context": json.dumps({"rule_id": "C1", "detector": "continuity"}),
        "recommended_investigation": json.dumps(
            [
                "Check indexer logs",
                "Query chain for object events",
            ]
        ),
        "generated_at": 1741700000,
    }


def test_format_markdown_has_headers():
    """Markdown output includes all section headers."""
    md = format_markdown(_sample_report())
    assert "# MONOLITH BUG REPORT" in md
    assert "## Summary" in md
    assert "## Affected Entities" in md
    assert "## Evidence" in md
    assert "## Chain References" in md
    assert "## Reproduction Context" in md
    assert "## Recommended Investigation" in md
    assert "## Plain English" in md


def test_format_markdown_contains_report_metadata():
    """Markdown contains report ID, severity, category."""
    md = format_markdown(_sample_report())
    assert "MNL-20260311-0001" in md
    assert "MEDIUM" in md
    assert "CONTINUITY" in md


def test_format_markdown_chain_references():
    """Markdown renders chain reference links."""
    md = format_markdown(_sample_report())
    assert "0xdeadbeef" in md
    assert "View on Explorer" in md


def test_format_markdown_investigation_numbered():
    """Markdown renders investigation steps as numbered list."""
    md = format_markdown(_sample_report())
    assert "1. Check indexer logs" in md
    assert "2. Query chain for object events" in md


def test_format_json_structure():
    """JSON format contains all required keys."""
    result = format_json(_sample_report())
    assert result["report_id"] == "MNL-20260311-0001"
    assert result["severity"] == "MEDIUM"
    assert result["category"] == "CONTINUITY"
    assert result["version"] == "0.3.0"
    assert result["generated_at_iso"]
    assert isinstance(result["evidence"], dict)
    assert isinstance(result["chain_references"], list)
    assert isinstance(result["recommended_investigation"], list)


def test_format_text_has_sections():
    """Plain text output includes key sections."""
    txt = format_text(_sample_report())
    assert "MONOLITH BUG REPORT" in txt
    assert "SUMMARY" in txt
    assert "EVIDENCE" in txt
    assert "PLAIN ENGLISH" in txt
    assert "RECOMMENDED INVESTIGATION" in txt
    assert "MNL-20260311-0001" in txt


def test_format_text_investigation_numbered():
    """Plain text investigation steps are indented and numbered."""
    txt = format_text(_sample_report())
    assert "  1. Check indexer logs" in txt
    assert "  2. Query chain for object events" in txt


def test_format_markdown_no_plain_english_when_empty():
    """Markdown omits Plain English section when empty."""
    report = _sample_report()
    report["plain_english"] = ""
    md = format_markdown(report)
    assert "## Plain English" not in md


def test_format_text_no_plain_english_when_empty():
    """Text omits Plain English section when empty."""
    report = _sample_report()
    report["plain_english"] = ""
    txt = format_text(report)
    assert "PLAIN ENGLISH" not in txt


def test_format_json_zero_timestamp():
    """JSON format handles zero timestamp gracefully."""
    report = _sample_report()
    report["generated_at"] = 0
    result = format_json(report)
    assert result["generated_at_iso"] == "unknown"

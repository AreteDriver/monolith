"""Tests for report builder — ID generation."""

from backend.reports.report_builder import generate_report_id


def test_report_id_format():
    """Report ID matches MNL-YYYYMMDD-NNNN format."""
    rid = generate_report_id()
    assert rid.startswith("MNL-")
    parts = rid.split("-")
    assert len(parts) == 3
    assert len(parts[1]) == 8  # YYYYMMDD
    assert len(parts[2]) == 4  # seq

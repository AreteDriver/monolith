"""Tests for eval/detection_quality.py scoring logic."""

from backend.db.database import init_db
from eval.detection_quality import CheckerResult, compute_checker_result, run_eval

# --- compute_checker_result ---


def test_perfect_detection():
    gt = [("TYPE_A", "obj-1"), ("TYPE_A", "obj-2")]
    detected = [("TYPE_A", "obj-1"), ("TYPE_A", "obj-2")]
    result = compute_checker_result("TestChecker", ["TYPE_A"], detected, gt)
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0
    assert result.true_positives == 2
    assert result.false_positives == 0
    assert result.false_negatives == 0
    assert result.passed()


def test_false_positives_reduce_precision():
    gt = [("TYPE_A", "obj-1")]
    detected = [("TYPE_A", "obj-1"), ("TYPE_A", "obj-extra")]
    result = compute_checker_result("TestChecker", ["TYPE_A"], detected, gt)
    assert result.precision == 0.5
    assert result.recall == 1.0
    assert result.false_positives == 1


def test_false_negatives_reduce_recall():
    gt = [("TYPE_A", "obj-1"), ("TYPE_A", "obj-2")]
    detected = [("TYPE_A", "obj-1")]
    result = compute_checker_result("TestChecker", ["TYPE_A"], detected, gt)
    assert result.precision == 1.0
    assert result.recall == 0.5
    assert result.false_negatives == 1


def test_no_detections():
    gt = [("TYPE_A", "obj-1")]
    detected = []
    result = compute_checker_result("TestChecker", ["TYPE_A"], detected, gt)
    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.f1 == 0.0
    assert not result.passed()


def test_no_ground_truth_or_detections():
    result = compute_checker_result("TestChecker", ["TYPE_A"], [], [])
    assert result.notes != ""  # Should have a warning note
    assert result.precision == 0.0


def test_filters_by_anomaly_type():
    gt = [("TYPE_A", "obj-1"), ("TYPE_B", "obj-2")]
    detected = [("TYPE_A", "obj-1"), ("TYPE_B", "obj-2")]
    result = compute_checker_result("AChecker", ["TYPE_A"], detected, gt)
    assert result.true_positives == 1  # Only counts TYPE_A


def test_passed_threshold():
    """Precision >= 0.85 and recall >= 0.70 required."""
    result = CheckerResult(
        checker_name="Test",
        anomaly_types=["X"],
        true_positives=7,
        false_positives=1,
        false_negatives=2,
        precision=0.875,
        recall=0.778,
        f1=0.823,
    )
    assert result.passed()

    result_fail = CheckerResult(
        checker_name="Test",
        anomaly_types=["X"],
        true_positives=5,
        false_positives=5,
        false_negatives=0,
        precision=0.5,
        recall=1.0,
        f1=0.667,
    )
    assert not result_fail.passed()


# --- run_eval with real DB ---


def test_run_eval_with_seeded_db():
    """Run eval against a seeded in-memory DB."""
    import json
    import time

    conn = init_db(":memory:")
    now = int(time.time())

    # Insert anomalies matching EVAL_GROUND_TRUTH
    for atype, obj_id in [
        ("PHANTOM_ITEM_CHANGE", "0x4f2a8c91d3e7b5f2a8c91d3e7b5f2a8c91d3e7b5"),
        ("UNEXPLAINED_OWNERSHIP_CHANGE", "0xc5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3"),
        ("RESURRECTION", "0xa7b3c1d9e8f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0"),
        ("STATE_GAP", "0xa7b3c1d9e8f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0"),
        ("ORPHAN_OBJECT", "0xff00ee11dd22cc33bb44aa5599886677ff00ee11"),
        ("SUPPLY_DISCREPANCY", "0x4f2a8c91d3e7b5f2a8c91d3e7b5f2a8c91d3e7b5"),
    ]:
        conn.execute(
            "INSERT INTO anomalies (anomaly_id, anomaly_type, severity, category, "
            "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"MNL-{atype[:8]}",
                atype,
                "HIGH",
                "TEST",
                "test",
                "X1",
                obj_id,
                "",
                now,
                json.dumps({}),
                "UNVERIFIED",
            ),
        )
    conn.commit()

    # Write to temp file for the eval to read
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name

    # Copy in-memory DB to file
    import sqlite3

    file_conn = sqlite3.connect(tmp_path)
    conn.backup(file_conn)
    file_conn.close()
    conn.close()

    try:
        summary = run_eval(tmp_path)
        assert summary.passed
        assert summary.overall_precision == 1.0
        assert summary.overall_recall == 1.0
        assert len(summary.checkers) == 3
    finally:
        import os

        os.unlink(tmp_path)

"""Tests for detection base classes — Anomaly dataclass and BaseChecker."""

from backend.detection.base import Anomaly


def test_anomaly_auto_classifies():
    """Anomaly auto-classifies severity and category from rule_id."""
    a = Anomaly(
        anomaly_type="RESURRECTION",
        rule_id="C2",
        detector="continuity_checker",
        object_id="obj-001",
    )
    assert a.severity == "CRITICAL"
    assert a.category == "DATA_INTEGRITY"


def test_anomaly_generates_id():
    """Anomaly generates an ID in MNL-YYYYMMDD-NNNN format."""
    a = Anomaly(
        anomaly_type="TEST",
        rule_id="C1",
        detector="test",
        object_id="obj-001",
    )
    assert a.anomaly_id.startswith("MNL-")
    parts = a.anomaly_id.split("-")
    assert len(parts) == 3


def test_anomaly_to_dict():
    """to_dict produces all required fields."""
    a = Anomaly(
        anomaly_type="STATE_GAP",
        rule_id="C3",
        detector="continuity_checker",
        object_id="obj-001",
        system_id="sys-001",
        evidence={"delta": 42},
    )
    d = a.to_dict()
    assert d["anomaly_type"] == "STATE_GAP"
    assert d["rule_id"] == "C3"
    assert d["severity"] == "HIGH"
    assert d["evidence"]["delta"] == 42
    assert d["object_id"] == "obj-001"


def test_anomaly_respects_explicit_severity():
    """Explicit severity overrides auto-classification."""
    a = Anomaly(
        anomaly_type="TEST",
        rule_id="C1",
        detector="test",
        object_id="obj-001",
        severity="CRITICAL",
        category="EXPLOIT_VECTOR",
    )
    assert a.severity == "CRITICAL"
    assert a.category == "EXPLOIT_VECTOR"

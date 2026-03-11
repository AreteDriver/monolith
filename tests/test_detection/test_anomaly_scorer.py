"""Tests for anomaly scorer — severity classification."""

from backend.detection.anomaly_scorer import classify_anomaly, severity_weight


def test_classify_critical_rules():
    """Critical rules get CRITICAL severity."""
    for rule_id in ["C2", "E3", "E4", "A5", "S1", "S2"]:
        severity, category = classify_anomaly(rule_id)
        assert severity == "CRITICAL", f"Rule {rule_id} should be CRITICAL"


def test_classify_high_rules():
    """High rules get HIGH severity."""
    for rule_id in ["C3", "E1", "E2", "A1", "A2", "A4", "S3"]:
        severity, _ = classify_anomaly(rule_id)
        assert severity == "HIGH", f"Rule {rule_id} should be HIGH"


def test_classify_medium_rules():
    """Medium rules get MEDIUM severity."""
    for rule_id in ["C1", "C4", "A3", "S4"]:
        severity, _ = classify_anomaly(rule_id)
        assert severity == "MEDIUM", f"Rule {rule_id} should be MEDIUM"


def test_classify_unknown_rule():
    """Unknown rule gets LOW/BEHAVIORAL default."""
    severity, category = classify_anomaly("Z99")
    assert severity == "LOW"
    assert category == "BEHAVIORAL"


def test_severity_weights():
    """Severity weights are ordered correctly."""
    assert severity_weight("CRITICAL") > severity_weight("HIGH")
    assert severity_weight("HIGH") > severity_weight("MEDIUM")
    assert severity_weight("MEDIUM") > severity_weight("LOW")
    assert severity_weight("UNKNOWN") == 0

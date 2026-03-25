"""Tests for eval/narration_eval.py scoring functions."""

from eval.narration_eval import (
    NarrationScore,
    check_hallucination,
    score_actionability,
    score_factual_grounding,
    score_severity_alignment,
)

# --- score_factual_grounding ---


def test_grounding_empty_evidence():
    assert score_factual_grounding("anything", {}) == 0.5


def test_grounding_no_identifiable_tokens():
    assert score_factual_grounding("text", {"a": 1, "b": 2}) == 0.5


def test_grounding_tokens_found():
    evidence = {"object_id": "0xabcdef1234567890", "system_id": "30012602"}
    narration = "Object 0xabcdef1234567890 in system 30012602 showed anomalous behavior."
    score = score_factual_grounding(narration, evidence)
    assert score > 0.5


def test_grounding_tokens_missing():
    evidence = {"object_id": "0xabcdef1234567890", "tx_hash": "0xdeadbeef00112233"}
    narration = "An anomaly was detected in the frontier."
    score = score_factual_grounding(narration, evidence)
    assert score <= 0.5


# --- score_severity_alignment ---


def test_severity_critical_with_matching_words():
    score = score_severity_alignment("Critical alert — immediate action required", "CRITICAL")
    assert score >= 0.7


def test_severity_critical_with_opposing_words():
    score = score_severity_alignment("This is routine and minor, low concern", "CRITICAL")
    assert score < 0.3


def test_severity_low_with_matching_words():
    score = score_severity_alignment("Low priority, minor and informational only", "LOW")
    assert score >= 0.7


def test_severity_low_with_opposing_words():
    score = score_severity_alignment("Critical and immediate, urgent action needed", "LOW")
    assert score < 0.3


def test_severity_neutral_language():
    score = score_severity_alignment("Object changed state between snapshots.", "HIGH")
    assert score == 0.3  # No expected words, no opposing = neutral


def test_severity_unknown_level():
    score = score_severity_alignment("text", "BANANA")
    assert score == 0.5


# --- score_actionability ---


def test_actionability_with_action_words():
    score = score_actionability("Investigate the chain events and verify the transaction.")
    assert score >= 0.5


def test_actionability_no_action_words():
    score = score_actionability("The object changed state between two snapshots.")
    assert score == 0.0


def test_actionability_many_action_words():
    text = "Investigate, review, check, and verify all transactions. Monitor and escalate."
    score = score_actionability(text)
    assert score == 1.0


# --- check_hallucination ---


def test_hallucination_clean():
    evidence = {"value": 12345, "hash": "0xabcdef1234567890ab"}
    narration = "Value 12345 found at hash 0xabcdef1234567890ab."
    flagged, details = check_hallucination(narration, evidence)
    assert flagged is False
    assert details == []


def test_hallucination_fabricated_number():
    evidence = {"value": 100}
    narration = "The balance was 99999 tokens, far exceeding the limit."
    flagged, details = check_hallucination(narration, evidence)
    assert flagged is True
    assert any("99999" in d for d in details)


def test_hallucination_fabricated_tx_hash():
    evidence = {"tx": "0xaaa111bbb222ccc333"}
    narration = "Transaction 0xfff999eee888ddd777 was suspicious."
    flagged, details = check_hallucination(narration, evidence)
    assert flagged is True
    assert any("tx hash" in d for d in details)


def test_hallucination_skips_year_numbers():
    evidence = {}
    narration = "This was detected in 2026 during routine monitoring."
    flagged, _ = check_hallucination(narration, evidence)
    assert flagged is False


def test_hallucination_no_specifics():
    evidence = {"description": "Something happened"}
    narration = "An anomaly was detected in the frontier region."
    flagged, _ = check_hallucination(narration, evidence)
    assert flagged is False


# --- NarrationScore composite ---


def test_composite_score_no_hallucination():
    score = NarrationScore(
        report_id="R1",
        anomaly_id="A1",
        severity="HIGH",
        factual_grounding=0.9,
        severity_alignment=0.8,
        actionability=0.7,
        hallucination_flag=False,
    )
    expected = round((0.9 + 0.8 + 0.7) / 3, 4)
    assert score.composite_score == expected


def test_composite_score_with_hallucination():
    score = NarrationScore(
        report_id="R1",
        anomaly_id="A1",
        severity="HIGH",
        factual_grounding=0.9,
        severity_alignment=0.8,
        actionability=0.7,
        hallucination_flag=True,
    )
    expected = round((0.9 + 0.8 + 0.7) / 3 * 0.5, 4)
    assert score.composite_score == expected

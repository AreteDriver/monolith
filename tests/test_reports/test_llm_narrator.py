"""Tests for LLM narrator — template fallback and API mocking."""

import pytest

from backend.reports.llm_narrator import TEMPLATES, narrate_anomaly


@pytest.mark.asyncio
async def test_template_fallback_no_api_key():
    """Without API key, uses template fallback."""
    result = await narrate_anomaly(
        anomaly_type="ORPHAN_OBJECT",
        evidence={"description": "Event for unknown object"},
        rule_id="C1",
        severity="MEDIUM",
        api_key="",
    )
    assert TEMPLATES["ORPHAN_OBJECT"] in result


@pytest.mark.asyncio
async def test_template_fallback_unknown_type():
    """Unknown anomaly type gets generic fallback."""
    result = await narrate_anomaly(
        anomaly_type="UNKNOWN_TYPE",
        evidence={},
        rule_id="X1",
        severity="LOW",
        api_key="",
    )
    assert "UNKNOWN_TYPE" in result


@pytest.mark.asyncio
async def test_template_appends_specifics():
    """Template appends evidence description when different from template."""
    result = await narrate_anomaly(
        anomaly_type="RESURRECTION",
        evidence={"description": "Object xyz reappeared at block 999"},
        rule_id="C2",
        severity="CRITICAL",
        api_key="",
    )
    assert "Specifics:" in result
    assert "Object xyz reappeared" in result


@pytest.mark.asyncio
async def test_template_no_duplicate_description():
    """Template does not duplicate when evidence description matches template."""
    template_text = TEMPLATES["ORPHAN_OBJECT"]
    result = await narrate_anomaly(
        anomaly_type="ORPHAN_OBJECT",
        evidence={"description": template_text},
        rule_id="C1",
        severity="MEDIUM",
        api_key="",
    )
    assert "Specifics:" not in result


@pytest.mark.asyncio
async def test_all_anomaly_types_have_templates():
    """All standard anomaly types have template narrations."""
    expected_types = [
        "ORPHAN_OBJECT",
        "RESURRECTION",
        "STATE_GAP",
        "STUCK_OBJECT",
        "SUPPLY_DISCREPANCY",
        "UNEXPLAINED_DESTRUCTION",
        "DUPLICATE_MINT",
        "NEGATIVE_BALANCE",
        "CONTRACT_STATE_MISMATCH",
        "PHANTOM_ITEM_CHANGE",
        "UNEXPLAINED_OWNERSHIP_CHANGE",
        "DUPLICATE_TRANSACTION",
        "BLOCK_PROCESSING_GAP",
    ]
    for atype in expected_types:
        assert atype in TEMPLATES, f"Missing template for {atype}"


@pytest.mark.asyncio
async def test_api_failure_falls_back(monkeypatch):
    """When API call fails, falls back to template."""

    # Provide a fake API key to trigger the API path, but mock anthropic to fail
    async def fake_create(*args, **kwargs):
        raise ConnectionError("API down")

    monkeypatch.setattr("backend.reports.llm_narrator.anthropic", None, raising=False)

    result = await narrate_anomaly(
        anomaly_type="ORPHAN_OBJECT",
        evidence={},
        rule_id="C1",
        severity="MEDIUM",
        api_key="sk-fake-key",
    )
    # Should fall back to template
    assert TEMPLATES["ORPHAN_OBJECT"] in result

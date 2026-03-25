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
    assert TEMPLATES["ORPHAN_OBJECT"] in result["narration"]
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


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
    assert "UNKNOWN_TYPE" in result["narration"]


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
    assert "Specifics:" in result["narration"]
    assert "Object xyz reappeared" in result["narration"]


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
    assert "Specifics:" not in result["narration"]


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
    assert TEMPLATES["ORPHAN_OBJECT"] in result["narration"]
    assert result["input_tokens"] is None


@pytest.mark.asyncio
async def test_api_success_returns_tokens(monkeypatch):
    """Successful API call returns narration + token counts."""
    import sys
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="  Wreckage adrift. Investigate immediately.  ")]
    mock_response.usage.input_tokens = 250
    mock_response.usage.output_tokens = 30

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    mock_anthropic_mod = MagicMock()
    mock_anthropic_mod.AsyncAnthropic.return_value = mock_client

    # Patch anthropic in sys.modules so `import anthropic` inside the function
    # picks up our mock instead of the real SDK
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic_mod)

    result = await narrate_anomaly(
        anomaly_type="ORPHAN_OBJECT",
        evidence={"description": "ghost object"},
        rule_id="C1",
        severity="MEDIUM",
        api_key="sk-test-key",  # noqa: S106
    )
    assert result["narration"] == "Wreckage adrift. Investigate immediately."
    assert result["input_tokens"] == 250
    assert result["output_tokens"] == 30

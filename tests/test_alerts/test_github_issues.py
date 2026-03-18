"""Tests for GitHub issue auto-filer."""

import time

import httpx
import pytest

from backend.alerts.github_issues import (
    _build_issue_body,
    _dedup_key,
    _filed_cache,
    _is_duplicate,
    _mark_filed,
    clear_cache,
    file_github_issue,
    get_filed_count,
)
from backend.db.database import init_db


def _sample_anomaly(severity="CRITICAL"):
    return {
        "anomaly_id": "MNLT-20260312-0001",
        "anomaly_type": "DUPLICATE_MINT",
        "severity": severity,
        "category": "EXPLOIT_VECTOR",
        "detector": "economic_checker",
        "rule_id": "E3",
        "object_id": "0xabcdef1234567890",
        "system_id": "30002187",
        "detected_at": int(time.time()),
        "evidence": {
            "description": "Token minted twice with same parameters",
            "tx_digest": "0x123abc",
            "block": "12345",
        },
    }


@pytest.fixture(autouse=True)
def _clear():
    clear_cache()
    yield
    clear_cache()


# --- Dedup tests ---


def test_dedup_key_deterministic():
    """Same anomaly type + object_id produces same key."""
    a = _sample_anomaly()
    assert _dedup_key(a) == _dedup_key(a)


def test_dedup_key_differs_by_type():
    """Different anomaly types produce different keys."""
    a1 = _sample_anomaly()
    a2 = _sample_anomaly()
    a2["anomaly_type"] = "RESURRECTION"
    assert _dedup_key(a1) != _dedup_key(a2)


def test_dedup_key_differs_by_object():
    """Different object IDs produce different keys."""
    a1 = _sample_anomaly()
    a2 = _sample_anomaly()
    a2["object_id"] = "0xdifferent"
    assert _dedup_key(a1) != _dedup_key(a2)


def test_is_duplicate_false_initially():
    """First occurrence is not a duplicate."""
    assert _is_duplicate(_sample_anomaly()) is False


def test_is_duplicate_true_after_filed():
    """After marking filed, same anomaly is duplicate."""
    a = _sample_anomaly()
    _mark_filed(a)
    assert _is_duplicate(a) is True


def test_dedup_expires():
    """Expired entries are pruned."""
    a = _sample_anomaly()
    key = _dedup_key(a)
    # Manually insert expired entry
    _filed_cache[key] = time.time() - 7200  # 2 hours ago
    assert _is_duplicate(a) is False


def test_clear_cache():
    """clear_cache empties the dedup cache."""
    _mark_filed(_sample_anomaly())
    assert len(_filed_cache) > 0
    clear_cache()
    assert len(_filed_cache) == 0


# --- Issue body tests ---


def test_build_issue_body_contains_fields():
    """Issue body contains key anomaly fields."""
    a = _sample_anomaly()
    body = _build_issue_body(a)
    assert "DUPLICATE_MINT" in body
    assert "CRITICAL" in body
    assert "E3" in body
    assert "MNLT-20260312-0001" in body
    assert "0xabcdef1234567890" in body
    assert "0x123abc" in body  # tx_digest
    assert "Token minted twice" in body


def test_build_issue_body_handles_missing_evidence():
    """Issue body handles missing evidence gracefully."""
    a = _sample_anomaly()
    a["evidence"] = {}
    body = _build_issue_body(a)
    assert "No description available" in body


# --- Filing tests ---


@pytest.mark.asyncio
async def test_no_repo_returns_false():
    """Returns False when no repo configured."""
    result = await file_github_issue("", "token123", _sample_anomaly())
    assert result is False


@pytest.mark.asyncio
async def test_no_token_returns_false():
    """Returns False when no token configured."""
    result = await file_github_issue("AreteDriver/monolith", "", _sample_anomaly())
    assert result is False


@pytest.mark.asyncio
async def test_non_critical_skipped():
    """Non-CRITICAL severities are not filed."""
    for severity in ("LOW", "MEDIUM", "HIGH"):
        result = await file_github_issue(
            "AreteDriver/monolith",
            "token123",
            _sample_anomaly(severity),
        )
        assert result is False


@pytest.mark.asyncio
async def test_successful_filing(respx_mock):
    """CRITICAL anomaly files a GitHub issue."""
    repo = "AreteDriver/monolith"
    url = f"https://api.github.com/repos/{repo}/issues"
    respx_mock.post(url).respond(
        201,
        json={"html_url": f"https://github.com/{repo}/issues/42"},
    )

    result = await file_github_issue(repo, "ghp_testtoken123", _sample_anomaly())
    assert result is True


@pytest.mark.asyncio
async def test_filing_sets_dedup(respx_mock):
    """After filing, same anomaly is deduplicated."""
    repo = "AreteDriver/monolith"
    url = f"https://api.github.com/repos/{repo}/issues"
    respx_mock.post(url).respond(
        201,
        json={"html_url": f"https://github.com/{repo}/issues/42"},
    )

    a = _sample_anomaly()
    await file_github_issue(repo, "ghp_testtoken123", a)
    # Second call should be deduped
    result = await file_github_issue(repo, "ghp_testtoken123", a)
    assert result is False


@pytest.mark.asyncio
async def test_api_error_returns_false(respx_mock):
    """Non-201 response returns False without crashing."""
    repo = "AreteDriver/monolith"
    url = f"https://api.github.com/repos/{repo}/issues"
    respx_mock.post(url).respond(422, json={"message": "Validation Failed"})

    result = await file_github_issue(repo, "ghp_testtoken123", _sample_anomaly())
    assert result is False


@pytest.mark.asyncio
async def test_network_error_returns_false(respx_mock):
    """Network errors return False without crashing."""
    repo = "AreteDriver/monolith"
    url = f"https://api.github.com/repos/{repo}/issues"
    respx_mock.post(url).mock(side_effect=httpx.ConnectError("Connection refused"))

    result = await file_github_issue(repo, "ghp_testtoken123", _sample_anomaly())
    assert result is False


@pytest.mark.asyncio
async def test_issue_labels(respx_mock):
    """Filed issue includes correct labels."""
    repo = "AreteDriver/monolith"
    url = f"https://api.github.com/repos/{repo}/issues"

    captured = {}

    def capture_request(request):
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(
            201,
            json={"html_url": f"https://github.com/{repo}/issues/1"},
        )

    respx_mock.post(url).mock(side_effect=capture_request)

    await file_github_issue(repo, "ghp_testtoken123", _sample_anomaly())

    assert "bug" in captured["labels"]
    assert "chain-integrity" in captured["labels"]
    assert "critical" in captured["labels"]


@pytest.mark.asyncio
async def test_issue_title_format(respx_mock):
    """Filed issue title contains anomaly type and rule."""
    repo = "AreteDriver/monolith"
    url = f"https://api.github.com/repos/{repo}/issues"

    captured = {}

    def capture_request(request):
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(
            201,
            json={"html_url": f"https://github.com/{repo}/issues/1"},
        )

    respx_mock.post(url).mock(side_effect=capture_request)

    await file_github_issue(repo, "ghp_testtoken123", _sample_anomaly())

    assert "[CRITICAL]" in captured["title"]
    assert "DUPLICATE_MINT" in captured["title"]
    assert "E3" in captured["title"]


# --- Filed count tests ---


def test_get_filed_count_zero_initially():
    """Counter starts at zero after clear."""
    assert get_filed_count() == 0


def test_get_filed_count_with_db():
    """get_filed_count reads from database when connection provided."""
    conn = init_db(":memory:")
    assert get_filed_count(conn) == 0
    conn.close()


@pytest.mark.asyncio
async def test_filed_count_increments_on_success(respx_mock):
    """Counter increments after successful filing."""
    repo = "AreteDriver/monolith"
    url = f"https://api.github.com/repos/{repo}/issues"
    respx_mock.post(url).respond(
        201,
        json={"html_url": f"https://github.com/{repo}/issues/42"},
    )

    assert get_filed_count() == 0
    await file_github_issue(repo, "ghp_testtoken123", _sample_anomaly())
    assert get_filed_count() == 1


@pytest.mark.asyncio
async def test_filed_count_persisted_to_db(respx_mock):
    """Filed issue is persisted to the database."""
    conn = init_db(":memory:")
    repo = "AreteDriver/monolith"
    url = f"https://api.github.com/repos/{repo}/issues"
    respx_mock.post(url).respond(
        201,
        json={"html_url": f"https://github.com/{repo}/issues/99"},
    )

    await file_github_issue(repo, "ghp_testtoken123", _sample_anomaly(), conn)
    assert get_filed_count(conn) == 1

    # Verify the record details
    row = conn.execute("SELECT * FROM filed_issues").fetchone()
    assert row["anomaly_id"] == "MNLT-20260312-0001"
    assert row["issue_url"] == f"https://github.com/{repo}/issues/99"
    assert row["filed_at"] > 0
    conn.close()


@pytest.mark.asyncio
async def test_filed_count_no_increment_on_failure(respx_mock):
    """Counter does not increment on API failure."""
    repo = "AreteDriver/monolith"
    url = f"https://api.github.com/repos/{repo}/issues"
    respx_mock.post(url).respond(422, json={"message": "Validation Failed"})

    before = get_filed_count()
    await file_github_issue(repo, "ghp_testtoken123", _sample_anomaly())
    assert get_filed_count() == before

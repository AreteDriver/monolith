"""GitHub issue auto-filer — files issues for CRITICAL anomalies.

Non-blocking: if GitHub API fails, logs error but never crashes the detection pipeline.
Deduplicates: same anomaly_type + object_id won't file twice within 1 hour.
Tracks total issues filed via in-memory counter + database persistence.
"""

import hashlib
import logging
import sqlite3
import time
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

# In-memory dedup cache: key → timestamp of last filed issue
_filed_cache: dict[str, float] = {}

# In-memory counter for issues filed this process lifetime
_filed_count: int = 0

# Dedup window in seconds (1 hour)
_DEDUP_WINDOW = 3600

GITHUB_API = "https://api.github.com"


def _dedup_key(anomaly: dict) -> str:
    """Generate a dedup key from anomaly type + object_id."""
    atype = anomaly.get("anomaly_type", "")
    obj_id = anomaly.get("object_id", "")
    return hashlib.sha256(f"{atype}:{obj_id}".encode()).hexdigest()[:16]


def _is_duplicate(anomaly: dict) -> bool:
    """Check if this anomaly was already filed within the dedup window."""
    key = _dedup_key(anomaly)
    now = time.time()

    # Prune expired entries
    expired = [k for k, ts in _filed_cache.items() if now - ts > _DEDUP_WINDOW]
    for k in expired:
        del _filed_cache[k]

    return key in _filed_cache


def _mark_filed(anomaly: dict) -> None:
    """Record that this anomaly was filed."""
    key = _dedup_key(anomaly)
    _filed_cache[key] = time.time()


def _build_issue_body(anomaly: dict) -> str:
    """Template the GitHub issue body from anomaly data."""
    evidence = anomaly.get("evidence", {})
    description = evidence.get("description", "No description available")
    detected_at = anomaly.get("detected_at", 0)
    ts_str = datetime.fromtimestamp(detected_at, tz=UTC).isoformat() if detected_at else "unknown"

    tx_hash = evidence.get("tx_digest", evidence.get("txDigest", "N/A"))
    block_data = evidence.get("block", evidence.get("checkpoint", "N/A"))

    body = f"""## Automated Bug Report — CRITICAL Anomaly Detected

**Anomaly Type**: `{anomaly.get("anomaly_type", "UNKNOWN")}`
**Severity**: `{anomaly.get("severity", "UNKNOWN")}`
**Detection Rule**: `{anomaly.get("rule_id", "N/A")}`
**Anomaly ID**: `{anomaly.get("anomaly_id", "N/A")}`
**Detector**: `{anomaly.get("detector", "unknown")}`

### Detection Details

| Field | Value |
|-------|-------|
| Timestamp | {ts_str} |
| Object ID | `{anomaly.get("object_id", "N/A")}` |
| System ID | `{anomaly.get("system_id", "N/A")}` |
| Transaction Hash | `{tx_hash}` |
| Block/Checkpoint | `{block_data}` |

### Description

{description}

### Evidence

```json
{_format_evidence(evidence)}
```

---
*Filed automatically by MONOLITH v0.2.0 detection engine.*
"""
    return body


def _format_evidence(evidence: dict) -> str:
    """Format evidence dict as indented JSON string."""
    import json

    try:
        return json.dumps(evidence, indent=2, default=str)[:2000]
    except (TypeError, ValueError):
        return str(evidence)[:2000]


async def file_github_issue(
    repo: str,
    token: str,
    anomaly: dict,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """File a GitHub issue for a CRITICAL anomaly.

    Args:
        repo: GitHub repo in "owner/repo" format (e.g., "AreteDriver/monolith")
        token: GitHub personal access token
        anomaly: Anomaly dict from DetectionEngine
        conn: Optional database connection for persisting filed issue records

    Returns:
        True if issue was filed, False if skipped or failed.
    """
    if not repo or not token:
        return False

    severity = anomaly.get("severity", "LOW")
    if severity != "CRITICAL":
        return False

    if _is_duplicate(anomaly):
        logger.debug(
            "Skipping duplicate GitHub issue for %s/%s",
            anomaly.get("anomaly_type"),
            anomaly.get("object_id", "")[:16],
        )
        return False

    title = (
        f"[CRITICAL] {anomaly.get('anomaly_type', 'UNKNOWN')} — "
        f"Rule {anomaly.get('rule_id', '?')} "
        f"({anomaly.get('anomaly_id', 'N/A')})"
    )
    body = _build_issue_body(anomaly)
    labels = ["bug", "chain-integrity", "critical"]

    url = f"{GITHUB_API}/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "title": title,
        "body": body,
        "labels": labels,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 201:
                global _filed_count  # noqa: PLW0603
                issue_url = resp.json().get("html_url", "unknown")
                _mark_filed(anomaly)
                _filed_count += 1
                _record_filed_issue(conn, anomaly, issue_url)
                logger.info(
                    "GitHub issue filed: %s — %s",
                    anomaly.get("anomaly_type"),
                    issue_url,
                )
                return True
            logger.warning(
                "GitHub API returned %d: %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
    except (httpx.HTTPError, OSError):
        logger.exception("GitHub issue filing failed (non-blocking)")
        return False


def get_filed_count(conn: sqlite3.Connection | None = None) -> int:
    """Return total bug reports filed as GitHub issues.

    If a database connection is provided, returns the persistent count
    from the filed_issues table. Otherwise returns the in-memory counter
    for the current process lifetime.
    """
    if conn is not None:
        try:
            row = conn.execute("SELECT COUNT(*) FROM filed_issues").fetchone()
            return row[0] if row else 0
        except sqlite3.OperationalError:
            # Table may not exist yet
            return _filed_count
    return _filed_count


def _record_filed_issue(
    conn: sqlite3.Connection | None,
    anomaly: dict,
    issue_url: str,
) -> None:
    """Persist a filed issue record to the database."""
    if conn is None:
        return
    try:
        conn.execute(
            "INSERT INTO filed_issues (anomaly_id, issue_url, filed_at) VALUES (?, ?, ?)",
            (
                anomaly.get("anomaly_id", ""),
                issue_url,
                int(time.time()),
            ),
        )
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("filed_issues table not available — skipping persistence")


def clear_cache() -> None:
    """Clear the dedup cache and reset in-memory counter. Useful for testing."""
    global _filed_count  # noqa: PLW0603
    _filed_cache.clear()
    _filed_count = 0

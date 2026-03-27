"""End-to-end test: fire a CRITICAL anomaly and verify GitHub issue gets filed.

Usage:
    python test_bug_report_e2e.py          # dry-run (no GitHub call)
    python test_bug_report_e2e.py --live   # actually files a GitHub issue

Requires MONOLITH_GITHUB_REPO and MONOLITH_GITHUB_TOKEN in .env or env vars.
"""

import asyncio
import sys
import time

from backend.alerts.github_issues import clear_cache, file_github_issue
from backend.config import get_settings


def _make_test_anomaly() -> dict:
    """Create a realistic CRITICAL anomaly dict matching DetectionEngine output."""
    return {
        "anomaly_id": f"test-e2e-{int(time.time())}",
        "anomaly_type": "DUPLICATE_MINT",
        "severity": "CRITICAL",
        "rule_id": "E3",
        "detector": "economic_checker",
        "object_id": f"0xTEST_{int(time.time())}",
        "system_id": "30002187",
        "detected_at": int(time.time()),
        "evidence": {
            "description": "E2E test — duplicate mint detected on test object",
            "tx_digest": "0xABC123_TEST_DIGEST",
            "checkpoint": "999999",
            "count": 2,
            "expected": 1,
        },
    }


async def main():
    live = "--live" in sys.argv
    settings = get_settings()

    print(f"GitHub repo:  {settings.github_repo or '(not set)'}")
    print(
        "GitHub token: "
        f"{'***' + settings.github_token[-4:] if settings.github_token else '(not set)'}"
    )
    print(f"Mode:         {'LIVE — will file real issue' if live else 'DRY RUN'}")
    print()

    anomaly = _make_test_anomaly()
    print(f"Anomaly ID:   {anomaly['anomaly_id']}")
    print(f"Type:         {anomaly['anomaly_type']}")
    print(f"Severity:     {anomaly['severity']}")
    print(f"Object ID:    {anomaly['object_id']}")
    print()

    if not live:
        print("Dry run — checking config and anomaly shape only.")
        print("Run with --live to actually file a GitHub issue.")

        if not settings.github_repo:
            print("\nWARNING: MONOLITH_GITHUB_REPO not set. Set it in .env:")
            print("  MONOLITH_GITHUB_REPO=AreteDriver/monolith")
        if not settings.github_token:
            print("\nWARNING: MONOLITH_GITHUB_TOKEN not set. Set it in .env:")
            print("  MONOLITH_GITHUB_TOKEN=ghp_...")
        return

    if not settings.github_repo or not settings.github_token:
        print("ERROR: MONOLITH_GITHUB_REPO and MONOLITH_GITHUB_TOKEN must be set.")
        sys.exit(1)

    clear_cache()
    result = await file_github_issue(settings.github_repo, settings.github_token, anomaly)

    if result:
        print("Issue filed successfully. Check GitHub Issues tab.")
    else:
        print("Filing failed. Check logs above for details.")

    # Test dedup — same anomaly should be skipped
    result2 = await file_github_issue(settings.github_repo, settings.github_token, anomaly)
    print(
        f"Dedup test:   {'PASS (skipped duplicate)' if not result2 else 'FAIL (filed duplicate)'}"
    )

    # Test non-critical — should be skipped
    low_anomaly = _make_test_anomaly()
    low_anomaly["severity"] = "LOW"
    result3 = await file_github_issue(settings.github_repo, settings.github_token, low_anomaly)
    print(f"Severity gate: {'PASS (skipped LOW)' if not result3 else 'FAIL (filed LOW)'}")


if __name__ == "__main__":
    asyncio.run(main())

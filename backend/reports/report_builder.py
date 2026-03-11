"""Report builder — transforms anomaly dicts into structured bug reports.

Full implementation in Sprint 3.
"""

import time
from datetime import UTC, datetime


def generate_report_id() -> str:
    """Generate a report ID: MNL-{YYYYMMDD}-{seq}."""
    date_str = datetime.now(tz=UTC).strftime("%Y%m%d")
    seq = int(time.time()) % 10000
    return f"MNL-{date_str}-{seq:04d}"

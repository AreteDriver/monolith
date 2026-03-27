"""Scatter anomalies missing system_id across known populated systems.

For anomalies where the on-chain object doesn't self-report location,
assign a system_id from the reference_data using a deterministic hash
of the object_id. This ensures the map shows real anomaly data across
the universe rather than a single cluster.

Usage:
    python scripts/scatter_anomalies.py --db /data/monolith.db
"""

import hashlib
import logging
import sqlite3
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main():
    db_path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--db" else "data/monolith.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get systems with coordinates (from reference_data)
    systems = conn.execute(
        "SELECT data_id FROM reference_data "
        "WHERE data_type = 'solarsystems' AND data_json LIKE '%location%' "
        "ORDER BY data_id LIMIT 500"
    ).fetchall()
    system_ids = [r["data_id"] for r in systems]

    if not system_ids:
        logger.error("No solarsystems in reference_data — run World API poller first")
        return

    logger.info("Found %d systems with coordinates", len(system_ids))

    # Get anomalies missing system_id (only real ones, not demo seed)
    rows = conn.execute(
        "SELECT id, object_id, anomaly_type FROM anomalies "
        "WHERE (system_id IS NULL OR system_id = '') "
        "AND anomaly_type != 'ORPHAN_OBJECT' "
        "AND object_id != ''"
    ).fetchall()

    logger.info("Found %d anomalies missing system_id", len(rows))

    updated = 0
    for row in rows:
        # Deterministic system assignment from object_id hash
        h = hashlib.md5(row["object_id"].encode(), usedforsecurity=False).hexdigest()
        idx = int(h[:8], 16) % len(system_ids)
        system_id = system_ids[idx]

        conn.execute(
            "UPDATE anomalies SET system_id = ? WHERE id = ?",
            (system_id, row["id"]),
        )
        updated += 1

    conn.commit()
    conn.close()
    logger.info("Assigned system_id to %d anomalies across %d systems", updated, len(system_ids))


if __name__ == "__main__":
    main()

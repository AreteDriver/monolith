"""State snapshotter — compares consecutive world state snapshots and records deltas."""

import json
import logging
import sqlite3
import time

logger = logging.getLogger(__name__)


class StateSnapshotter:
    """Compares consecutive snapshots to detect state changes and write transitions."""

    def __init__(self, conn: sqlite3.Connection, recency_seconds: int = 3600):
        self.conn = conn
        self.recency_seconds = recency_seconds

    def get_latest_two_snapshots(self, object_id: str) -> tuple[dict | None, dict | None]:
        """Get the two most recent snapshots for an object."""
        rows = self.conn.execute(
            """SELECT state_data, snapshot_time FROM world_states
               WHERE object_id = ?
               ORDER BY snapshot_time DESC LIMIT 2""",
            (object_id,),
        ).fetchall()
        if len(rows) < 2:
            return (dict(rows[0]) if rows else None, None)
        return (dict(rows[0]), dict(rows[1]))

    def compute_delta(self, old_state: dict, new_state: dict) -> dict | None:
        """Compare two state snapshots and return delta if changed.

        Returns None if states are identical.
        """
        old_data = json.loads(old_state.get("state_data", "{}"))
        new_data = json.loads(new_state.get("state_data", "{}"))

        if old_data == new_data:
            return None

        changes: dict = {}
        all_keys = set(old_data.keys()) | set(new_data.keys())
        for key in all_keys:
            old_val = old_data.get(key)
            new_val = new_data.get(key)
            if old_val != new_val:
                changes[key] = {"old": old_val, "new": new_val}

        return changes if changes else None

    def record_transition(
        self,
        object_id: str,
        from_state: str,
        to_state: str,
        timestamp: int,
        event_id: str = "",
        transaction_hash: str = "",
        block_number: int = 0,
    ) -> None:
        """Record a state transition for an object."""
        self.conn.execute(
            """INSERT INTO state_transitions
               (object_id, from_state, to_state, event_id, transaction_hash,
                block_number, timestamp, is_valid)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (object_id, from_state, to_state, event_id, transaction_hash, block_number, timestamp),
        )

    def process_all_objects(self) -> int:
        """Compare latest snapshots for all tracked objects. Returns count of deltas found."""
        delta_count = 0
        now = int(time.time())
        batch_size = 100
        offset = 0

        while True:
            objects = self.conn.execute(
                """SELECT o.object_id FROM objects o
                   WHERE EXISTS (
                       SELECT 1 FROM world_states ws
                       WHERE ws.object_id = o.object_id
                       AND ws.snapshot_time >= (strftime('%s', 'now') - ?)
                   )
                   LIMIT ? OFFSET ?""",
                (self.recency_seconds, batch_size, offset),
            ).fetchall()
            if not objects:
                break
            offset += batch_size

            for row in objects:
                object_id = row["object_id"]
                newest, previous = self.get_latest_two_snapshots(object_id)

                if not newest or not previous:
                    continue

                delta = self.compute_delta(previous, newest)
                if delta:
                    self.record_transition(
                        object_id=object_id,
                        from_state=json.dumps(
                            json.loads(previous.get("state_data", "{}")), sort_keys=True
                        ),
                        to_state=json.dumps(
                            json.loads(newest.get("state_data", "{}")), sort_keys=True
                        ),
                        timestamp=now,
                    )
                    delta_count += 1

            if delta_count:
                self.conn.commit()

        if delta_count:
            logger.info("Snapshotter found %d state deltas", delta_count)
        return delta_count

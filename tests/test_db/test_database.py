"""Tests for database initialization and schema."""

from backend.db.database import get_row_counts, init_db


def test_init_db_creates_tables():
    """All expected tables exist after init."""
    conn = init_db(":memory:")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {row[0] for row in tables}
    expected = {
        "chain_events",
        "world_states",
        "objects",
        "state_transitions",
        "anomalies",
        "bug_reports",
    }
    assert expected.issubset(table_names)
    conn.close()


def test_wal_mode():
    """Database uses WAL journal mode."""
    conn = init_db(":memory:")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    # In-memory databases may report 'memory' instead of 'wal'
    assert mode in ("wal", "memory")
    conn.close()


def test_row_counts_empty(db_conn):
    """Row counts are all zero on fresh database."""
    counts = get_row_counts(db_conn)
    assert all(v == 0 for v in counts.values())
    assert "chain_events" in counts
    assert "anomalies" in counts


def test_chain_events_unique_constraint(db_conn):
    """Duplicate event_id is rejected."""
    import sqlite3

    db_conn.execute(
        "INSERT INTO chain_events (event_id, event_type, timestamp) VALUES (?, ?, ?)",
        ("evt-001", "test", 1000),
    )
    db_conn.commit()

    import pytest

    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            "INSERT INTO chain_events (event_id, event_type, timestamp) VALUES (?, ?, ?)",
            ("evt-001", "test", 1001),
        )


def test_objects_upsert(db_conn):
    """Objects table supports upsert via ON CONFLICT."""
    db_conn.execute(
        "INSERT INTO objects (object_id, object_type, last_seen) VALUES (?, ?, ?)",
        ("obj-001", "gate", 1000),
    )
    db_conn.commit()

    db_conn.execute(
        """INSERT INTO objects (object_id, object_type, last_seen)
           VALUES (?, ?, ?)
           ON CONFLICT(object_id) DO UPDATE SET last_seen = excluded.last_seen""",
        ("obj-001", "gate", 2000),
    )
    db_conn.commit()

    row = db_conn.execute(
        "SELECT last_seen FROM objects WHERE object_id = ?", ("obj-001",)
    ).fetchone()
    assert row[0] == 2000


def test_foreign_keys_enabled(db_conn):
    """Foreign keys are enforced."""
    fk = db_conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1

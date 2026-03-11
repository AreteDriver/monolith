"""Shared test fixtures for Monolith."""

import pytest

from backend.db.database import init_db


@pytest.fixture
def db_conn():
    """In-memory SQLite database with full schema."""
    conn = init_db(":memory:")
    yield conn
    conn.close()

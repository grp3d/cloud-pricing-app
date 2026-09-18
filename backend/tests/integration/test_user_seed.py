"""Integration test for migration `0004_user_accounts_sharing`'s seeded default Admin account
(012-user-accounts-sharing, spec FR-012, research.md §6).

Runs against the already-migrated test database's real current state (matching
`test_regions.py`'s "assert against real data" convention) rather than simulating the migration
in a rolled-back transaction, since — unlike 010's ephemeral collections backfill — this seed
row is meant to durably exist in every migrated database from here on.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text

from src.services.auth_service import verify_password

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost/cloud_pricing_test"
)


def test_default_admin_seeded_exactly_once_with_working_password():
    sync_engine = create_engine(TEST_DATABASE_URL)
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT username, password_hash, is_active, is_admin, is_default_admin "
                "FROM users WHERE username = 'Admin'"
            )
        ).fetchall()
    sync_engine.dispose()

    assert len(rows) == 1
    row = rows[0]
    assert row.is_active is True
    assert row.is_admin is True
    assert row.is_default_admin is True
    assert row.password_hash is not None
    assert verify_password("admin123", row.password_hash) is True

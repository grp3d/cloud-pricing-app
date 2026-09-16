"""Integration test for the 010-multi-region-support region-backfill migration (spec FR-016).

Exercises the exact add/backfill/constrain SQL sequence migration `0003_collection_region`
performs, directly against the test database's `collections` table, rather than orchestrating
a full Alembic upgrade/downgrade cycle on the shared test database (no existing precedent for
migration-level tests in this repo — see research.md §1). Everything runs inside one
connection that is rolled back at the end (never committed), so this test leaves the schema
and data exactly as it found them regardless of outcome.
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import create_engine, text

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost/cloud_pricing_test"
)

# The literal value migration 0003 backfills existing rows with — the app's former single
# global pricing region (spec FR-016, Clarifications).
_FORMER_GLOBAL_REGION = "us-east-1"


def test_backfill_sets_former_global_region_on_null_rows():
    sync_engine = create_engine(TEST_DATABASE_URL)
    with sync_engine.connect() as conn:
        try:
            # Simulate the pre-migration state: region nullable, existing row has NULL.
            conn.execute(text("ALTER TABLE collections ALTER COLUMN region DROP NOT NULL"))

            user_id = uuid.uuid4()
            conn.execute(text("INSERT INTO users (id) VALUES (:id)"), {"id": user_id})
            arch_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO architectures (id, user_id, provider, name) "
                    "VALUES (:id, :u, 'aws', 'Backfill Test')"
                ),
                {"id": arch_id, "u": user_id},
            )
            collection_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO collections (id, architecture_id, type, name, region) "
                    "VALUES (:id, :a, 'vpc', 'Legacy VPC', NULL)"
                ),
                {"id": collection_id, "a": arch_id},
            )

            # The migration's own backfill + constrain steps, verbatim.
            conn.execute(
                text("UPDATE collections SET region = :region WHERE region IS NULL"),
                {"region": _FORMER_GLOBAL_REGION},
            )
            conn.execute(text("ALTER TABLE collections ALTER COLUMN region SET NOT NULL"))

            region = conn.execute(
                text("SELECT region FROM collections WHERE id = :id"), {"id": collection_id}
            ).scalar()
            assert region == _FORMER_GLOBAL_REGION
        finally:
            conn.rollback()
    sync_engine.dispose()

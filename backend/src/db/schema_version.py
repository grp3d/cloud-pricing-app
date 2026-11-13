"""Refuse to start against a database whose migrations don't match the code (023).

Locally, migrations run only when a developer runs `alembic upgrade head`; in the cloud, `db-init`
runs them before the backend starts. A backend started against an older schema would otherwise
come up "healthy" and then fail on any query that touches a new table or column.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine

# backend/alembic.ini locally, /app/alembic.ini in the image: both sit beside src/.
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

# Reading the revisions logs several Alembic setup lines at info; they say nothing useful here.
logging.getLogger("alembic.runtime").setLevel(logging.WARNING)


class SchemaVersionMismatchError(RuntimeError):
    """The database isn't at the migration revision this code expects."""


def code_revision() -> str:
    """The newest migration revision in the code."""
    head = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()
    if head is None:  # pragma: no cover - the repo always has migrations
        raise SchemaVersionMismatchError("no database migrations found")
    return head


async def database_revision(engine: AsyncEngine) -> str | None:
    """The revision the database was last migrated to, or None if it never was."""
    async with engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: MigrationContext.configure(
                sync_conn
            ).get_current_revision()
        )


async def check_schema_version(engine: AsyncEngine) -> None:
    expected = code_revision()
    actual = await database_revision(engine)
    if actual != expected:
        raise SchemaVersionMismatchError(
            f"database is at migration {actual or 'none'}, the code expects {expected}: "
            "run `alembic upgrade head` in backend/"
        )

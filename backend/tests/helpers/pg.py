"""Scratch Postgres databases for the backup and restore tests (018-app-cloud-deployment).

Each test gets its own throwaway database on the test server (`TEST_DATABASE_URL`), so restores
never touch the shared test database. Tests that run `pg_dump`/`pg_restore` skip with a clear
reason when the client tools aren't on `PATH` (CI installs them, T088).
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import pytest
from sqlalchemy.engine import make_url

from src.ops.db import connect


def require_pg_tools() -> None:
    missing = [t for t in ("pg_dump", "pg_restore") if shutil.which(t) is None]
    if missing:
        pytest.skip(f"{', '.join(missing)} not on PATH (install postgresql-client-18)")


@contextmanager
def scratch_database(base_url: str) -> Iterator[str]:
    """Create an empty database next to `base_url`'s, yield its SQLAlchemy URL, drop it."""
    url = make_url(base_url)
    name = f"cp_scratch_{uuid.uuid4().hex[:12]}"
    admin_url = url.set(database="postgres").render_as_string(hide_password=False)
    with connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield url.set(database=name).render_as_string(hide_password=False)
    finally:
        with connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (name,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')


def execute(database_url: str, sql: str, params: tuple = ()) -> list[tuple]:
    with connect(database_url, autocommit=True) as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchall() if cursor.description else []


__all__ = ["execute", "psycopg", "require_pg_tools", "scratch_database"]

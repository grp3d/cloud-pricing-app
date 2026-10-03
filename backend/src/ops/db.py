"""Postgres helpers shared by the ops commands (018-app-cloud-deployment, research.md R8–R9).

The app's `DATABASE_URL` is a SQLAlchemy URL (`postgresql+psycopg://…`). The client tools
(`pg_dump`, `pg_restore`) get the same target as libpq parameters with the password passed in
`PGPASSWORD`, never on the command line or in logs (FR-041).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from src.models.orm import Base

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"


class OpsError(Exception):
    """A failed ops step, carrying the contract's exit code (contracts/ops-cli.md)."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def libpq(database_url: str) -> tuple[str, dict[str, str]]:
    """(connection URL without the password, environment with `PGPASSWORD` if there is one)."""
    url = make_url(database_url).set(drivername="postgresql")
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = str(url.password)
    return url.set(password=None).render_as_string(hide_password=False), env


def connect(database_url: str, **kwargs) -> psycopg.Connection:
    url, env = libpq(database_url)
    return psycopg.connect(url, password=env.get("PGPASSWORD"), **kwargs)


def user_tables() -> list[str]:
    """Every user-data table, from the ORM metadata (not a hard-coded list), in dependency
    order."""
    return [table.name for table in Base.metadata.sorted_tables]


def row_counts(conn: psycopg.Connection) -> dict[str, int]:
    counts = {}
    for table in user_tables():
        counts[table] = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
    return counts


def alembic_revision(conn: psycopg.Connection) -> str | None:
    exists = conn.execute("SELECT to_regclass('public.alembic_version')").fetchone()[0]
    if exists is None:
        return None
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0] if row else None


def _alembic_config(database_url: str) -> Config:
    # No ini file, so Alembic doesn't reconfigure the process's logging.
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["database_url"] = database_url
    return config


def known_revisions() -> set[str]:
    script = ScriptDirectory.from_config(_alembic_config("postgresql://unused"))
    return {rev.revision for rev in script.walk_revisions()}


def alembic_upgrade(database_url: str) -> None:
    from alembic import command

    command.upgrade(_alembic_config(database_url), "head")


def run_tool(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run a Postgres client tool, raising `OpsError(1)` with its stderr tail on failure."""
    try:
        result = subprocess.run(args, env=env, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise OpsError(1, f"{args[0]} is not installed") from exc
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-5:])
        raise OpsError(1, f"{args[0]} failed: {tail}")
    return result

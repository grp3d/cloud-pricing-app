"""Shared pytest fixtures: a real Postgres test database and an httpx client wired to the app.

Deliberately uses a real Postgres (not SQLite) — the constitution specifies Postgres, and the
ORM models use Postgres-specific check constraint expressions (e.g. boolean::int casts).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost/cloud_pricing_test"
)

# Point the app at the test database before importing it, so src.db.session's module-level
# engine is created against the right database.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# 018-app-cloud-deployment: the committed fixture is a pipeline storage root (new layout). CI sets
# PRICING_DATA_URI explicitly; locally it defaults to the fixture so no network is ever needed.
PRICING_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "pricing_parquet"
os.environ.setdefault("PRICING_DATA_URI", f"file://{PRICING_FIXTURE_ROOT}")

from src.db.session import get_session  # noqa: E402
from src.main import app  # noqa: E402
from src.models.orm import Architecture, Collection, DataConnector, SKUSelection, User  # noqa: E402

test_engine = create_async_engine(TEST_DATABASE_URL)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _clean_db():
    """Truncate all app tables before each test for isolation.

    The seeded default Admin account (012-user-accounts-sharing, migration
    `0004_user_accounts_sharing`) is deliberately excluded from the `users` truncation — it's
    meant to durably survive forever in a real database (the app itself refuses to deactivate
    or purge it, `is_default_admin`), so preserving it here across tests mirrors that same
    invariant rather than working around it.
    """
    async with test_engine.begin() as conn:
        for table in (SKUSelection, DataConnector, Collection, Architecture):
            await conn.execute(table.__table__.delete())
        await conn.execute(User.__table__.delete().where(User.is_default_admin.is_(False)))
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    async def _override_get_session():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """A fresh, valid bearer token — a new distinct user identity per test (FR-002)."""
    return {"Authorization": f"Bearer {uuid.uuid4()}"}


@pytest_asyncio.fixture
async def admin_headers() -> dict[str, str]:
    """Bearer headers for the seeded default Admin account (012-user-accounts-sharing)."""
    async with TestSessionLocal() as session:
        from sqlalchemy import select

        admin_id = (
            await session.execute(select(User.id).where(User.is_default_admin.is_(True)))
        ).scalar_one()
    return {"Authorization": f"Bearer {admin_id}"}


@pytest.fixture
def log_output():
    """Captures the rendered JSON log records as a list of dicts (017-structured-json-logging,
    FR-012). Call the returned function to read everything logged so far."""
    import io
    import json

    import structlog

    from src.config import settings
    from src.logging_config import configure_logging

    buf = io.StringIO()
    configure_logging(level="DEBUG", fmt="json", stream=buf)
    structlog.contextvars.clear_contextvars()
    yield lambda: [json.loads(line) for line in buf.getvalue().splitlines()]
    structlog.contextvars.clear_contextvars()
    configure_logging(settings.log_level, settings.log_format)


@pytest.fixture
def use_pricing_root(monkeypatch):
    """Point the app at another pipeline storage root for one test (018-app-cloud-deployment):
    call the returned function with the root. The monitor is reset afterwards, so later tests
    re-select from the default fixture."""
    from src.config import settings
    from src.pricing_data import active_snapshot

    def use(root: Path) -> None:
        monkeypatch.setattr(settings, "pricing_data_uri", f"file://{root}")
        active_snapshot.reset()
        active_snapshot.run_check(at_startup=True)

    yield use
    active_snapshot.reset()

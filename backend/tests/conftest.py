"""Shared pytest fixtures: a real Postgres test database and an httpx client wired to the app.

Deliberately uses a real Postgres (not SQLite) — the constitution specifies Postgres, and the
ORM models use Postgres-specific check constraint expressions (e.g. boolean::int casts).
"""

from __future__ import annotations

import os
import uuid

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

from src.db.session import get_session  # noqa: E402
from src.main import app  # noqa: E402
from src.models.orm import Architecture, Collection, DataConnector, SKUSelection, User  # noqa: E402

test_engine = create_async_engine(TEST_DATABASE_URL)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _clean_db():
    """Truncate all app tables before each test for isolation."""
    async with test_engine.begin() as conn:
        for table in (SKUSelection, DataConnector, Collection, Architecture, User):
            await conn.execute(table.__table__.delete())
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

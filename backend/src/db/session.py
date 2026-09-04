"""Async PostgreSQL engine/session setup.

This is the ONLY place a SQLAlchemy engine is created. Per the constitution's data-layer
separation principle, this session is used exclusively for user-defined objects (User,
Architecture, Collection, SKU Selection, Data Connector) — never for AWS pricing data, which
lives in Parquet and is read only via `src/pricing_data/`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped AsyncSession."""
    async with async_session_factory() as session:
        yield session

"""Shared lookups and lifecycle operations for Architectures/Collections/Data Connectors.

Centralized here so every router enforces the same ownership scoping (FR-002) and the same
soft-delete/cascade rules (FR-014, FR-015) rather than each re-implementing them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.orm import Architecture, Collection, DataConnector, User


async def get_owned_architecture(
    architecture_id: uuid.UUID, session: AsyncSession, user: User
) -> Architecture:
    """Fetch a non-deleted Architecture the given user owns, with Collections/Connectors."""
    stmt = (
        select(Architecture)
        .where(
            Architecture.id == architecture_id,
            Architecture.user_id == user.id,
            Architecture.deleted_at.is_(None),
        )
        .options(
            selectinload(
                Architecture.collections.and_(Collection.deleted_at.is_(None))
            ).selectinload(Collection.sku_selections),
            selectinload(
                Architecture.connectors.and_(DataConnector.deleted_at.is_(None))
            ).selectinload(DataConnector.sku_selection),
        )
    )
    result = await session.execute(stmt)
    architecture = result.scalar_one_or_none()
    if architecture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Architecture not found")
    return architecture


async def get_owned_collection(
    collection_id: uuid.UUID, session: AsyncSession, user: User
) -> Collection:
    """Fetch a non-deleted Collection whose parent Architecture the given user owns."""
    stmt = (
        select(Collection)
        .join(Architecture, Collection.architecture_id == Architecture.id)
        .where(
            Collection.id == collection_id,
            Architecture.user_id == user.id,
            Collection.deleted_at.is_(None),
        )
    )
    result = await session.execute(stmt)
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection


async def get_owned_connector(
    connector_id: uuid.UUID, session: AsyncSession, user: User
) -> DataConnector:
    """Fetch a non-deleted Data Connector whose parent Architecture the given user owns."""
    stmt = (
        select(DataConnector)
        .join(Architecture, DataConnector.architecture_id == Architecture.id)
        .where(
            DataConnector.id == connector_id,
            Architecture.user_id == user.id,
            DataConnector.deleted_at.is_(None),
        )
        .options(selectinload(DataConnector.sku_selection))
    )
    result = await session.execute(stmt)
    connector = result.scalar_one_or_none()
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    return connector


async def soft_delete_collection(collection: Collection, session: AsyncSession) -> None:
    """Soft-delete a Collection and cascade to any Data Connector referencing it (FR-015)."""
    now = datetime.now(UTC)
    collection.deleted_at = now

    stmt = select(DataConnector).where(
        DataConnector.deleted_at.is_(None),
        (DataConnector.from_collection_id == collection.id)
        | (DataConnector.to_collection_id == collection.id),
    )
    result = await session.execute(stmt)
    for connector in result.scalars().all():
        connector.deleted_at = now

    await session.commit()

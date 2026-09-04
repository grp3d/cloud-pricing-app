"""Collection endpoints (spec FR-004, FR-015)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from src.api.deps import CurrentUser, DbSession
from src.models.orm import Collection
from src.models.schemas import CollectionCreate, CollectionOut
from src.services.architecture_service import (
    get_owned_architecture,
    get_owned_collection,
    soft_delete_collection,
)

router = APIRouter(tags=["collections"])


@router.post(
    "/architectures/{architecture_id}/collections", response_model=CollectionOut, status_code=201
)
async def create_collection(
    architecture_id: uuid.UUID, body: CollectionCreate, session: DbSession, user: CurrentUser
) -> Collection:
    architecture = await get_owned_architecture(architecture_id, session, user)
    collection = Collection(
        architecture_id=architecture.id, type=body.type.value, name=body.name
    )
    session.add(collection)
    await session.commit()
    await session.refresh(collection, attribute_names=["sku_selections"])
    return collection


@router.delete("/collections/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> None:
    """Soft delete, cascading to any Data Connector attached to this Collection (FR-015)."""
    collection = await get_owned_collection(collection_id, session, user)
    await soft_delete_collection(collection, session)

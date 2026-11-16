"""Collection endpoints (spec FR-004, FR-015; 010-multi-region-support FR-001-FR-003)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from src.api.deps import CurrentUser, DbSession
from src.models.orm import Collection
from src.models.schemas import CollectionCreate, CollectionOut, CollectionUpdate
from src.services import architecture_rules as rules
from src.services.architecture_service import (
    get_owned_architecture,
    get_owned_collection,
    set_collection_parent,
    set_collection_region,
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

    parent: Collection | None = None
    if body.parent_collection_id is not None:
        # 010-multi-region-support, spec FR-001a: creating an Application already nested in a
        # selected VPC skips the region prompt entirely — the parent's region is authoritative,
        # any client-supplied `region` is ignored so a stale/bypassed client can never create a
        # mismatched nesting.
        if body.type.value != "application_component":
            rules.check_nesting(body.type.value, "", None, creating=True)
        stmt = select(Collection).where(
            Collection.id == body.parent_collection_id,
            Collection.architecture_id == architecture.id,
            Collection.type == "vpc",
            Collection.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        parent = result.scalar_one_or_none()
        rules.check_nesting(
            body.type.value, "",
            None if parent is None else rules.CollectionFacts(type=parent.type,
                                                              region=parent.region),
            creating=True,
        )
        region = parent.region
    else:
        rules.check_region_given(body.region)
        rules.check_region_available(architecture.provider, body.region)
        region = body.region

    collection = Collection(
        architecture_id=architecture.id,
        type=body.type.value,
        name=body.name,
        region=region,
        parent_collection_id=parent.id if parent is not None else None,
    )
    session.add(collection)
    await session.commit()
    await session.refresh(collection, attribute_names=["sku_selections"])
    return collection


@router.patch("/collections/{collection_id}", response_model=CollectionOut)
async def update_collection(
    collection_id: uuid.UUID, body: CollectionUpdate, session: DbSession, user: CurrentUser
) -> Collection:
    """Nest/move/un-nest an Application Component (002-vpc-component-nesting, FR-001-FR-004)
    and/or change a collection's region while unlocked (010-multi-region-support, FR-003).
    Only the fields actually present in the request body are applied."""
    collection = await get_owned_collection(collection_id, session, user)
    fields = body.model_fields_set
    if "region" in fields:
        collection = await set_collection_region(collection, body.region, session)
    if "parent_collection_id" in fields:
        collection = await set_collection_parent(collection, body.parent_collection_id, session)
    await session.refresh(collection, attribute_names=["sku_selections"])
    return collection


@router.delete("/collections/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> None:
    """Soft delete, cascading to any Data Connector attached to this Collection (FR-015)."""
    collection = await get_owned_collection(collection_id, session, user)
    await soft_delete_collection(collection, session)

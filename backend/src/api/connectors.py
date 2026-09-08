"""Data Connector endpoints (spec FR-008, FR-009, FR-015)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from src.api.deps import CurrentUser, DbSession
from src.models.orm import DataConnector, SKUSelection
from src.models.schemas import (
    DataConnectorCreate,
    DataConnectorOut,
    SKUSelectionCreate,
    SKUSelectionOut,
)
from src.services.architecture_service import (
    get_owned_architecture,
    get_owned_connector,
    sku_selection_out_with_unit,
)

router = APIRouter(tags=["connectors"])


@router.post(
    "/architectures/{architecture_id}/connectors",
    response_model=DataConnectorOut,
    status_code=201,
)
async def create_connector(
    architecture_id: uuid.UUID,
    body: DataConnectorCreate,
    session: DbSession,
    user: CurrentUser,
) -> DataConnector:
    if body.from_collection_id == body.to_collection_id:
        raise HTTPException(
            status_code=400, detail="A connector cannot link a Collection to itself"
        )

    architecture = await get_owned_architecture(architecture_id, session, user)
    collection_ids = {c.id for c in architecture.collections if c.deleted_at is None}
    if body.from_collection_id not in collection_ids or body.to_collection_id not in collection_ids:
        raise HTTPException(
            status_code=400,
            detail="Both collections must belong to this Architecture",
        )

    connector = DataConnector(
        architecture_id=architecture.id,
        from_collection_id=body.from_collection_id,
        to_collection_id=body.to_collection_id,
    )
    session.add(connector)
    await session.commit()
    await session.refresh(connector, attribute_names=["sku_selection"])
    return connector


@router.post(
    "/connectors/{connector_id}/sku-selection",
    response_model=SKUSelectionOut,
    status_code=201,
)
async def attach_connector_sku(
    connector_id: uuid.UUID, body: SKUSelectionCreate, session: DbSession, user: CurrentUser
) -> SKUSelectionOut:
    """Attach (or replace) the single AWS SKU on a Data Connector (FR-009)."""
    connector = await get_owned_connector(connector_id, session, user)

    existing = (
        await session.get(SKUSelection, connector.sku_selection.id)
        if connector.sku_selection
        else None
    )
    if existing is not None:
        await session.delete(existing)
        await session.flush()

    selection = SKUSelection(
        connector_id=connector.id,
        service_code=body.service_code,
        sku=body.sku,
        pricing_term=body.pricing_term.value,
        purchase_option=body.purchase_option.value,
        usage_quantity=body.usage_quantity,
    )
    session.add(selection)
    await session.commit()
    await session.refresh(selection)
    return sku_selection_out_with_unit(selection)


@router.delete("/connectors/{connector_id}", status_code=204)
async def delete_connector(connector_id: uuid.UUID, session: DbSession, user: CurrentUser) -> None:
    """Soft delete (FR-015)."""
    connector = await get_owned_connector(connector_id, session, user)
    connector.deleted_at = datetime.now(UTC)
    await session.commit()

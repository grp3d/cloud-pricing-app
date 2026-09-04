"""SKU Selection endpoints, attached to a Collection (spec FR-006, FR-007)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser, DbSession
from src.models.orm import SKUSelection
from src.models.schemas import SKUSelectionCreate, SKUSelectionOut, SKUSelectionUpdate
from src.services.architecture_service import get_owned_collection, get_owned_connector

router = APIRouter(tags=["sku-selections"])


@router.post(
    "/collections/{collection_id}/sku-selections",
    response_model=SKUSelectionOut,
    status_code=201,
)
async def add_sku_selection(
    collection_id: uuid.UUID, body: SKUSelectionCreate, session: DbSession, user: CurrentUser
) -> SKUSelection:
    collection = await get_owned_collection(collection_id, session, user)
    # Duplicates are explicitly allowed (spec Edge Cases) — the same SKU may appear more than
    # once, each with independent pricing inputs.
    selection = SKUSelection(
        collection_id=collection.id,
        service_code=body.service_code,
        sku=body.sku,
        pricing_term=body.pricing_term.value,
        purchase_option=body.purchase_option.value,
        usage_quantity=body.usage_quantity,
    )
    session.add(selection)
    await session.commit()
    await session.refresh(selection)
    return selection


async def _get_owned_sku_selection(
    sku_selection_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> SKUSelection:
    # A SKU Selection is owned transitively via its Collection's or Connector's Architecture —
    # fetch it, then verify ownership through whichever of the two parent paths is set.
    selection = await session.get(SKUSelection, sku_selection_id)
    if selection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU Selection not found")
    if selection.collection_id is not None:
        await get_owned_collection(selection.collection_id, session, user)
    else:
        await get_owned_connector(selection.connector_id, session, user)
    return selection


@router.patch("/sku-selections/{sku_selection_id}", response_model=SKUSelectionOut)
async def update_sku_selection(
    sku_selection_id: uuid.UUID, body: SKUSelectionUpdate, session: DbSession, user: CurrentUser
) -> SKUSelection:
    selection = await _get_owned_sku_selection(sku_selection_id, session, user)
    if body.pricing_term is not None:
        selection.pricing_term = body.pricing_term.value
    if body.purchase_option is not None:
        selection.purchase_option = body.purchase_option.value
    if body.usage_quantity is not None:
        selection.usage_quantity = body.usage_quantity
    await session.commit()
    await session.refresh(selection)
    return selection


@router.delete("/sku-selections/{sku_selection_id}", status_code=204)
async def delete_sku_selection(
    sku_selection_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> None:
    selection = await _get_owned_sku_selection(sku_selection_id, session, user)
    await session.delete(selection)
    await session.commit()

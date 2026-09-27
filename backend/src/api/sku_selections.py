"""SKU Selection endpoints, attached to a Collection (spec FR-006, FR-007)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from src.api.deps import CurrentUser, DbSession
from src.models.orm import SKUSelection
from src.models.schemas import SKUSelectionCreate, SKUSelectionOut, SKUSelectionUpdate
from src.services.architecture_service import (
    get_owned_collection,
    get_owned_connector,
    sku_selection_out_with_unit,
)

router = APIRouter(tags=["sku-selections"])


@router.post(
    "/collections/{collection_id}/sku-selections",
    response_model=SKUSelectionOut,
    status_code=201,
)
async def add_sku_selection(
    collection_id: uuid.UUID, body: SKUSelectionCreate, session: DbSession, user: CurrentUser
) -> SKUSelectionOut:
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
    return sku_selection_out_with_unit(selection, region=collection.region)


async def _get_owned_sku_selection(
    sku_selection_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> tuple[SKUSelection, str]:
    # A SKU Selection is owned transitively via its Collection's or Connector's Architecture —
    # fetch it, then verify ownership through whichever of the two parent paths is set, keeping
    # the owning Collection's (or Connector's "from" Collection's) region for pricing/catalog
    # lookups (010-multi-region-support).
    selection = await session.get(SKUSelection, sku_selection_id)
    if selection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU Selection not found")
    if selection.collection_id is not None:
        collection = await get_owned_collection(selection.collection_id, session, user)
        region = collection.region
    else:
        connector = await get_owned_connector(selection.connector_id, session, user)
        region = connector.from_collection.region
    return selection, region


async def _move_to_collection(
    selection: SKUSelection,
    target_id: uuid.UUID,
    source_region: str,
    session: DbSession,
    user: CurrentUser,
) -> JSONResponse | None:
    """016-canvas-icon-layout, FR-004a/FR-004b: move a box's service into another box of the same
    Architecture and region (dragging its icon on the canvas). Returns an error response when
    the move isn't allowed; otherwise re-points the selection and returns None. Prices are
    unaffected — same SKU, same region, same inputs."""
    if selection.collection_id is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "not_movable",
                "message": "Services attached to a connector can't be moved to a box.",
            },
        )
    source = await get_owned_collection(selection.collection_id, session, user)
    target = await get_owned_collection(target_id, session, user)
    if target.architecture_id != source.architecture_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    if target.region != source_region:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "region_mismatch",
                "message": (
                    f'"{selection.service_code}" is in {source_region} and can only move to a '
                    "box in the same region."
                ),
            },
        )
    selection.collection_id = target.id
    return None


@router.patch(
    "/sku-selections/{sku_selection_id}",
    response_model=SKUSelectionOut,
    responses={400: {"description": "not_movable"}, 409: {"description": "region_mismatch"}},
)
async def update_sku_selection(
    sku_selection_id: uuid.UUID, body: SKUSelectionUpdate, session: DbSession, user: CurrentUser
) -> SKUSelectionOut | JSONResponse:
    selection, region = await _get_owned_sku_selection(sku_selection_id, session, user)
    if body.collection_id is not None and body.collection_id != selection.collection_id:
        refused = await _move_to_collection(selection, body.collection_id, region, session, user)
        if refused is not None:
            return refused
    if body.pricing_term is not None:
        selection.pricing_term = body.pricing_term.value
    if body.purchase_option is not None:
        selection.purchase_option = body.purchase_option.value
    if body.usage_quantity is not None:
        selection.usage_quantity = body.usage_quantity
    await session.commit()
    await session.refresh(selection)
    return sku_selection_out_with_unit(selection, region=region)


@router.delete("/sku-selections/{sku_selection_id}", status_code=204)
async def delete_sku_selection(
    sku_selection_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> None:
    selection, _region = await _get_owned_sku_selection(sku_selection_id, session, user)
    await session.delete(selection)
    await session.commit()

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

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection, User
from src.models.schemas import ArchitectureDetailOut, SKUSelectionOut
from src.pricing_data.catalog import resolve_attributes
from src.pricing_data.pricing import resolve_units
from src.pricing_data.regions import list_available_regions


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
        .options(
            selectinload(DataConnector.sku_selection),
            selectinload(DataConnector.from_collection),
        )
    )
    result = await session.execute(stmt)
    connector = result.scalar_one_or_none()
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    return connector


async def soft_delete_collection(collection: Collection, session: AsyncSession) -> None:
    """Soft-delete a Collection: cascade to any Data Connector referencing it (FR-015), and if
    it's a VPC, un-nest — never delete — any Application Components nested inside it
    (002-vpc-component-nesting, FR-007: nothing nested inside a VPC is ever lost by deleting
    the VPC)."""
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

    children_stmt = select(Collection).where(
        Collection.parent_collection_id == collection.id, Collection.deleted_at.is_(None)
    )
    children_result = await session.execute(children_stmt)
    for child in children_result.scalars().all():
        child.parent_collection_id = None

    await session.commit()


async def set_collection_parent(
    collection: Collection, parent_collection_id: uuid.UUID | None, session: AsyncSession
) -> Collection:
    """Nest, move, or un-nest an Application Component (002-vpc-component-nesting, FR-001-004).

    `collection` must already be resolved via `get_owned_collection` so ownership is
    established before this runs. The DB-level check constraints
    (`ck_collection_parent_only_app_component`, `ck_collection_no_self_parent`) are the
    single-row safety net; the cross-row rule below — the parent must actually be a VPC in the
    same Architecture — cannot be expressed as a `CHECK` constraint, so it's enforced here,
    mirroring how a Data Connector's two Collections are validated to share an Architecture.
    """
    if parent_collection_id is None:
        collection.parent_collection_id = None
        await session.commit()
        await session.refresh(collection)
        return collection

    if collection.type != "application_component":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only an Application Component can be nested inside a VPC",
        )

    stmt = select(Collection).where(
        Collection.id == parent_collection_id,
        Collection.architecture_id == collection.architecture_id,
        Collection.type == "vpc",
        Collection.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    parent = result.scalar_one_or_none()
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "parent_collection_id must reference an existing, non-deleted VPC Collection "
                "in the same Architecture"
            ),
        )

    # 010-multi-region-support, spec FR-004: an Application can only nest inside a same-region
    # VPC — enforced here as the authoritative server-side gate (a client-side check also
    # exists, research.md §8), so a bypassed/stale client can never create a mismatched nest.
    if collection.region != parent.region:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "region_mismatch",
                "application_region": collection.region,
                "vpc_region": parent.region,
            },
        )

    collection.parent_collection_id = parent.id
    await session.commit()
    await session.refresh(collection)
    return collection


async def is_collection_locked(collection: Collection, session: AsyncSession) -> bool:
    """010-multi-region-support, spec FR-003: a collection's region locks once it has at least
    one service attached, or, for a VPC, at least one nested Application."""
    has_sku = await session.scalar(
        select(SKUSelection.id).where(SKUSelection.collection_id == collection.id).limit(1)
    )
    if has_sku is not None:
        return True
    if collection.type == "vpc":
        has_child = await session.scalar(
            select(Collection.id)
            .where(
                Collection.parent_collection_id == collection.id,
                Collection.deleted_at.is_(None),
            )
            .limit(1)
        )
        if has_child is not None:
            return True
    return False


async def set_collection_region(
    collection: Collection, region: str | None, session: AsyncSession
) -> Collection:
    """Change a collection's region while it's still unlocked (010-multi-region-support, spec
    FR-003). `collection` must already be resolved via `get_owned_collection`."""
    if not region:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="region is required")
    if await is_collection_locked(collection, session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This collection's region is locked because it already has content",
        )
    if region not in list_available_regions():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"region '{region}' is not currently available",
        )
    collection.region = region
    await session.commit()
    await session.refresh(collection)
    return collection


def _unit_key(selection: SKUSelection) -> tuple[str, str, str]:
    return (selection.sku, selection.pricing_term, selection.purchase_option)


def sku_selection_out_with_unit(selection: SKUSelection, *, region: str) -> SKUSelectionOut:
    """Build a `SKUSelectionOut` for one SKU Selection with `unit` and `attributes` resolved and
    attached (003-service-selection-improvements FR-004/FR-005;
    004-canvas-pricing-improvements FR-014). Used by the single-object endpoints (add/update a
    SKU Selection, attach one to a Data Connector) — for a whole Architecture's nested tree,
    batch through `attach_units_to_architecture` instead so many selections cost one DuckDB
    query each, not N. `region` (010-multi-region-support) is the owning Collection's region,
    or, for a Connector-owned selection, the Connector's "from" Collection's region — the
    caller resolves it, since it already has the owning Collection/Connector in scope.
    """
    out = SKUSelectionOut.model_validate(selection)
    key = _unit_key(selection)
    out.unit = resolve_units([key], region=region).get(key)
    out.attributes = resolve_attributes(
        [(selection.service_code, selection.sku)], region=region
    ).get((selection.service_code, selection.sku), {})
    return out


def _region_grouped_batch_resolve(
    selections: list[SKUSelection], selection_regions: dict[uuid.UUID, str | None]
) -> tuple[dict, dict]:
    """Groups `selections` by their resolved region and calls `resolve_units`/
    `resolve_attributes` once per distinct region, merging the results (010-multi-region-
    support, research.md §11) — safe to merge since AWS SKU codes are themselves region-scoped,
    so a SKU from one region's partition never collides with another's. Selections with no
    resolved region (the defensive fallback, data-model.md) are skipped — `unit`/`attributes`
    stay unresolved (`None`/`{}`) for them, same as any other unmatched key.
    """
    by_region: dict[str, list[SKUSelection]] = {}
    for selection in selections:
        region = selection_regions.get(selection.id)
        if region is None:
            continue
        by_region.setdefault(region, []).append(selection)

    units: dict = {}
    attributes: dict = {}
    for region, region_selections in by_region.items():
        units.update(
            resolve_units([_unit_key(s) for s in region_selections], region=region)
        )
        attributes.update(
            resolve_attributes(
                [(s.service_code, s.sku) for s in region_selections], region=region
            )
        )
    return units, attributes


def attach_units_to_architecture(detail: ArchitectureDetailOut, architecture: Architecture) -> None:
    """Batch-resolve and attach `unit` and `attributes` to every SKU Selection nested in an
    Architecture's response tree — one DuckDB query per field per distinct region present, not
    one per SKU Selection (003-service-selection-improvements FR-004/FR-005, research.md #3;
    004-canvas-pricing-improvements FR-014, research.md #5; 010-multi-region-support §11).

    `detail` must have been built from `architecture` via `model_validate` so the two trees
    line up positionally; mutates `detail` in place.
    """
    collection_regions = {
        c.id: c.region for c in architecture.collections if c.deleted_at is None
    }
    selection_regions: dict[uuid.UUID, str | None] = {}
    for collection in architecture.collections:
        for selection in collection.sku_selections:
            selection_regions[selection.id] = collection_regions.get(collection.id)
    for connector in architecture.connectors:
        if connector.sku_selection is not None:
            selection_regions[connector.sku_selection.id] = collection_regions.get(
                connector.from_collection_id
            )

    orm_selections: list[SKUSelection] = [
        selection
        for collection in architecture.collections
        for selection in collection.sku_selections
    ] + [
        connector.sku_selection
        for connector in architecture.connectors
        if connector.sku_selection is not None
    ]
    if not orm_selections:
        return
    units, attributes = _region_grouped_batch_resolve(orm_selections, selection_regions)

    def _attach(selection_out: SKUSelectionOut, selection: SKUSelection) -> None:
        selection_out.unit = units.get(_unit_key(selection))
        selection_out.attributes = attributes.get((selection.service_code, selection.sku), {})

    for collection_out, collection in zip(
        detail.collections, architecture.collections, strict=True
    ):
        for selection_out, selection in zip(
            collection_out.sku_selections, collection.sku_selections, strict=True
        ):
            _attach(selection_out, selection)

    for connector_out, connector in zip(detail.connectors, architecture.connectors, strict=True):
        if connector_out.sku_selection is not None and connector.sku_selection is not None:
            _attach(connector_out.sku_selection, connector.sku_selection)

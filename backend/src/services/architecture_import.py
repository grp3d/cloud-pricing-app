"""Deep-copy import of a public Architecture (012-user-accounts-sharing, spec FR-029,
data-model.md).

Produces a fully independent copy: every `Collection`, `DataConnector`, and `SKUSelection` is
cloned with a fresh id, and every cross-reference (`parent_collection_id`,
`from_collection_id`/`to_collection_id`) is remapped to point at the *new* rows — the copy has
no reference back to the source, so later edits/deletes/purges of the source never affect it
(spec Edge Cases).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import Architecture, SKUSelection, User
from src.services.architecture_transfer import (
    CollectionSpec,
    ConnectorSpec,
    SKUSelectionSpec,
    build_architecture,
)


def _selection_spec(selection: SKUSelection) -> SKUSelectionSpec:
    return SKUSelectionSpec(
        service_code=selection.service_code,
        sku=selection.sku,
        pricing_term=selection.pricing_term,
        purchase_option=selection.purchase_option,
        usage_quantity=selection.usage_quantity,
    )


async def import_architecture(
    session: AsyncSession, source: Architecture, new_owner: User, new_name: str
) -> Architecture:
    # Row creation and reference remapping live in `architecture_transfer.build_architecture`
    # (014-architecture-templates-import-export, research.md §10), shared with the Admin file
    # import. The source's own row ids serve as the refs. `source.collections` is already
    # ordered by `created_at` (orm.py) — a child's parent is always a VPC created earlier, so
    # the builder's single parent-first pass holds.
    collections = [
        CollectionSpec(
            ref=str(collection.id),
            type=collection.type,
            name=collection.name,
            region=collection.region,
            parent_ref=(
                str(collection.parent_collection_id)
                if collection.parent_collection_id is not None
                else None
            ),
            sku_selections=tuple(_selection_spec(s) for s in collection.sku_selections),
        )
        for collection in source.collections
    ]
    connectors = [
        ConnectorSpec(
            from_ref=str(connector.from_collection_id),
            to_ref=str(connector.to_collection_id),
            sku_selection=(
                _selection_spec(connector.sku_selection)
                if connector.sku_selection is not None
                else None
            ),
        )
        for connector in source.connectors
    ]
    new_architecture = build_architecture(
        session,
        owner=new_owner,
        name=new_name,
        provider=source.provider,
        collections=collections,
        connectors=connectors,
    )
    await session.commit()
    await session.refresh(new_architecture)
    return new_architecture

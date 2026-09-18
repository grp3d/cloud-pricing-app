"""Deep-copy import of a public Architecture (012-user-accounts-sharing, spec FR-029,
data-model.md).

Produces a fully independent copy: every `Collection`, `DataConnector`, and `SKUSelection` is
cloned with a fresh id, and every cross-reference (`parent_collection_id`,
`from_collection_id`/`to_collection_id`) is remapped to point at the *new* rows — the copy has
no reference back to the source, so later edits/deletes/purges of the source never affect it
(spec Edge Cases).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection, User


async def import_architecture(
    session: AsyncSession, source: Architecture, new_owner: User, new_name: str
) -> Architecture:
    new_architecture = Architecture(
        id=uuid.uuid4(), user_id=new_owner.id, name=new_name, provider=source.provider,
        is_public=False,
    )
    session.add(new_architecture)

    # Every clone gets its id assigned explicitly (not left to the ORM's flush-time default,
    # `orm.py`'s `_uuid_pk()`) so `parent_collection_id`/`from_collection_id`/
    # `to_collection_id` can be remapped to the *new* rows before anything is flushed.
    # `source.collections` is already ordered by `created_at` (orm.py) — a child's
    # `parent_collection_id` always refers to a VPC created earlier, so a single left-to-right
    # pass is enough for every parent to already be in `collection_id_map` by the time its
    # children are cloned.
    collection_id_map: dict[uuid.UUID, uuid.UUID] = {}
    for collection in source.collections:
        new_collection_id = uuid.uuid4()
        new_collection = Collection(
            id=new_collection_id,
            architecture=new_architecture,
            type=collection.type,
            name=collection.name,
            region=collection.region,
            parent_collection_id=collection_id_map.get(collection.parent_collection_id),
        )
        session.add(new_collection)
        collection_id_map[collection.id] = new_collection_id

        for sku in collection.sku_selections:
            session.add(
                SKUSelection(
                    id=uuid.uuid4(),
                    collection_id=new_collection_id,
                    service_code=sku.service_code,
                    sku=sku.sku,
                    pricing_term=sku.pricing_term,
                    purchase_option=sku.purchase_option,
                    usage_quantity=sku.usage_quantity,
                )
            )

    for connector in source.connectors:
        new_connector_id = uuid.uuid4()
        session.add(
            DataConnector(
                id=new_connector_id,
                architecture=new_architecture,
                from_collection_id=collection_id_map[connector.from_collection_id],
                to_collection_id=collection_id_map[connector.to_collection_id],
            )
        )
        if connector.sku_selection is not None:
            session.add(
                SKUSelection(
                    id=uuid.uuid4(),
                    connector_id=new_connector_id,
                    service_code=connector.sku_selection.service_code,
                    sku=connector.sku_selection.sku,
                    pricing_term=connector.sku_selection.pricing_term,
                    purchase_option=connector.sku_selection.purchase_option,
                    usage_quantity=connector.sku_selection.usage_quantity,
                )
            )

    await session.commit()
    await session.refresh(new_architecture)
    return new_architecture

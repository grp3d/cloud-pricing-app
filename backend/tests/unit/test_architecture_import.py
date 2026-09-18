"""Unit test for `import_architecture`'s deep-copy/id-remap correctness
(012-user-accounts-sharing, spec FR-029, data-model.md).

Runs against the real test database (no mocking, per this repo's existing convention) — builds
a small nested VPC/Application + Connector graph, imports it, and asserts the copy is a fully
independent clone with every cross-reference remapped to the new rows.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection, User
from src.services.architecture_import import import_architecture


@pytest.mark.asyncio
async def test_import_clones_nested_collections_connectors_and_selections(db_session):
    owner = User(id=uuid.uuid4())
    importer = User(id=uuid.uuid4())
    db_session.add_all([owner, importer])
    await db_session.flush()

    source = Architecture(id=uuid.uuid4(), user_id=owner.id, provider="aws", name="Source")
    db_session.add(source)
    await db_session.flush()

    vpc = Collection(
        id=uuid.uuid4(), architecture_id=source.id, type="vpc", name="VPC", region="us-east-1"
    )
    db_session.add(vpc)
    await db_session.flush()

    app = Collection(
        id=uuid.uuid4(),
        architecture_id=source.id,
        type="application_component",
        name="App",
        region="us-east-1",
        parent_collection_id=vpc.id,
    )
    db_session.add(app)
    await db_session.flush()

    sku = SKUSelection(
        id=uuid.uuid4(),
        collection_id=app.id,
        service_code="AmazonEC2",
        sku="SKU1",
        pricing_term="on_demand",
        purchase_option="not_applicable",
        usage_quantity=Decimal("1"),
    )
    db_session.add(sku)

    connector = DataConnector(
        id=uuid.uuid4(), architecture_id=source.id, from_collection_id=vpc.id,
        to_collection_id=app.id,
    )
    db_session.add(connector)
    await db_session.flush()

    connector_sku = SKUSelection(
        id=uuid.uuid4(),
        connector_id=connector.id,
        service_code="AWSDataTransfer",
        sku="SKU2",
        pricing_term="on_demand",
        purchase_option="not_applicable",
        usage_quantity=Decimal("2"),
    )
    db_session.add(connector_sku)
    await db_session.commit()

    # Reload with the relationships `import_architecture` walks eagerly populated.
    reloaded = (
        await db_session.execute(select(Architecture).where(Architecture.id == source.id))
    ).scalar_one()
    await db_session.refresh(reloaded, attribute_names=["collections", "connectors"])
    for collection in reloaded.collections:
        await db_session.refresh(collection, attribute_names=["sku_selections"])
    for conn in reloaded.connectors:
        await db_session.refresh(conn, attribute_names=["sku_selection"])

    copy = await import_architecture(db_session, reloaded, importer, "My Source")

    assert copy.id != source.id
    assert copy.user_id == importer.id
    assert copy.name == "My Source"
    assert copy.is_public is False

    copy_collections = (
        await db_session.execute(select(Collection).where(Collection.architecture_id == copy.id))
    ).scalars().all()
    assert len(copy_collections) == 2
    copy_vpc = next(c for c in copy_collections if c.type == "vpc")
    copy_app = next(c for c in copy_collections if c.type == "application_component")
    assert copy_vpc.id != vpc.id
    assert copy_app.id != app.id
    assert copy_app.parent_collection_id == copy_vpc.id  # remapped, not the original VPC's id

    copy_skus = (
        await db_session.execute(
            select(SKUSelection).where(SKUSelection.collection_id == copy_app.id)
        )
    ).scalars().all()
    assert len(copy_skus) == 1
    assert copy_skus[0].id != sku.id
    assert copy_skus[0].sku == "SKU1"

    copy_connectors = (
        await db_session.execute(
            select(DataConnector).where(DataConnector.architecture_id == copy.id)
        )
    ).scalars().all()
    assert len(copy_connectors) == 1
    assert copy_connectors[0].id != connector.id
    assert copy_connectors[0].from_collection_id == copy_vpc.id
    assert copy_connectors[0].to_collection_id == copy_app.id

    copy_connector_sku = (
        await db_session.execute(
            select(SKUSelection).where(SKUSelection.connector_id == copy_connectors[0].id)
        )
    ).scalar_one()
    assert copy_connector_sku.id != connector_sku.id
    assert copy_connector_sku.sku == "SKU2"

    # The source is untouched by the import.
    still_source = await db_session.get(Architecture, source.id)
    assert still_source is not None
    assert still_source.user_id == owner.id

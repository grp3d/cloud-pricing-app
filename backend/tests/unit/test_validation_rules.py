"""Tests for the data-model check constraints (data-model.md) that the API layer also
enforces, but which must hold at the database level regardless of API-layer bugs.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection, User


@pytest.mark.asyncio
async def test_data_connector_rejects_self_link(db_session):
    user = User(id=uuid.uuid4())
    architecture = Architecture(user_id=user.id, name="A", provider="aws")
    collection = Collection(architecture=architecture, type="vpc", name="VPC A")
    db_session.add_all([user, architecture, collection])
    await db_session.flush()

    connector = DataConnector(
        architecture_id=architecture.id,
        from_collection_id=collection.id,
        to_collection_id=collection.id,
    )
    db_session.add(connector)
    with pytest.raises(IntegrityError, match="ck_connector_no_self_link"):
        await db_session.commit()


@pytest.mark.asyncio
async def test_sku_selection_requires_exactly_one_parent(db_session):
    user = User(id=uuid.uuid4())
    architecture = Architecture(user_id=user.id, name="A", provider="aws")
    db_session.add_all([user, architecture])
    await db_session.flush()

    # Neither collection_id nor connector_id set.
    orphan = SKUSelection(
        service_code="AmazonEC2",
        sku="X",
        pricing_term="on_demand",
        purchase_option="not_applicable",
        usage_quantity=Decimal("1"),
    )
    db_session.add(orphan)
    with pytest.raises(IntegrityError, match="ck_sku_selection_exactly_one_parent"):
        await db_session.commit()


@pytest.mark.asyncio
async def test_sku_selection_rejects_both_parents(db_session):
    user = User(id=uuid.uuid4())
    architecture = Architecture(user_id=user.id, name="A", provider="aws")
    c1 = Collection(architecture=architecture, type="vpc", name="A")
    c2 = Collection(architecture=architecture, type="vpc", name="B")
    db_session.add_all([user, architecture, c1, c2])
    await db_session.flush()
    connector = DataConnector(
        architecture_id=architecture.id, from_collection_id=c1.id, to_collection_id=c2.id
    )
    db_session.add(connector)
    await db_session.flush()

    both = SKUSelection(
        collection_id=c1.id,
        connector_id=connector.id,
        service_code="AmazonEC2",
        sku="X",
        pricing_term="on_demand",
        purchase_option="not_applicable",
        usage_quantity=Decimal("1"),
    )
    db_session.add(both)
    with pytest.raises(IntegrityError, match="ck_sku_selection_exactly_one_parent"):
        await db_session.commit()

"""Tests for the two new Collection-nesting check constraints (data-model.md, spec FR-004)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.orm import Architecture, Collection, User


@pytest.mark.asyncio
async def test_application_component_may_have_a_vpc_parent(db_session):
    """Positive case: valid nesting is accepted, not rejected by the new constraints."""
    user = User(id=uuid.uuid4())
    architecture = Architecture(user_id=user.id, name="A", provider="aws")
    vpc = Collection(architecture=architecture, type="vpc", name="VPC", region="us-east-1")
    app = Collection(
        architecture=architecture, type="application_component", name="App", region="us-east-1"
    )
    db_session.add_all([user, architecture, vpc, app])
    await db_session.flush()

    app.parent_collection_id = vpc.id
    await db_session.commit()  # must not raise

    await db_session.refresh(app)
    assert app.parent_collection_id == vpc.id


@pytest.mark.asyncio
async def test_vpc_parent_collection_id_must_stay_null(db_session):
    """A VPC can never have a parent, even another VPC (spec FR-004)."""
    user = User(id=uuid.uuid4())
    architecture = Architecture(user_id=user.id, name="A", provider="aws")
    vpc1 = Collection(architecture=architecture, type="vpc", name="VPC 1", region="us-east-1")
    vpc2 = Collection(architecture=architecture, type="vpc", name="VPC 2", region="us-east-1")
    db_session.add_all([user, architecture, vpc1, vpc2])
    await db_session.flush()

    vpc2.parent_collection_id = vpc1.id
    with pytest.raises(IntegrityError, match="ck_collection_parent_only_app_component"):
        await db_session.commit()


@pytest.mark.asyncio
async def test_collection_cannot_be_its_own_parent(db_session):
    user = User(id=uuid.uuid4())
    architecture = Architecture(user_id=user.id, name="A", provider="aws")
    app = Collection(
        architecture=architecture, type="application_component", name="App", region="us-east-1"
    )
    db_session.add_all([user, architecture, app])
    await db_session.flush()

    app.parent_collection_id = app.id
    with pytest.raises(IntegrityError, match="ck_collection_no_self_parent"):
        await db_session.commit()

"""025 (research R2): applying a state to a saved architecture keeps ids and is exact, so accept,
undo and redo can all be "apply this state". Real Postgres."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.models.orm import Collection, DataConnector, SKUSelection
from src.services.architecture_state import (
    CollectionState,
    ConnectorState,
    ServiceState,
    apply_state,
    fingerprint,
    read_state,
)
from tests.helpers.agent import build_standard
from tests.helpers.architectures import assert_state_equal, make_user

WEB_APP = "Active-Standby Multi-Region Web Application"


@pytest.fixture
async def saved(db_session):
    user = await make_user(db_session)
    architecture = await build_standard(db_session, user, "aws", WEB_APP, rename="Prod Web")
    before = await read_state(db_session, architecture.id)
    return db_session, architecture.id, before


def _changed(before):
    """Add a collection with a service, change a quantity and a collection name, remove a
    service, and rename the architecture."""
    after = before.model_copy(deep=True)
    after.name = "Prod Web v2"
    stamp = max(c.created_at for c in before.collections) + timedelta(seconds=1)
    new = CollectionState(id=uuid.uuid4(), type="vpc", name="Standby", region="eu-west-1",
                          created_at=stamp)
    after.collections.append(new)
    after.services.append(ServiceState(
        **{**after.services[0].model_dump(), "id": uuid.uuid4(), "collection_id": new.id,
           "connector_id": None, "created_at": stamp}))
    after.services[0].usage_quantity = Decimal("372")
    after.collections[0].name = "Primary"
    after.services.pop(1)
    return after


async def test_apply_changes_then_restores_exactly(saved):
    db, architecture_id, before = saved
    after = _changed(before)
    await apply_state(db, architecture_id, after)
    await db.commit()
    assert_state_equal(await read_state(db, architecture_id), after)

    await apply_state(db, architecture_id, before)
    await db.commit()
    restored = await read_state(db, architecture_id)
    assert_state_equal(restored, before)
    assert fingerprint(restored) == fingerprint(before)

    await apply_state(db, architecture_id, after)
    await db.commit()
    assert_state_equal(await read_state(db, architecture_id), after)


async def test_removed_rows_are_soft_deleted_and_revived_with_the_same_ids(saved):
    db, architecture_id, before = saved
    after = before.model_copy(deep=True)
    gone = after.collections.pop()
    after.services = [s for s in after.services if s.collection_id != gone.id]
    after.connectors = [c for c in after.connectors if gone.id not in (c.from_id, c.to_id)]
    after.services = [s for s in after.services
                      if s.connector_id is None or after.connector(s.connector_id)]
    for c in after.collections:
        if c.parent_id == gone.id:
            c.parent_id = None
    await apply_state(db, architecture_id, after)
    await db.commit()
    row = await db.get(Collection, gone.id)
    assert row is not None and row.deleted_at is not None

    await apply_state(db, architecture_id, before)
    await db.commit()
    row = await db.get(Collection, gone.id)
    assert row.deleted_at is None
    assert_state_equal(await read_state(db, architecture_id), before)


async def test_services_dropped_from_the_target_are_deleted(saved):
    db, architecture_id, before = saved
    after = before.model_copy(deep=True)
    dropped = next(s for s in after.services if s.collection_id is not None)
    after.services.remove(dropped)
    await apply_state(db, architecture_id, after)
    await db.commit()
    assert await db.get(SKUSelection, dropped.id) is None


async def test_nothing_is_applied_when_the_transaction_is_rolled_back(saved):
    db, architecture_id, before = saved
    await apply_state(db, architecture_id, _changed(before))
    await db.rollback()
    assert_state_equal(await read_state(db, architecture_id), before)


async def test_a_new_connector_with_a_service(saved):
    db, architecture_id, before = saved
    after = before.model_copy(deep=True)
    a, b = after.collections[0], after.collections[1]
    stamp = max(c.created_at for c in before.collections) + timedelta(seconds=1)
    connector = ConnectorState(id=uuid.uuid4(), from_id=a.id, to_id=b.id, arrow_style="one_way",
                               created_at=stamp)
    after.connectors.append(connector)
    after.services.append(ServiceState(
        **{**after.services[0].model_dump(), "id": uuid.uuid4(), "collection_id": None,
           "connector_id": connector.id, "created_at": stamp}))
    await apply_state(db, architecture_id, after)
    await db.commit()
    assert_state_equal(await read_state(db, architecture_id), after)
    rows = (await db.execute(select(DataConnector).where(
        DataConnector.architecture_id == architecture_id))).scalars().all()
    assert connector.id in {r.id for r in rows}

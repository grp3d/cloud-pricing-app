"""Undo and redo (025, US4, FR-005, FR-006, FR-013, FR-016, research R3): one accepted message
undoes and redoes exactly, and only while nothing else changed the architecture."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.agent.proposals import (
    Draft,
    ServiceSpec,
    cost_summary,
    create_proposal,
    db_clock,
)
from src.models.orm import (
    AgentMessage,
    AgentOperation,
    AgentSession,
    Architecture,
    Collection,
    User,
)
from src.services.architecture_state import ArchitectureState, read_state
from tests.helpers.agent import build_standard
from tests.helpers.architectures import assert_state_equal

WEB_APP = "Active-Standby Multi-Region Web Application"


@pytest.fixture
async def world(db_session):
    user = User(id=uuid.uuid4(), username=f"u-{uuid.uuid4().hex[:6]}",
                agent_preview_input_counter=0)
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(UTC)
    agent_session = AgentSession(user_id=user.id, started_at=now,
                                 closes_at=now + timedelta(days=3))
    db_session.add(agent_session)
    await db_session.flush()
    message = AgentMessage(session_id=agent_session.id, seq=1, role="user", content="q",
                           status="answered")
    db_session.add(message)
    architecture = await build_standard(db_session, user, "aws", WEB_APP, rename="Prod Web")
    return db_session, user, agent_session, message, architecture.id


def _headers(user) -> dict:
    return {"Authorization": f"Bearer {user.id}"}


def _url(proposal_id, action) -> str:
    return f"/api/v1/agent/proposals/{proposal_id}/{action}"


async def _many_changes(world) -> tuple[uuid.UUID, ArchitectureState, ArchitectureState]:
    """Twenty changes from one message: a collection, services, changes and a removal."""
    db, _user, agent_session, message, architecture_id = world
    base = await read_state(db, architecture_id)
    draft = Draft(base, await db_clock(db))
    new = draft.add_collection("new1", type="vpc", name="Standby", region="us-west-2",
                               parent_id=None, group="standby")
    template = base.services[0]
    for n in range(12):
        draft.add_service(ServiceSpec(template.service_code, template.sku, template.pricing_term,
                                      template.purchase_option, template.usage_quantity, None,
                                      f"Copy {n}"), collection_id=new, group="standby",
                          where="Standby")
    for service in base.services[1:6]:
        draft.change("service", service.id, {"usage_quantity": str(service.usage_quantity * 3)},
                     label="Triple", group="scale")
    draft.remove("service", base.services[7].id, label="Drop", group="scale")
    draft.rename(f"Prod Web {uuid.uuid4().hex[:4]}", group="scale")
    assert len(draft.items) == 20
    target = draft.state
    proposal = await create_proposal(
        db, agent_session, message, kind="change", title="Many", base=base, target=target,
        items=draft.items, cost=cost_summary(base, draft.items, target, "1_month"),
        assumptions=[], architecture_id=architecture_id)
    await db.commit()
    return proposal.id, base, target


async def _accept(client, user, proposal_id, architecture_id):
    response = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                                 json={"architecture_id": str(architecture_id)
                                       if architecture_id else None})
    assert response.status_code == 200, response.text
    return response.json()


async def test_twenty_changes_undo_and_redo_exactly(client, world):
    db, user, _s, _m, architecture_id = world
    proposal_id, base, target = await _many_changes(world)
    await _accept(client, user, proposal_id, architecture_id)
    assert_state_equal(await read_state(db, architecture_id), target)

    undone = await client.post(_url(proposal_id, "undo"), headers=_headers(user))
    assert undone.status_code == 200, undone.text
    assert undone.json()["proposal"]["undo"] == {"status": "undone", "can_undo": False,
                                                 "can_redo": True, "end_reason": None}
    assert_state_equal(await read_state(db, architecture_id), base)

    redone = await client.post(_url(proposal_id, "redo"), headers=_headers(user))
    assert redone.status_code == 200
    assert_state_equal(await read_state(db, architecture_id), target)
    names = (await db.execute(select(AgentOperation.name).order_by(AgentOperation.seq)
                              )).scalars().all()
    assert names == ["accept_proposal", "undo_proposal", "redo_proposal"]


async def test_undoing_a_new_architecture_removes_it_and_redo_restores_it(client, world):
    db, user, agent_session, message, architecture_id = world
    base = await read_state(db, architecture_id)
    draft = Draft(ArchitectureState(name="Fresh", provider="aws"), await db_clock(db))
    vpc = draft.add_collection("new1", type="vpc", name="Web", region="us-east-1",
                               parent_id=None, group=None)
    s = base.services[0]
    draft.add_service(ServiceSpec(s.service_code, s.sku, s.pricing_term, s.purchase_option,
                                  s.usage_quantity, None, "Copy"), collection_id=vpc,
                      group=None, where="Web")
    target = draft.state
    proposal = await create_proposal(
        db, agent_session, message, kind="create", title="Fresh", base=None, target=target,
        items=draft.items, cost=cost_summary(None, draft.items, target, "1_month"),
        assumptions=[], architecture_id=None)
    await db.commit()
    body = await _accept(client, user, proposal.id, None)
    new_id = uuid.UUID(body["open_architecture_id"])
    assert (await client.post(_url(proposal.id, "undo"), headers=_headers(user))).status_code \
        == 200
    assert (await db.get(Architecture, new_id, populate_existing=True)).deleted_at is not None
    assert (await client.get(f"/api/v1/architectures/{new_id}", headers=_headers(user))
            ).status_code == 404
    assert (await client.post(_url(proposal.id, "redo"), headers=_headers(user))).status_code \
        == 200
    assert (await db.get(Architecture, new_id, populate_existing=True)).deleted_at is None
    assert_state_equal(await read_state(db, new_id), target)


@pytest.mark.parametrize("edit", ["service", "collection", "rename", "connector"])
async def test_a_manual_edit_ends_undo(client, world, edit):
    db, user, _s, _m, architecture_id = world
    proposal_id, base, _target = await _many_changes(world)
    await _accept(client, user, proposal_id, architecture_id)
    h = _headers(user)
    if edit == "service":
        r = await client.patch(f"/api/v1/sku-selections/{base.services[2].id}", headers=h,
                               json={"usage_quantity": "1"})
    elif edit == "collection":
        r = await client.post(f"/api/v1/architectures/{architecture_id}/collections", headers=h,
                              json={"type": "vpc", "name": "Extra", "region": "us-east-1"})
    elif edit == "rename":
        r = await client.patch(f"/api/v1/architectures/{architecture_id}", headers=h,
                               json={"name": "Renamed by hand"})
    else:
        ids = [c.id for c in base.collections]
        r = await client.post(f"/api/v1/architectures/{architecture_id}/connectors", headers=h,
                              json={"from_collection_id": str(ids[0]),
                                    "to_collection_id": str(ids[1])})
    assert r.status_code in (200, 201), r.text
    detail = (await client.get("/api/v1/agent/session", headers=h)).json()
    assert detail["proposals"][0]["undo"] == {"status": "ended", "can_undo": False,
                                              "can_redo": False, "end_reason": "edited"}
    refused = await client.post(_url(proposal_id, "undo"), headers=h)
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Your latest edit means the agent's previous change can no longer be undone.")


async def test_making_it_public_doesnt_end_undo(client, world):
    _db, user, _s, _m, architecture_id = world
    proposal_id, _base, _target = await _many_changes(world)
    await _accept(client, user, proposal_id, architecture_id)
    r = await client.patch(f"/api/v1/architectures/{architecture_id}", headers=_headers(user),
                           json={"is_public": True})
    assert r.status_code == 200
    assert (await client.post(_url(proposal_id, "undo"), headers=_headers(user))).status_code \
        == 200


async def test_the_end_is_kept_even_if_the_edit_is_reverted(client, world):
    _db, user, _s, _m, architecture_id = world
    proposal_id, _base, target = await _many_changes(world)
    await _accept(client, user, proposal_id, architecture_id)
    h = _headers(user)
    await client.patch(f"/api/v1/architectures/{architecture_id}", headers=h,
                       json={"name": "Temporary"})
    await client.get("/api/v1/agent/session", headers=h)  # the end is seen and saved
    await client.patch(f"/api/v1/architectures/{architecture_id}", headers=h,
                       json={"name": target.name})
    assert (await client.post(_url(proposal_id, "undo"), headers=h)).status_code == 409


async def test_only_the_latest_accepted_proposal_can_be_undone(client, world):
    _db, user, _s, _m, architecture_id = world
    first, _b, _t = await _many_changes(world)
    await _accept(client, user, first, architecture_id)
    second, _b, _t = await _many_changes(world)
    await _accept(client, user, second, architecture_id)
    refused = await client.post(_url(first, "undo"), headers=_headers(user))
    assert refused.status_code == 409
    assert "A later change replaced this one" in refused.json()["detail"]
    assert (await client.post(_url(second, "undo"), headers=_headers(user))).status_code == 200


async def test_deleting_the_architecture_ends_undo(client, world):
    _db, user, _s, _m, architecture_id = world
    proposal_id, _b, _t = await _many_changes(world)
    await _accept(client, user, proposal_id, architecture_id)
    await client.delete(f"/api/v1/architectures/{architecture_id}", headers=_headers(user))
    refused = await client.post(_url(proposal_id, "undo"), headers=_headers(user))
    assert refused.status_code == 409 and "deleted" in refused.json()["detail"]


async def test_undo_waits_while_a_message_is_answered(client, world):
    db, user, agent_session, message, architecture_id = world
    proposal_id, _b, _t = await _many_changes(world)
    await _accept(client, user, proposal_id, architecture_id)
    agent_session.busy_message_id = message.id
    await db.commit()
    refused = await client.post(_url(proposal_id, "undo"), headers=_headers(user))
    assert (refused.status_code, refused.json()["detail"]) == (409, "busy")


async def test_undo_ends_with_the_session(client, world):
    db, user, agent_session, _m, architecture_id = world
    proposal_id, _b, _t = await _many_changes(world)
    await _accept(client, user, proposal_id, architecture_id)
    agent_session.closes_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    refused = await client.post(_url(proposal_id, "undo"), headers=_headers(user))
    assert refused.status_code == 404


async def test_undo_and_redo_work_after_a_limit_and_use_no_allowance(client, world):
    db, user, _s, _m, architecture_id = world
    proposal_id, _b, _t = await _many_changes(world)
    await _accept(client, user, proposal_id, architecture_id)  # allowance already 0
    assert (await client.post(_url(proposal_id, "undo"), headers=_headers(user))).status_code \
        == 200
    assert (await client.post(_url(proposal_id, "redo"), headers=_headers(user))).status_code \
        == 200
    await db.refresh(user)
    assert user.agent_preview_input_counter == 0


async def test_removed_rows_come_back_with_their_ids(client, world):
    db, user, _s, _m, architecture_id = world
    proposal_id, base, _target = await _many_changes(world)
    await _accept(client, user, proposal_id, architecture_id)
    await client.post(_url(proposal_id, "undo"), headers=_headers(user))
    ids = set((await db.execute(select(Collection.id).where(
        Collection.architecture_id == architecture_id, Collection.deleted_at.is_(None))
    )).scalars())
    assert ids == {c.id for c in base.collections}

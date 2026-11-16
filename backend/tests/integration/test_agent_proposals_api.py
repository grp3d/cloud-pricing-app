"""Accepting and rejecting proposals (025, contracts/agent-api.md, FR-003, FR-007, FR-016): the
saved architecture changes only on accept, exactly as proposed; a stale proposal is re-priced
first; nothing calls the model or uses the allowance; only the owner can act."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

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
    AgentProposal,
    AgentSession,
    Architecture,
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


async def _change_proposal(world, *, group="standby") -> tuple[uuid.UUID, ArchitectureState,
                                                               ArchitectureState]:
    db, user, agent_session, message, architecture_id = world
    base = await read_state(db, architecture_id)
    draft = Draft(base, await db_clock(db))
    template = base.services[0]
    standby = draft.add_collection("new1", type="vpc", name="Standby", region="us-west-2",
                                   parent_id=None, group=group)
    draft.add_service(ServiceSpec(template.service_code, template.sku, template.pricing_term,
                                  template.purchase_option, template.usage_quantity, None,
                                  "Copy"), collection_id=standby, group=group, where="Standby")
    draft.change("service", base.services[1].id,
                 {"usage_quantity": str(base.services[1].usage_quantity * 2)},
                 label="Double", group=group)
    target = draft.state
    proposal = await create_proposal(
        db, agent_session, message, kind="change", title="Replicate", base=base, target=target,
        items=draft.items, cost=cost_summary(base, draft.items, target, "1_month"),
        assumptions=[], architecture_id=architecture_id)
    await db.commit()
    return proposal.id, base, target


def _headers(user) -> dict:
    return {"Authorization": f"Bearer {user.id}"}


def _url(proposal_id, action) -> str:
    return f"/api/v1/agent/proposals/{proposal_id}/{action}"


async def test_session_detail_lists_the_pending_proposal(client, world):
    _db, user, _s, _m, architecture_id = world
    proposal_id, _base, _target = await _change_proposal(world)
    detail = (await client.get("/api/v1/agent/session", headers=_headers(user))).json()
    [out] = detail["proposals"]
    assert out["id"] == str(proposal_id) and out["status"] == "pending"
    assert out["stale"] is False and out["undo"] is None
    assert out["architecture_name"] == "Prod Web"
    assert [i["op"] for i in out["items"]] == ["add", "add", "change"]
    assert "id" not in out["items"][0]
    assert [m["proposal_ids"] for m in detail["messages"]] == [[str(proposal_id)]]


async def test_accept_saves_exactly_the_proposal(client, world):
    db, user, _s, _m, architecture_id = world
    proposal_id, _base, target = await _change_proposal(world)
    response = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                                 json={"architecture_id": str(architecture_id)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proposal"]["status"] == "accepted"
    assert body["proposal"]["undo"] == {"status": "available", "can_undo": True,
                                        "can_redo": False, "end_reason": None}
    assert body["open_architecture_id"] is None
    db.expire_all()
    assert_state_equal(await read_state(db, architecture_id), target)
    log = (await db.execute(select(AgentOperation.name))).scalars().all()
    assert "accept_proposal" in log


async def test_reject_changes_nothing(client, world):
    db, user, _s, _m, architecture_id = world
    proposal_id, base, _target = await _change_proposal(world)
    response = await client.post(_url(proposal_id, "reject"), headers=_headers(user))
    assert response.status_code == 200
    assert response.json()["proposal"]["status"] == "rejected"
    assert_state_equal(await read_state(db, architecture_id), base)
    again = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                              json={"architecture_id": str(architecture_id)})
    assert again.status_code == 409


async def test_nothing_is_saved_before_accept(world):
    db, _user, _s, _m, architecture_id = world
    before = await read_state(db, architecture_id)
    await _change_proposal(world)
    assert_state_equal(await read_state(db, architecture_id), before)


async def test_accept_needs_the_architecture_open(client, world):
    _db, user, _s, _m, _architecture_id = world
    proposal_id, _base, _target = await _change_proposal(world)
    response = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                                 json={"architecture_id": None})
    assert response.status_code == 409
    assert response.json()["detail"] == "Open Prod Web to accept this change."


async def test_accept_is_refused_while_a_message_is_answered(client, world):
    db, user, agent_session, message, architecture_id = world
    proposal_id, _base, _target = await _change_proposal(world)
    agent_session.busy_message_id = message.id
    await db.commit()
    response = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                                 json={"architecture_id": str(architecture_id)})
    assert (response.status_code, response.json()["detail"]) == (409, "busy")


async def test_a_stale_proposal_is_repriced_then_accepted(client, world):
    db, user, _s, _m, architecture_id = world
    proposal_id, base, _target = await _change_proposal(world)
    # The user edits the architecture by hand.
    service = base.services[3]
    edited = await client.patch(f"/api/v1/sku-selections/{service.id}", headers=_headers(user),
                                json={"usage_quantity": "5"})
    assert edited.status_code == 200
    detail = (await client.get("/api/v1/agent/session", headers=_headers(user))).json()
    assert detail["proposals"][0]["stale"] is True
    old_after = Decimal(detail["proposals"][0]["cost"]["after"]["total"])

    response = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                                 json={"architecture_id": str(architecture_id)})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "stale"
    detail = (await client.get("/api/v1/agent/session", headers=_headers(user))).json()
    out = detail["proposals"][0]
    assert out["stale"] is False and out["status"] == "pending"
    assert Decimal(out["cost"]["after"]["total"]) != old_after

    response = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                                 json={"architecture_id": str(architecture_id),
                                       "confirm_restaled": True})
    assert response.status_code == 200, response.text
    db.expire_all()
    saved = await read_state(db, architecture_id)
    assert saved.service(service.id).usage_quantity == Decimal("5")  # the user's edit kept
    assert any(c.name == "Standby" for c in saved.collections)


async def test_a_proposal_that_no_longer_applies_is_refused(client, world):
    _db, user, _s, _m, architecture_id = world
    proposal_id, base, _target = await _change_proposal(world)
    removed = base.services[1]  # the one the proposal changes
    await client.delete(f"/api/v1/sku-selections/{removed.id}", headers=_headers(user))
    response = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                                 json={"architecture_id": str(architecture_id)})
    assert response.status_code == 422
    assert "no longer in the architecture" in response.json()["detail"]


async def test_actions_use_no_allowance_and_no_model(client, world, monkeypatch):
    db, user, _s, _m, architecture_id = world
    import src.agent.model as model

    monkeypatch.setattr(model, "build_client", lambda *a, **k: pytest.fail("model called"))
    proposal_id, _base, _target = await _change_proposal(world)
    response = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                                 json={"architecture_id": str(architecture_id)})
    assert response.status_code == 200
    await db.refresh(user)
    assert user.agent_preview_input_counter == 0


async def test_another_users_proposal_is_not_found(client, world):
    db, _user, _s, _m, architecture_id = world
    proposal_id, _base, _target = await _change_proposal(world)
    stranger = User(id=uuid.uuid4(), username=f"s-{uuid.uuid4().hex[:6]}")
    db.add(stranger)
    await db.flush()
    now = datetime.now(UTC)
    db.add(AgentSession(user_id=stranger.id, started_at=now, closes_at=now + timedelta(days=3)))
    await db.commit()
    response = await client.post(_url(proposal_id, "accept"), headers=_headers(stranger),
                                 json={"architecture_id": str(architecture_id)})
    assert response.status_code == 404


async def test_a_new_proposal_supersedes_the_pending_one(world):
    db, *_ = world
    first, _b, _t = await _change_proposal(world)
    second, _b, _t = await _change_proposal(world)
    statuses = {p.id: p.status for p in (await db.execute(select(AgentProposal))).scalars()}
    assert statuses[first] == "superseded" and statuses[second] == "pending"


async def test_accepting_a_new_architecture_creates_it_private_and_returns_it(client, world):
    db, user, agent_session, message, _architecture_id = world
    base = await read_state(db, _architecture_id)
    empty = ArchitectureState(name="Fresh", provider="aws")
    draft = Draft(empty, await db_clock(db))
    vpc = draft.add_collection("new1", type="vpc", name="Web", region="us-east-1",
                               parent_id=None, group=None)
    s = base.services[0]
    draft.add_service(ServiceSpec(s.service_code, s.sku, s.pricing_term, s.purchase_option,
                                  s.usage_quantity, None, "Copy"), collection_id=vpc, group=None,
                      where="Web")
    target = draft.state
    proposal = await create_proposal(
        db, agent_session, message, kind="create", title="Fresh", base=None, target=target,
        items=draft.items, cost=cost_summary(None, draft.items, target, "1_month"),
        assumptions=[], architecture_id=None)
    await db.commit()
    response = await client.post(_url(proposal.id, "accept"), headers=_headers(user),
                                 json={"architecture_id": None})
    assert response.status_code == 200, response.text
    new_id = uuid.UUID(response.json()["open_architecture_id"])
    created = await db.get(Architecture, new_id)
    assert (created.user_id, created.is_public, created.name) == (user.id, False, "Fresh")
    assert_state_equal(await read_state(db, new_id), target)
    assert response.json()["proposal"]["undo"]["can_undo"] is True

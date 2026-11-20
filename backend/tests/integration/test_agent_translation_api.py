"""Translations through the proposal API (026, contracts/agent-api.md, SC-004, FR-012, FR-017):
accept creates the user's private architecture on the target provider, reject creates nothing,
undo and redo work as for a create, the original never changes, and a stale translation can't be
accepted."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, update

from src.agent.operations import registry
from src.models.orm import AgentOperation, AgentProposal, Architecture, ServiceMapping
from src.services.architecture_state import fingerprint, read_state
from tests.helpers.agent import build_standard, combined_pricing_root
from tests.helpers.translation import WEB_APP, context, make_world


@pytest.fixture
async def translated(db_session, use_pricing_root):
    use_pricing_root(combined_pricing_root())
    world = await make_world(db_session)
    source = await build_standard(db_session, world[1], "aws", WEB_APP, rename="Prod Web")
    ctx = context(world, source.id)
    await registry.run(ctx, "find_translation", {"provider": "azure"})
    await registry.run(ctx, "propose_translation", {"provider": "azure"})
    await db_session.commit()
    original = fingerprint(await read_state(db_session, source.id))
    return db_session, world[1], source.id, ctx.proposals[-1].id, original


def _url(proposal_id, action):
    return f"/api/v1/agent/proposals/{proposal_id}/{action}"


def _headers(user):
    return {"Authorization": f"Bearer {user.id}"}


async def _same_original(db, source_id, original):
    assert fingerprint(await read_state(db, source_id)) == original


async def test_accept_undo_redo_and_the_original_never_changes(client, translated):
    db, user, source_id, proposal_id, original = translated
    accepted = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                                 json={"architecture_id": None})
    assert accepted.status_code == 200, accepted.text
    new_id = uuid.UUID(accepted.json()["open_architecture_id"])
    created = await db.get(Architecture, new_id)
    assert (created.user_id, created.provider, created.is_public, created.name) == (
        user.id, "azure", False, "Prod Web")
    proposal = await db.get(AgentProposal, proposal_id)
    await db.refresh(proposal)
    assert fingerprint(await read_state(db, new_id)) == proposal.after_fingerprint
    await _same_original(db, source_id, original)
    assert (await client.post(_url(proposal_id, "undo"), headers=_headers(user))).status_code \
        == 200
    await db.refresh(created)
    assert created.deleted_at is not None
    await _same_original(db, source_id, original)
    assert (await client.post(_url(proposal_id, "redo"), headers=_headers(user))).status_code \
        == 200
    await db.refresh(created)
    assert created.deleted_at is None
    await _same_original(db, source_id, original)
    logged = (await db.execute(select(AgentOperation).where(
        AgentOperation.name.in_(("accept_proposal", "undo_proposal", "redo_proposal"))))
    ).scalars().all()
    assert len(logged) == 3
    for entry in logged:
        assert entry.summary["mapping_version"]["seed"] == 1
        assert set(entry.snapshot) == {"aws", "azure"}


async def test_reject_creates_nothing(client, translated):
    db, user, source_id, proposal_id, original = translated
    before = (await db.execute(select(Architecture.id))).scalars().all()
    rejected = await client.post(_url(proposal_id, "reject"), headers=_headers(user))
    assert rejected.status_code == 200, rejected.text
    assert (await db.execute(select(Architecture.id))).scalars().all() == before
    await _same_original(db, source_id, original)


async def _stale_then_refused(client, db, user, proposal_id):
    detail = await client.get("/api/v1/agent/session", headers=_headers(user))
    shown = next(p for p in detail.json()["proposals"] if p["id"] == str(proposal_id))
    assert shown["stale"] is True
    refused = await client.post(_url(proposal_id, "accept"), headers=_headers(user),
                                json={"architecture_id": None})
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "stale_translation"
    proposal = await db.get(AgentProposal, proposal_id)
    await db.refresh(proposal)
    assert proposal.status == "expired"


async def test_a_changed_source_makes_it_stale(client, translated):
    db, user, source_id, proposal_id, _original = translated
    architecture = await db.get(Architecture, source_id)
    architecture.name = "Prod Web 2"
    await db.commit()
    await _stale_then_refused(client, db, user, proposal_id)


async def test_a_changed_seed_version_makes_it_stale(client, translated):
    db, user, _source_id, proposal_id, _original = translated
    await db.execute(update(ServiceMapping).values(version=ServiceMapping.version + 1))
    await db.commit()
    try:
        await _stale_then_refused(client, db, user, proposal_id)
    finally:
        await db.execute(update(ServiceMapping).values(version=ServiceMapping.version - 1))
        await db.commit()


async def test_a_changed_pricing_snapshot_makes_it_stale(client, translated, monkeypatch):
    db, user, _source_id, proposal_id, _original = translated
    proposal = await db.get(AgentProposal, proposal_id)
    record = dict(proposal.translation)
    record["mapping_version"] = {**record["mapping_version"],
                                 "snapshots": {**record["mapping_version"]["snapshots"],
                                               "azure": "2026-01-01"}}
    proposal.translation = record
    await db.commit()
    await _stale_then_refused(client, db, user, proposal_id)

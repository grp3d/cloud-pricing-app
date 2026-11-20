"""The eval runner's 025 checks (research R10): proposal expectations and scripted user actions,
on a proposal built directly (no model)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from src.agent.proposals import (
    Draft,
    ServiceSpec,
    cost_summary,
    create_proposal,
    db_clock,
)
from src.models.orm import AgentMessage, AgentSession, User
from src.services.architecture_state import fingerprint, read_state
from tests.agent_evals.runner import proposal_checks, run_actions
from tests.helpers.agent import build_standard

WEB_APP = "Active-Standby Multi-Region Web Application"


async def _world(db):
    user = User(id=uuid.uuid4(), username=f"r-{uuid.uuid4().hex[:6]}")
    db.add(user)
    await db.flush()
    now = datetime.now(UTC)
    agent_session = AgentSession(user_id=user.id, started_at=now,
                                 closes_at=now + timedelta(days=3))
    db.add(agent_session)
    await db.flush()
    message = AgentMessage(session_id=agent_session.id, seq=1, role="user", content="q",
                           status="answered")
    db.add(message)
    architecture = await build_standard(db, user, "aws", WEB_APP)
    base = await read_state(db, architecture.id)
    draft = Draft(base, await db_clock(db))
    one, two = base.services[0], base.services[1]
    new = draft.add_collection("new1", type="vpc", name="Standby", region="us-west-2",
                               parent_id=None, group="standby")
    # An AWS SKU is per region, so this us-east-1 copy in us-west-2 is unpriceable (partial).
    draft.add_service(ServiceSpec(one.service_code, one.sku, one.pricing_term,
                                  one.purchase_option, one.usage_quantity, None, "Copy"),
                      collection_id=new, group="standby", where="Standby")
    draft.change("service", two.id, {"usage_quantity": str(two.usage_quantity * 2)},
                 label="Double", group="scale")
    target = draft.state
    proposal = await create_proposal(
        db, agent_session, message, kind="change", title="t", base=base, target=target,
        items=draft.items, cost=cost_summary(base, draft.items, target, "1_month"),
        assumptions=[], architecture_id=architecture.id)
    await db.commit()
    return user, agent_session, proposal, base, target


async def test_proposal_checks_pass_for_a_good_proposal(db_session):
    _user, _s, proposal, _base, _target = await _world(db_session)
    checks = proposal_checks({"proposal": {"kind": "change", "at_least": {"add": 2},
                                           "none_of": ["remove"], "partial": True}},
                             [proposal])
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]
    assert {c.name for c in checks} >= {"after total is the engine's",
                                        "before total is the engine's", "contributions add up"}


async def test_proposal_checks_catch_a_wrong_kind_and_a_missing_proposal(db_session):
    _user, _s, proposal, _base, _target = await _world(db_session)
    checks = proposal_checks({"proposal": {"kind": "create"}}, [proposal])
    assert not next(c for c in checks if c.name == "proposal is a create").passed
    assert not proposal_checks({"proposal": {"kind": "change"}}, [])[0].passed
    assert proposal_checks({"no_proposal": True}, [])[0].passed


async def test_actions_accept_undo_redo_and_a_manual_edit(db_session):
    user, agent_session, proposal, base, target = await _world(db_session)
    checks = await run_actions(db_session, user, agent_session, [proposal],
                               ["accept", "undo", "redo", "manual_edit", "undo"])
    named = [(c.name, c.passed) for c in checks]
    assert named[:4] == [("accept saves the proposal", True),
                         ("undo restores the architecture", True),
                         ("redo applies it again", True), ("a manual edit ends undo", True)]
    assert named[4] == ("undo allowed", False)  # undo has ended
    assert "can no longer be undone" in checks[4].detail
    saved = await read_state(db_session, proposal.architecture_id)
    assert fingerprint(saved) not in (fingerprint(base), fingerprint(target))


async def test_reject_leaves_the_architecture(db_session):
    user, agent_session, proposal, base, _target = await _world(db_session)
    checks = await run_actions(db_session, user, agent_session, [proposal], ["reject"])
    assert [(c.name, c.passed) for c in checks] == [("reject changes nothing", True)]


def test_the_question_limit_is_per_answer():
    """T068: GC-20 asked 2, then 0, then 3 questions over three messages; the limit (FR-001) is
    per answer, not per conversation."""
    from tests.agent_evals.runner import _result_checks

    answers = ["Which region? Which components?", "Proposed.", "Smaller family? Class? Storage?"]
    check = _result_checks({"max_questions": 3}, [], "".join(answers), answers)[0]
    assert check.passed and check.detail == "2, 0, 3 asked"
    answers[2] += " And the term?"
    assert not _result_checks({"max_questions": 3}, [], "".join(answers), answers)[0].passed


async def test_translation_checks(db_session, use_pricing_root):
    """026: the runner's translation expectations pass for a real translation and fail for a
    wrong one."""
    from src.agent.operations import registry
    from tests.agent_evals.runner import translation_checks
    from tests.helpers.agent import combined_pricing_root
    from tests.helpers.translation import context, make_world

    use_pricing_root(combined_pricing_root())
    world = await make_world(db_session)
    architecture = await build_standard(db_session, world[1], "aws", WEB_APP)
    ctx = context(world, architecture.id)
    await registry.run(ctx, "find_translation", {"provider": "gcp"})
    await registry.run(ctx, "propose_translation", {"provider": "gcp"})
    good = translation_checks({"translation": {
        "rows": {"matched": 14, "left_out": 2, "chosen_by_user": 0},
        "origins": ["seeded"], "partial": True}}, ctx.proposals)
    assert good and all(c.passed for c in good), [c.name for c in good if not c.passed]
    bad = translation_checks({"translation": {"rows": {"left_out": 0},
                                              "origins": ["chosen_by_user"],
                                              "partial": False}}, ctx.proposals)
    assert sorted(c.name for c in bad if not c.passed) == [
        "0 left_out", "has a chosen_by_user match", "translation total complete"]
    assert translation_checks({"translation": {"rows": {}}}, [])[0].passed is False

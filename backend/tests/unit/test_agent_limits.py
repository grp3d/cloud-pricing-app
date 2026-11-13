"""Access, preview and limits (023, research R6, FR-019–FR-023, clarification 4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.agent import limits
from src.agent.settings_service import EffectiveAgentSettings
from src.models.orm import AgentMessage, AgentSession, AgentUsage, User

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


def _effective(**overrides) -> EffectiveAgentSettings:
    values = {"enabled": True, "provider": "ollama", "model": "m", "base_url": "http://x",
              "timeout_seconds": 60, "global_monthly_cap_usd": Decimal("10"),
              "default_user_monthly_inputs": 100, "price_per_input_token_usd": None,
              "price_per_output_token_usd": None}
    values.update(overrides)
    return EffectiveAgentSettings(**values)


@pytest.fixture
async def user(db_session):
    u = User(id=uuid.uuid4(), username=f"u-{uuid.uuid4().hex[:6]}")
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.fixture
async def agent_session(db_session, user):
    s = AgentSession(user_id=user.id, started_at=NOW, closes_at=NOW + timedelta(days=3))
    db_session.add(s)
    await db_session.commit()
    return s


def _usage(user, *, at=NOW, counts=True, preview=False, cost="0"):
    return AgentUsage(user_id=user.id, provider="ollama", model="m", created_at=at,
                      counts_as_input=counts, is_preview=preview, cost_usd=Decimal(cost))


async def _accept(db, user, agent_session, effective=None):
    return await limits.accept_message(db, user, agent_session, "hi", None,
                                       effective or _effective(), NOW, usable=True)


@pytest.mark.parametrize(
    ("now", "expected"),
    [(NOW, "2026-12-01"), (datetime(2026, 12, 31, 23, 59, tzinfo=UTC), "2027-01-01")],
)
def test_resets_on_is_the_first_of_next_month_utc(now, expected):
    assert limits.resets_on(now) == expected


async def test_guest_is_refused(db_session):
    guest = User(id=uuid.uuid4())
    db_session.add(guest)
    await db_session.commit()
    status = await limits.status(db_session, guest, _effective(), NOW, usable=True)
    assert (status.available, status.reason) == (False, "guest")


async def test_agent_off_and_unavailable(db_session, user):
    off = await limits.status(db_session, user, _effective(enabled=False), NOW, usable=True)
    assert off.reason == "agent_off"
    unusable = await limits.status(db_session, user, _effective(), NOW, usable=False)
    assert unusable.reason == "unavailable"


async def test_preview_inputs_are_used_one_per_message(db_session, user, agent_session):
    for left in (2, 1, 0):
        message = await _accept(db_session, user, agent_session)
        assert message.is_preview is True
        await db_session.refresh(user)
        assert user.agent_preview_input_counter == left
        agent_session.busy_message_id = None
        await db_session.commit()
    with pytest.raises(limits.Refusal) as refused:
        await _accept(db_session, user, agent_session)
    assert (refused.value.reason, refused.value.resets_on) == ("preview_used", None)


async def test_enabled_user_uses_no_preview(db_session, user, agent_session):
    user.agent_enabled_for_user = True
    await db_session.commit()
    message = await _accept(db_session, user, agent_session)
    assert message.is_preview is False
    await db_session.refresh(user)
    assert user.agent_preview_input_counter == 3


async def test_monthly_limit_counts_preview_inputs_and_only_this_month(db_session, user,
                                                                       agent_session):
    user.agent_enabled_for_user = True
    user.agent_monthly_input_limit = 2
    db_session.add(_usage(user, preview=True))
    db_session.add(_usage(user, at=NOW - timedelta(days=20)))  # October: doesn't count
    db_session.add(_usage(user, counts=False))  # a tool round: not an input
    await db_session.commit()
    await _accept(db_session, user, agent_session)
    agent_session.busy_message_id = None
    db_session.add(_usage(user))
    await db_session.commit()
    with pytest.raises(limits.Refusal) as refused:
        await _accept(db_session, user, agent_session)
    assert (refused.value.reason, refused.value.resets_on) == ("user_limit", "2026-12-01")


async def test_default_limit_applies_when_the_users_is_blank(db_session, user, agent_session):
    user.agent_enabled_for_user = True
    await db_session.commit()
    with pytest.raises(limits.Refusal) as refused:
        await _accept(db_session, user, agent_session, _effective(default_user_monthly_inputs=0))
    assert refused.value.reason == "user_limit"


async def test_global_cap(db_session, user, agent_session):
    user.agent_enabled_for_user = True
    other = User(id=uuid.uuid4(), username="other")
    db_session.add(other)
    await db_session.flush()
    db_session.add(_usage(other, cost="9.99"))
    await db_session.commit()
    assert await limits.global_cap_reached(db_session, _effective(), NOW) is False
    db_session.add(_usage(other, cost="0.01", counts=False))
    await db_session.commit()
    assert await limits.global_cap_reached(db_session, _effective(), NOW) is True
    with pytest.raises(limits.Refusal) as refused:
        await _accept(db_session, user, agent_session)
    assert (refused.value.reason, refused.value.resets_on) == ("global_cap", "2026-12-01")
    assert await limits.spend_this_month(db_session, NOW) == Decimal("10.00")


async def test_busy_session_is_refused(db_session, user, agent_session):
    user.agent_enabled_for_user = True
    await db_session.commit()
    await _accept(db_session, user, agent_session)
    with pytest.raises(limits.Busy):
        await _accept(db_session, user, agent_session)


async def test_accepted_message_is_stored_with_the_open_architecture(db_session, user,
                                                                     agent_session):
    arch = uuid.uuid4()
    message = await limits.accept_message(db_session, user, agent_session, "cost?", arch,
                                          _effective(), NOW, usable=True)
    stored = (await db_session.execute(select(AgentMessage))).scalar_one()
    assert (stored.id, stored.content, stored.architecture_id, stored.status, stored.seq) == (
        message.id, "cost?", arch, "accepted", 1
    )
    await db_session.refresh(agent_session)
    assert agent_session.busy_message_id == message.id


async def test_status_reports_preview_and_limits(db_session, user):
    status = await limits.status(db_session, user, _effective(), NOW, usable=True)
    assert (status.available, status.on_preview, status.preview_inputs_left) == (True, True, 3)
    user.agent_preview_input_counter = 0
    await db_session.commit()
    status = await limits.status(db_session, user, _effective(), NOW, usable=True)
    assert (status.available, status.reason) == (False, "preview_used")

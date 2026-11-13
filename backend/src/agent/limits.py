"""Access, the free preview and usage limits (023-agent-foundation, research R6, FR-019–FR-023,
constitution Principle VIII).

A user message is accepted in one transaction that locks the user's row, so two tabs can't both
spend the last input. The checks, in order: a named, active user; the agent on and usable; the
agent on for this user or preview inputs left; the user's monthly input limit; the global
monthly spending cap. "Month" is the UTC calendar month; limits reset on the 1st. A refusal
says why only (clarification 4), with the reset date for the two monthly limits.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.settings_service import EffectiveAgentSettings
from src.models.orm import AgentMessage, AgentSession, AgentUsage, User


class Refusal(Exception):
    def __init__(self, reason: str, resets_on: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.resets_on = resets_on


class Busy(Exception):
    """A message in this session is still being answered."""


@dataclass(frozen=True)
class Status:
    available: bool
    reason: str | None = None
    resets_on: str | None = None
    on_preview: bool = False
    preview_inputs_left: int = 0


def month_start(now: datetime) -> datetime:
    now = now.astimezone(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def resets_on(now: datetime) -> str:
    start = month_start(now)
    year, month = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    return f"{year:04d}-{month:02d}-01"


async def inputs_this_month(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> int:
    return (await db.execute(
        select(func.count(AgentUsage.id)).where(
            AgentUsage.user_id == user_id,
            AgentUsage.counts_as_input.is_(True),
            AgentUsage.created_at >= month_start(now),
        )
    )).scalar_one()


async def spend_this_month(db: AsyncSession, now: datetime) -> Decimal:
    total = (await db.execute(
        select(func.coalesce(func.sum(AgentUsage.cost_usd), 0)).where(
            AgentUsage.created_at >= month_start(now)
        )
    )).scalar_one()
    return Decimal(total).quantize(Decimal("0.01"))


async def global_cap_reached(db: AsyncSession, effective: EffectiveAgentSettings,
                             now: datetime) -> bool:
    return await spend_this_month(db, now) >= effective.global_monthly_cap_usd


def effective_limit(user: User, effective: EffectiveAgentSettings) -> int:
    if user.agent_monthly_input_limit is not None:
        return user.agent_monthly_input_limit
    return effective.default_user_monthly_inputs


async def _check(db: AsyncSession, user: User, effective: EffectiveAgentSettings,
                 now: datetime, usable: bool) -> bool:
    """Raises `Refusal`, or returns whether the next input is a preview input."""
    if user.username is None:
        raise Refusal("guest")
    if not user.is_active:
        raise Refusal("agent_off")
    if not effective.enabled:
        raise Refusal("agent_off")
    if not usable:
        raise Refusal("unavailable")
    on_preview = not user.agent_enabled_for_user
    if on_preview and user.agent_preview_input_counter <= 0:
        raise Refusal("preview_used")
    if await inputs_this_month(db, user.id, now) >= effective_limit(user, effective):
        raise Refusal("user_limit", resets_on(now))
    if await global_cap_reached(db, effective, now):
        raise Refusal("global_cap", resets_on(now))
    return on_preview


async def status(db: AsyncSession, user: User, effective: EffectiveAgentSettings,
                 now: datetime, *, usable: bool) -> Status:
    on_preview = not user.agent_enabled_for_user
    left = user.agent_preview_input_counter if on_preview else 0
    try:
        await _check(db, user, effective, now, usable)
    except Refusal as refusal:
        return Status(False, refusal.reason, refusal.resets_on, on_preview, left)
    return Status(True, None, None, on_preview, left)


async def accept_message(db: AsyncSession, user: User, agent_session: AgentSession,
                         content: str, architecture_id: uuid.UUID | None,
                         effective: EffectiveAgentSettings, now: datetime, *,
                         usable: bool) -> AgentMessage:
    """Check everything and record the input, all under a lock on the user's row."""
    locked = (await db.execute(
        select(User).where(User.id == user.id).with_for_update().execution_options(
            populate_existing=True)
    )).scalar_one()
    session = (await db.execute(
        select(AgentSession).where(AgentSession.id == agent_session.id)
        .execution_options(populate_existing=True)
    )).scalar_one()
    if session.busy_message_id is not None:
        await db.rollback()
        raise Busy()
    try:
        on_preview = await _check(db, locked, effective, now, usable)
    except Refusal:
        await db.rollback()
        raise
    if on_preview:
        locked.agent_preview_input_counter -= 1
    seq = (await db.execute(
        select(func.coalesce(func.max(AgentMessage.seq), 0))
        .where(AgentMessage.session_id == session.id)
    )).scalar_one() + 1
    message = AgentMessage(session_id=session.id, seq=seq, role="user", content=content,
                           architecture_id=architecture_id, status="accepted",
                           is_preview=on_preview)
    db.add(message)
    await db.flush()
    session.busy_message_id = message.id
    await db.commit()
    return message

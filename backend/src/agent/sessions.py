"""Agent sessions (023-agent-foundation, FR-010–FR-013, research R4).

One session per user, closed and deleted 3 days after it starts. Expiry is enforced on every
agent request (an expired session is deleted and treated as absent) and by a background sweep,
so a conversation never outlives its 3 days even if the user never comes back. Deleting a
session deletes its messages and activity log; usage records stay (their session is set to
null).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import AgentMessage, AgentOperation, AgentResult, AgentSession, User

SESSION_LIFETIME = timedelta(days=3)


class SessionExists(Exception):
    """A session is open and the caller didn't confirm replacing it."""


async def current_session(db: AsyncSession, user: User, now: datetime) -> AgentSession | None:
    session = (await db.execute(
        select(AgentSession).where(AgentSession.user_id == user.id)
    )).scalar_one_or_none()
    if session is not None and session.closes_at <= now:
        await db.delete(session)
        await db.commit()
        return None
    return session


async def start_session(db: AsyncSession, user: User, now: datetime, *,
                        replace: bool) -> AgentSession:
    existing = await current_session(db, user, now)
    if existing is not None:
        if not replace:
            raise SessionExists()
        await db.delete(existing)
        await db.flush()
    session = AgentSession(user_id=user.id, started_at=now, closes_at=now + SESSION_LIFETIME)
    db.add(session)
    await db.commit()
    return session


async def messages(db: AsyncSession, session: AgentSession) -> list[AgentMessage]:
    return list((await db.execute(
        select(AgentMessage).where(AgentMessage.session_id == session.id)
        .order_by(AgentMessage.seq)
    )).scalars().all())


async def results(db: AsyncSession, session: AgentSession) -> list[AgentResult]:
    """024: the session's comparison results in order."""
    return list((await db.execute(
        select(AgentResult).where(AgentResult.session_id == session.id)
        .order_by(AgentResult.seq)
    )).scalars().all())


def result_ids_by_message(messages: list[AgentMessage],
                          results: list[AgentResult]) -> dict:
    """024: which message shows each result's card. A result belongs to the user message whose
    answer made it; its card goes on the agent message that answered that question (the next
    agent message, unless another answered question comes first), else on the question itself
    (a failed answer)."""
    by_question: dict = {}
    for result in results:
        by_question.setdefault(result.message_id, []).append(result.id)
    ordered = sorted(messages, key=lambda m: m.seq)
    shown: dict = {}
    for index, message in enumerate(ordered):
        if message.id not in by_question:
            continue
        target = message
        for later in ordered[index + 1:]:
            if later.role == "agent":
                target = later
                break
            if later.status == "answered":
                break
        shown.setdefault(target.id, []).extend(by_question[message.id])
    return shown


async def operations(db: AsyncSession, session: AgentSession) -> list[AgentOperation]:
    return list((await db.execute(
        select(AgentOperation).join(AgentMessage, AgentOperation.message_id == AgentMessage.id)
        .where(AgentOperation.session_id == session.id)
        .order_by(AgentMessage.seq, AgentOperation.seq)
    )).scalars().all())


async def sweep_expired(db: AsyncSession, now: datetime) -> int:
    """Delete every session past its close time; returns how many."""
    result = await db.execute(delete(AgentSession).where(AgentSession.closes_at <= now))
    await db.commit()
    return result.rowcount or 0


async def clear_busy(db: AsyncSession) -> None:
    """At startup: no answer survives a restart, so no session is still busy."""
    await db.execute(update(AgentSession).values(busy_message_id=None))
    await db.commit()

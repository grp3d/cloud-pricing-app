"""Test helpers for translation (026): a user with an agent session and a message, an operation
context, earlier-message log entries, and reading a translation's rows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from src.agent.figures import FigureBook
from src.agent.operations import OperationContext
from src.models.orm import AgentMessage, AgentOperation, AgentSession, User

WEB_APP = "Active-Standby Multi-Region Web Application"
LAKE = "Modern Data Lake & ETL Analytics Pipeline"
SERVERLESS = "Serverless Microservices Back-End"
EKS = "Containerized Microservices Platform (EKS)"
STANDARD = (WEB_APP, LAKE, SERVERLESS, EKS)


async def make_world(db) -> tuple:
    """(db, user, agent session, message), committed."""
    user = User(id=uuid.uuid4(), username=f"t-{uuid.uuid4().hex[:6]}",
                agent_preview_input_counter=0)
    db.add(user)
    await db.flush()
    now = datetime.now(UTC)
    agent_session = AgentSession(user_id=user.id, started_at=now,
                                 closes_at=now + timedelta(days=3))
    db.add(agent_session)
    await db.flush()
    message = await add_message(db, agent_session, 1)
    await db.commit()
    return db, user, agent_session, message


async def add_message(db, agent_session, seq: int) -> AgentMessage:
    message = AgentMessage(session_id=agent_session.id, seq=seq, role="user", content="q",
                           status="accepted")
    db.add(message)
    await db.flush()
    return message


def context(world, architecture_id=None, message=None) -> OperationContext:
    db, user, agent_session, first = world
    return OperationContext(session=db, user=user, open_architecture_id=architecture_id,
                            figures=FigureBook(), agent_session=agent_session,
                            message=message or first)


async def log_operation(db, ctx: OperationContext, name: str, result) -> None:
    """Record an operation's summary as the loop does (the activity log)."""
    db.add(AgentOperation(session_id=ctx.agent_session.id, message_id=ctx.message.id, seq=1,
                          name=name, inputs={}, outcome="ok", summary=result.summary,
                          started_at=datetime.now(UTC), duration_ms=0))
    await db.commit()


def rows_by_label(record: dict) -> dict[tuple[str, str], dict]:
    return {(r["where"], r["source"]["label"]): r for r in record["rows"]}


def one_row_per_service(record: dict, detail) -> None:
    services = (sum(len(c.sku_selections) for c in detail.collections)
                + sum(1 for k in detail.connectors if k.sku_selection is not None))
    assert len(record["rows"]) == services

"""`/agent/*` — the agent panel's routes (023-agent-foundation, contracts/agent-api.md).

Named users only (FR-001); guests get `403`. A message is checked and its input recorded before
anything is streamed (research R6); refusals are plain JSON (`423` with the reason, `409` when
busy). The answer then streams as server-sent events, one JSON event per `data:` line (research
R3), from its own database session, since it outlives the request's.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from src.agent import limits, sessions
from src.agent import results as agent_results
from src.agent.loop import LoopContext, answer
from src.agent.model import AgentUnavailable, build_client
from src.agent.settings_service import EffectiveAgentSettings, effective_settings
from src.api.deps import CurrentUser, DbSession, SessionFactory
from src.logging_config import get_logger
from src.models.orm import AgentMessage, AgentResult, AgentSession, User
from src.models.schemas import (
    AgentAcceptedEvent,
    AgentErrorEvent,
    AgentMessageCreate,
    AgentMessageOut,
    AgentOperationOut,
    AgentRefusalOut,
    AgentSessionCreate,
    AgentSessionDetailOut,
    AgentSessionOut,
    AgentStatusOut,
    AgentStreamEnvelope,
)

router = APIRouter(prefix="/agent", tags=["agent"])
logger = get_logger("cloud_pricing.agent")

_STREAM_RESPONSES = {
    200: {
        "model": AgentStreamEnvelope,
        "description": "Server-sent events: one `AgentStreamEnvelope.data` object per line.",
        "content": {"text/event-stream": {
            "schema": {"$ref": "#/components/schemas/AgentStreamEnvelope"}
        }},
    },
    409: {"description": "`busy` (or, for retry, the message isn't failed)"},
    423: {"model": AgentRefusalOut, "description": "Not accepted; no model call was made."},
}


def _now() -> datetime:
    return datetime.now(UTC)


def _require_named(user: User) -> None:
    if user.username is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="guest")


def _usable(effective: EffectiveAgentSettings) -> bool:
    try:
        build_client(effective)
    except AgentUnavailable:
        return False
    return True


async def _session_or_404(db, user: User) -> AgentSession:
    agent_session = await sessions.current_session(db, user, _now())
    if agent_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_session")
    return agent_session


@router.get("/status", response_model=AgentStatusOut)
async def agent_status(session: DbSession, user: CurrentUser) -> AgentStatusOut:
    effective = await effective_settings(session)
    if user.username is None:
        return AgentStatusOut(enabled=False, available=False, reason="guest")
    current = await limits.status(session, user, effective, _now(),
                                  usable=_usable(effective))
    agent_session = await sessions.current_session(session, user, _now())
    return AgentStatusOut(
        enabled=effective.enabled,
        available=current.available,
        reason=current.reason,
        resets_on=current.resets_on,
        on_preview=current.on_preview,
        preview_inputs_left=current.preview_inputs_left,
        session=AgentSessionOut.model_validate(agent_session) if agent_session else None,
    )


@router.post("/session", response_model=AgentSessionOut, status_code=201)
async def start_agent_session(
    body: AgentSessionCreate, session: DbSession, user: CurrentUser
) -> AgentSessionOut:
    _require_named(user)
    try:
        agent_session = await sessions.start_session(session, user, _now(), replace=body.replace)
    except sessions.SessionExists as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="session_exists") from exc
    return AgentSessionOut.model_validate(agent_session)


@router.get("/session", response_model=AgentSessionDetailOut)
async def get_agent_session(session: DbSession, user: CurrentUser) -> AgentSessionDetailOut:
    _require_named(user)
    agent_session = await _session_or_404(session, user)
    messages = await sessions.messages(session, agent_session)
    results = await sessions.results(session, agent_session)
    shown = sessions.result_ids_by_message(messages, results)
    return AgentSessionDetailOut(
        id=agent_session.id,
        started_at=agent_session.started_at,
        closes_at=agent_session.closes_at,
        messages=[AgentMessageOut.model_validate(m).model_copy(
            update={"result_ids": shown.get(m.id, [])}) for m in messages],
        results=[agent_results.to_out(r) for r in results],
    )


@router.get(
    "/session/results/{result_id}/csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}},
                     "description": "The result as CSV (024, FR-020): a basis block, then the "
                     "rows and totals shown."}},
)
async def get_agent_result_csv(result_id: uuid.UUID, session: DbSession,
                               user: CurrentUser) -> Response:
    """024: download one result of the caller's open session; another user's or an expired
    session's result is 404 (FR-021)."""
    _require_named(user)
    agent_session = await _session_or_404(session, user)
    result = await session.get(AgentResult, result_id)
    if result is None or result.session_id != agent_session.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_result")
    out = agent_results.to_out(result)
    return Response(
        content=agent_results.write_csv(out).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="{agent_results.csv_filename(out)}"'},
    )


@router.get("/session/operations", response_model=list[AgentOperationOut])
async def get_agent_operations(session: DbSession, user: CurrentUser) -> list[AgentOperationOut]:
    _require_named(user)
    agent_session = await _session_or_404(session, user)
    return [AgentOperationOut.model_validate(o)
            for o in await sessions.operations(session, agent_session)]


def _refused(refusal: limits.Refusal) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_423_LOCKED,
        detail=AgentRefusalOut(reason=refusal.reason, resets_on=refusal.resets_on).model_dump(),
    )


def _sse(event: BaseModel) -> str:
    return f"data: {event.model_dump_json()}\n\n"


# Answers in progress. Each runs as its own task, apart from the HTTP stream that relays its
# events: the request-logging middleware cancels the app's work when the browser closes the
# stream (which it does as soon as it has "done"), and that must never cut an answer, or the
# cleanup that clears the session's busy flag, short. Held here so a task can't be
# garbage-collected mid-run.
_answers: set[asyncio.Task] = set()
_END = object()


def _stream(factory, user_id: uuid.UUID, session_id: uuid.UUID, message_id: uuid.UUID,
            *, charge_input: bool) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()

    async def run() -> None:
        async with factory() as db:
            try:
                user = await db.get(User, user_id)
                agent_session = await db.get(AgentSession, session_id)
                message = await db.get(AgentMessage, message_id)
                effective = await effective_settings(db)
                queue.put_nowait(_sse(AgentAcceptedEvent(
                    message_id=message.id, is_preview=message.is_preview,
                    preview_inputs_left=user.agent_preview_input_counter,
                )))

                async def cap_reached() -> bool:
                    return await limits.global_cap_reached(db, effective, _now())

                try:
                    client = build_client(effective)
                except AgentUnavailable:
                    message.status, message.error_kind = "failed", "failed"
                    await db.commit()
                    queue.put_nowait(_sse(AgentErrorEvent(
                        kind="failed", message="The agent is unavailable.")))
                    return
                context = LoopContext(session=db, user=user, agent_session=agent_session,
                                      user_message=message, client=client, effective=effective,
                                      charge_input=charge_input, cap_reached=cap_reached)
                async for event in answer(context):
                    queue.put_nowait(_sse(event))
            except Exception as exc:  # noqa: BLE001
                logger.exception("agent answer task failed", error=str(exc))
            finally:
                try:
                    await db.rollback()
                    message = await db.get(AgentMessage, message_id, populate_existing=True)
                    if message is not None and message.status == "accepted":
                        message.status, message.error_kind = "failed", "failed"
                    busy = await db.get(AgentSession, session_id, populate_existing=True)
                    if busy is not None and busy.busy_message_id == message_id:
                        busy.busy_message_id = None
                    await db.commit()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("agent busy flag not cleared", error=str(exc))
                queue.put_nowait(_END)

    task = asyncio.create_task(run())
    _answers.add(task)
    task.add_done_callback(_answers.discard)

    async def events() -> AsyncIterator[str]:
        while (item := await queue.get()) is not _END:
            yield item

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/session/messages", responses=_STREAM_RESPONSES, response_class=StreamingResponse)
async def send_agent_message(
    body: AgentMessageCreate, session: DbSession, factory: SessionFactory, user: CurrentUser
):
    _require_named(user)
    agent_session = await _session_or_404(session, user)
    effective = await effective_settings(session)
    try:
        message = await limits.accept_message(
            session, user, agent_session, body.content, body.architecture_id, effective, _now(),
            usable=_usable(effective),
        )
    except limits.Refusal as refusal:
        raise _refused(refusal) from refusal
    except limits.Busy as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="busy") from exc
    return _stream(factory, user.id, agent_session.id, message.id, charge_input=True)


@router.post("/session/messages/{message_id}/retry", responses=_STREAM_RESPONSES,
             response_class=StreamingResponse)
async def retry_agent_message(
    message_id: uuid.UUID, session: DbSession, factory: SessionFactory, user: CurrentUser
):
    """Re-run a failed message. No new input is charged (research R6); the agent must still be
    on and usable, and the global cap is checked before each model call."""
    _require_named(user)
    agent_session = await _session_or_404(session, user)
    message = await session.get(AgentMessage, message_id)
    if (message is None or message.session_id != agent_session.id or message.role != "user"
            or message.status != "failed"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="not_failed")
    effective = await effective_settings(session)
    if not effective.enabled:
        raise _refused(limits.Refusal("agent_off"))
    if not _usable(effective):
        raise _refused(limits.Refusal("unavailable"))
    if await limits.global_cap_reached(session, effective, _now()):
        raise _refused(limits.Refusal("global_cap", limits.resets_on(_now())))
    if agent_session.busy_message_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="busy")
    agent_session.busy_message_id = message.id
    message.status, message.error_kind = "accepted", None
    await session.commit()
    return _stream(factory, user.id, agent_session.id, message.id, charge_input=False)

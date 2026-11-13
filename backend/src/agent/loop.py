"""The agent loop (023-agent-foundation, contracts/agent-internals.md "Agent loop", research R2,
R10, R11).

For one accepted user message: send the conversation to the model; run any operations it asks
for and send back the results; repeat up to `MAX_ROUNDS` model calls; stream the answer through
the figure filter (research R1) and add the app's footer (FR-005a). Every model call is
preceded by the session-close and global-cap checks, runs under the timeout setting, and
records one usage row (research R6, R7). Any failure ends with one `error` event and leaves the
user message `failed`, so Retry can re-run it without a new input charge.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent import operations as ops
from src.agent.figures import FigureBook, FigureStreamFilter, footer
from src.agent.model import (
    ModelClient,
    ModelError,
    ModelMessage,
    ModelTimeout,
    TextDelta,
    ToolCall,
    Usage,
)
from src.agent.prompt import SYSTEM_PROMPT, user_turn
from src.agent.settings_service import EffectiveAgentSettings
from src.logging_config import get_logger
from src.models.orm import AgentMessage, AgentOperation, AgentSession, AgentUsage, User
from src.models.schemas import (
    AgentDoneEvent,
    AgentErrorEvent,
    AgentOperationEvent,
    AgentStatusEvent,
    AgentTextEvent,
)

logger = get_logger("cloud_pricing.agent")

MAX_ROUNDS = 6
HISTORY_MESSAGES = 20

ERROR_MESSAGES = {
    "timeout": "The agent took too long to answer.",
    "unreachable": "The agent's model can't be reached right now.",
    "bad_output": "The agent's model gave an answer the app couldn't use.",
    "failed": "The agent couldn't answer.",
    "session_closed": "This session has reached its close time.",
    "global_cap": "The agent has reached its monthly limit.",
}


async def _never() -> bool:
    return False


@dataclass
class LoopContext:
    session: AsyncSession
    user: User
    agent_session: AgentSession
    user_message: AgentMessage
    client: ModelClient
    effective: EffectiveAgentSettings
    registry: ops.Registry = field(default_factory=lambda: ops.registry)
    # False on a retry: the input was charged when the message was first accepted.
    charge_input: bool = True
    # Returns True once the global monthly cap is reached (checked before every model call).
    cap_reached: Callable[[], Awaitable[bool]] = _never
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))


class _Stop(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


def _cost(effective: EffectiveAgentSettings, provider: str, usage: Usage) -> Decimal:
    if provider != "anthropic":
        return Decimal(0)
    rate_in = effective.price_per_input_token_usd or Decimal(0)
    rate_out = effective.price_per_output_token_usd or Decimal(0)
    return usage.input_tokens * rate_in + usage.output_tokens * rate_out


async def _history(ctx: LoopContext) -> list[ModelMessage]:
    rows = (await ctx.session.execute(
        select(AgentMessage)
        .where(AgentMessage.session_id == ctx.agent_session.id,
               AgentMessage.seq < ctx.user_message.seq,
               AgentMessage.status.in_(("answered", "complete")))
        .order_by(AgentMessage.seq.desc())
        .limit(HISTORY_MESSAGES)
    )).scalars().all()
    history = []
    for row in reversed(rows):
        if row.role == "user":
            arch = str(row.architecture_id) if row.architecture_id else None
            history.append(ModelMessage(role="user", text=user_turn(row.content, arch)))
        else:
            history.append(ModelMessage(role="assistant", text=row.content))
    return history


async def _next_seq(ctx: LoopContext) -> int:
    current = (await ctx.session.execute(
        select(func.max(AgentMessage.seq)).where(AgentMessage.session_id == ctx.agent_session.id)
    )).scalar_one()
    return (current or 0) + 1


class _Round:
    def __init__(self) -> None:
        self.text = ""
        self.tool_calls: list[ToolCall] = []
        self.usage = Usage(0, 0)


async def answer(ctx: LoopContext) -> AsyncIterator:
    """Yields the stream events (after `accepted`, which the route sends)."""
    yield AgentStatusEvent(state="thinking")
    message_id = ctx.user_message.id
    figures = FigureBook()
    stream = FigureStreamFilter(figures)
    shown: list[str] = []
    op_seq = 0
    counted = not ctx.charge_input
    op_context = ops.OperationContext(
        session=ctx.session, user=ctx.user,
        open_architecture_id=ctx.user_message.architecture_id, figures=figures,
    )
    arch = str(ctx.user_message.architecture_id) if ctx.user_message.architecture_id else None
    conversation = [*await _history(ctx),
                    ModelMessage(role="user", text=user_turn(ctx.user_message.content, arch))]
    tools = ctx.registry.tool_specs()

    try:
        writing = False
        for _round_number in range(MAX_ROUNDS):
            if ctx.now() >= ctx.agent_session.closes_at:
                raise _Stop("session_closed")
            if await ctx.cap_reached():
                raise _Stop("global_cap")

            this = _Round()
            iterator = ctx.client.stream(SYSTEM_PROMPT, conversation, tools).__aiter__()
            deadline = asyncio.get_running_loop().time() + ctx.effective.timeout_seconds
            try:
                while True:
                    try:
                        async with asyncio.timeout_at(deadline):
                            event = await anext(iterator)
                    except StopAsyncIteration:
                        break
                    except TimeoutError as exc:
                        raise ModelTimeout("timed out") from exc
                    if isinstance(event, TextDelta):
                        this.text += event.text
                        out = stream.feed(event.text)
                        if out:
                            if not writing:
                                writing = True
                                yield AgentStatusEvent(state="writing")
                            shown.append(out)
                            yield AgentTextEvent(delta=out)
                    elif isinstance(event, ToolCall):
                        this.tool_calls.append(event)
                    elif isinstance(event, Usage):
                        this.usage = event
            finally:
                await iterator.aclose()

            ctx.session.add(AgentUsage(
                user_id=ctx.user.id, session_id=ctx.agent_session.id,
                message_id=ctx.user_message.id, provider=ctx.client.provider,
                model=ctx.client.model, input_tokens=this.usage.input_tokens,
                output_tokens=this.usage.output_tokens,
                cost_usd=_cost(ctx.effective, ctx.client.provider, this.usage),
                counts_as_input=not counted, is_preview=ctx.user_message.is_preview,
            ))
            counted = True
            await ctx.session.commit()

            if not this.tool_calls:
                break

            conversation.append(
                ModelMessage(role="assistant", text=this.text, tool_calls=this.tool_calls)
            )
            for call in this.tool_calls:
                yield AgentStatusEvent(state="running_operation")
                op_seq += 1
                started = datetime.now(UTC)
                clock = time.perf_counter()
                snapshot = None
                try:
                    result = await ctx.registry.run(op_context, call.name, call.arguments)
                    outcome, summary, snapshot = "ok", result.summary, result.snapshot
                    content, is_error = json.dumps(result.data, default=str), False
                except ops.ToolError as exc:
                    outcome, summary = "error", {"error": str(exc)}
                    content, is_error = json.dumps({"error": str(exc)}), True
                except Exception:
                    logger.exception("agent operation failed", operation=call.name)
                    outcome, summary = "error", {"error": "the operation failed"}
                    content, is_error = json.dumps(summary), True
                ctx.session.add(AgentOperation(
                    session_id=ctx.agent_session.id, message_id=ctx.user_message.id,
                    seq=op_seq, name=call.name[:100], inputs=call.arguments or {},
                    outcome=outcome, summary=summary, snapshot=snapshot, started_at=started,
                    duration_ms=int((time.perf_counter() - clock) * 1000),
                ))
                await ctx.session.commit()
                yield AgentOperationEvent(name=call.name, inputs=call.arguments or {},
                                          outcome=outcome, summary=summary, snapshot=snapshot)
                conversation.append(ModelMessage(
                    role="tool", text=content, tool_call_id=call.id, tool_name=call.name,
                    is_error=is_error,
                ))
        else:
            raise _Stop("bad_output")

        tail = stream.flush()
        if tail:
            shown.append(tail)
            yield AgentTextEvent(delta=tail)
        note = footer(figures, stream.used)
        if note:
            note = f"\n\n{note}"
            shown.append(note)
            yield AgentTextEvent(delta=note)
        if stream.removed:
            op_seq += 1
            ctx.session.add(AgentOperation(
                session_id=ctx.agent_session.id, message_id=ctx.user_message.id, seq=op_seq,
                name="figure_check", inputs={}, outcome="ok",
                summary={"figures_removed": stream.removed}, figures_removed=stream.removed,
                started_at=datetime.now(UTC), duration_ms=0,
            ))

        agent_message = AgentMessage(
            session_id=ctx.agent_session.id, seq=await _next_seq(ctx), role="agent",
            content="".join(shown), status="complete",
            architecture_id=ctx.user_message.architecture_id,
        )
        ctx.session.add(agent_message)
        ctx.user_message.status = "answered"
        ctx.user_message.error_kind = None
        await ctx.session.commit()
        yield AgentDoneEvent(agent_message_id=agent_message.id)
    except (_Stop, ModelError) as exc:
        kind = exc.kind
        await _fail(ctx, message_id, kind)
        yield AgentErrorEvent(kind=kind, message=ERROR_MESSAGES[kind])
    except Exception:
        logger.exception("agent answer failed")
        await _fail(ctx, message_id, "failed")
        yield AgentErrorEvent(kind="failed", message=ERROR_MESSAGES["failed"])


async def _fail(ctx: LoopContext, message_id, kind: str) -> None:
    await ctx.session.rollback()
    message = await ctx.session.get(AgentMessage, message_id)
    if message is not None:
        message.status = "failed"
        message.error_kind = kind
        await ctx.session.commit()

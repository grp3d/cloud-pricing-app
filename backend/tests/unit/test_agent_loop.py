"""The agent loop (023, contracts/agent-internals.md "Agent loop"), with the scripted model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from src.agent.clients.scripted import ScriptedModelClient, Turn
from src.agent.loop import MAX_ROUNDS, LoopContext, answer
from src.agent.model import ModelUnreachable, ToolCall, Usage
from src.agent.operations import OperationContext, OperationResult, Registry, ToolError
from src.agent.settings_service import EffectiveAgentSettings
from src.models.orm import AgentMessage, AgentOperation, AgentSession, AgentUsage, User
from src.models.schemas import (
    AgentErrorEvent,
    AgentOperationEvent,
    AgentStatusEvent,
    AgentTextEvent,
)

SNAP = {"aws": {"date": "2026-11-02", "revision": 2}}


class NoArgs(BaseModel):
    pass


def _registry(calls: list) -> Registry:
    registry = Registry()

    @registry.operation("total", "The total.", NoArgs)
    async def total(ctx: OperationContext, args: NoArgs) -> OperationResult:
        calls.append(ctx.open_architecture_id)
        ref = ctx.figures.add(Decimal("1780.955"), "total", duration="1_month", snapshot=SNAP)
        return OperationResult(data={"total": ref}, summary={"total": "1780.955"},
                               snapshot=SNAP)

    @registry.operation("broken", "Fails.", NoArgs)
    async def broken(ctx: OperationContext, args: NoArgs) -> OperationResult:
        raise ToolError("nothing to price")

    @registry.operation("crash", "Crashes.", NoArgs)
    async def crash(ctx: OperationContext, args: NoArgs) -> OperationResult:
        raise RuntimeError("bug")

    return registry


def _effective(**overrides) -> EffectiveAgentSettings:
    values = {"enabled": True, "provider": "ollama", "model": "m", "base_url": "http://x",
              "timeout_seconds": 60, "global_monthly_cap_usd": Decimal("10"),
              "default_user_monthly_inputs": 100, "price_per_input_token_usd": None,
              "price_per_output_token_usd": None}
    values.update(overrides)
    return EffectiveAgentSettings(**values)


@pytest.fixture
async def setup(db_session):
    user = User(id=uuid.uuid4(), username=f"u-{uuid.uuid4().hex[:6]}")
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(UTC)
    agent_session = AgentSession(user_id=user.id, started_at=now,
                                 closes_at=now + timedelta(days=3))
    db_session.add(agent_session)
    await db_session.flush()
    arch = uuid.uuid4()
    message = AgentMessage(session_id=agent_session.id, seq=1, role="user",
                           content="What does it cost?", status="accepted",
                           architecture_id=arch, is_preview=True)
    db_session.add(message)
    await db_session.commit()
    return db_session, user, agent_session, message, arch


def _ctx(setup, client, registry, **kw) -> LoopContext:
    db, user, agent_session, message, _arch = setup
    return LoopContext(session=db, user=user, agent_session=agent_session, user_message=message,
                       client=client, effective=kw.pop("effective", _effective()),
                       registry=registry, charge_input=kw.pop("charge_input", True), **kw)


async def _run(ctx) -> list:
    return [e async for e in answer(ctx)]


def _text(events) -> str:
    return "".join(e.delta for e in events if isinstance(e, AgentTextEvent))


async def test_text_only_answer_streams_and_is_stored(setup):
    db, user, agent_session, message, _ = setup
    client = ScriptedModelClient([Turn(text=["It has ", "two collections."], usage=Usage(9, 4))])
    events = await _run(_ctx(setup, client, _registry([])))
    assert isinstance(events[0], AgentStatusEvent) and events[0].state == "thinking"
    assert _text(events) == "It has two collections."
    assert events[-1].event == "done"
    stored = (await db.execute(select(AgentMessage).where(AgentMessage.role == "agent"))
              ).scalar_one()
    assert stored.content == "It has two collections."
    await db.refresh(message)
    assert message.status == "answered"


async def test_tool_call_runs_the_operation_with_the_open_architecture(setup):
    db, user, agent_session, message, arch = setup
    calls: list = []
    client = ScriptedModelClient([
        Turn(tool_calls=[ToolCall("c1", "total", {})], usage=Usage(10, 2)),
        Turn(text=["The total is [[F1]]."], usage=Usage(20, 5)),
    ])
    events = await _run(_ctx(setup, client, _registry(calls)))
    assert calls == [arch]
    ops = [e for e in events if isinstance(e, AgentOperationEvent)]
    assert [(o.name, o.outcome) for o in ops] == [("total", "ok")]
    assert _text(events) == (
        "The total is $1,780.96.\n\nPrices for 1 month (31 days), snapshot 2026-11-02 r2"
    )
    logged = (await db.execute(select(AgentOperation))).scalars().all()
    assert [(o.name, o.outcome, o.snapshot) for o in logged] == [("total", "ok", SNAP)]
    # The tool result went back to the model as data.
    second_call = client.calls[1]
    assert second_call.messages[-1].role == "tool"
    assert '"total": "F1"' in second_call.messages[-1].text


async def test_one_usage_row_per_call_and_only_the_first_counts_as_the_input(setup):
    db, *_ = setup
    client = ScriptedModelClient([
        Turn(tool_calls=[ToolCall("c1", "total", {})], usage=Usage(10, 2)),
        Turn(text=["Done."], usage=Usage(20, 5)),
    ])
    await _run(_ctx(setup, client, _registry([])))
    rows = (await db.execute(select(AgentUsage).order_by(AgentUsage.created_at))).scalars().all()
    assert [(r.input_tokens, r.output_tokens, r.counts_as_input, r.is_preview) for r in rows] == [
        (10, 2, True, True), (20, 5, False, True)
    ]
    assert all(r.cost_usd == 0 for r in rows)  # a local model costs $0


async def test_hosted_usage_is_costed_at_the_rates(setup):
    db, *_ = setup
    client = ScriptedModelClient([Turn(text=["Hi."], usage=Usage(1000, 200))])
    client.provider = "anthropic"
    effective = _effective(provider="anthropic", price_per_input_token_usd=Decimal("0.000001"),
                           price_per_output_token_usd=Decimal("0.000005"))
    await _run(_ctx(setup, client, _registry([]), effective=effective))
    row = (await db.execute(select(AgentUsage))).scalar_one()
    assert row.cost_usd == Decimal("0.002")


async def test_a_retry_charges_no_new_input(setup):
    db, *_ = setup
    client = ScriptedModelClient([Turn(text=["Hi."], usage=Usage(1, 1))])
    await _run(_ctx(setup, client, _registry([]), charge_input=False))
    row = (await db.execute(select(AgentUsage))).scalar_one()
    assert row.counts_as_input is False


async def test_the_model_sees_the_system_prompt_recent_history_and_the_new_message(setup):
    db, user, agent_session, message, arch = setup
    # 30 earlier exchanges: only the last 20 messages before this one are sent.
    message.seq = 100
    for i in range(30):
        db.add(AgentMessage(session_id=agent_session.id, seq=2 * i + 1, role="user",
                            content=f"q{i}", status="answered"))
        db.add(AgentMessage(session_id=agent_session.id, seq=2 * i + 2, role="agent",
                            content=f"a{i}", status="complete"))
    await db.commit()
    client = ScriptedModelClient([Turn(text=["ok"])])
    await _run(_ctx(setup, client, _registry([])))
    sent = client.calls[0].messages
    assert len(sent) == 21
    assert sent[0].text.endswith("q20") and sent[19].text == "a29"
    assert sent[-1].role == "user"
    assert str(arch) in sent[-1].text and sent[-1].text.endswith("What does it cost?")
    assert "Never write an amount" in client.calls[0].system


async def test_stops_after_the_maximum_rounds(setup):
    db, *_ = setup
    client = ScriptedModelClient(
        [Turn(tool_calls=[ToolCall(f"c{i}", "total", {})]) for i in range(MAX_ROUNDS)]
    )
    events = await _run(_ctx(setup, client, _registry([])))
    assert len(client.calls) == MAX_ROUNDS
    assert isinstance(events[-1], AgentErrorEvent)


async def test_model_written_amounts_are_removed_and_logged(setup):
    db, *_ = setup
    client = ScriptedModelClient([Turn(text=["I think it's $500.00 a month."])])
    events = await _run(_ctx(setup, client, _registry([])))
    assert _text(events) == "I think it's [figure removed] a month."
    check = (await db.execute(select(AgentOperation))).scalar_one()
    assert check.name == "figure_check" and check.figures_removed == 1


# --- failures (US4, T048) ---------------------------------------------------------------------


async def _failed(setup):
    db, user, agent_session, message, _ = setup
    await db.refresh(message)
    return message


async def test_timeout(setup):
    client = ScriptedModelClient([Turn(text=["late"], delay_seconds=2)])
    events = await _run(_ctx(setup, client, _registry([]),
                             effective=_effective(timeout_seconds=1)))
    assert isinstance(events[-1], AgentErrorEvent) and events[-1].kind == "timeout"
    message = await _failed(setup)
    assert (message.status, message.error_kind) == ("failed", "timeout")


async def test_unreachable(setup):
    client = ScriptedModelClient([Turn(raises=ModelUnreachable("down"))])
    events = await _run(_ctx(setup, client, _registry([])))
    assert events[-1].kind == "unreachable"
    assert (await _failed(setup)).status == "failed"


async def test_unknown_tool_is_reported_back_to_the_model(setup):
    db, *_ = setup
    client = ScriptedModelClient([
        Turn(tool_calls=[ToolCall("c1", "delete_everything", {})]),
        Turn(text=["I can't do that."]),
    ])
    events = await _run(_ctx(setup, client, _registry([])))
    ops = [e for e in events if isinstance(e, AgentOperationEvent)]
    assert ops[0].outcome == "error" and "unknown operation" in ops[0].summary["error"]
    assert client.calls[1].messages[-1].is_error
    assert events[-1].event == "done"


async def test_operation_errors_are_tool_errors(setup):
    client = ScriptedModelClient([
        Turn(tool_calls=[ToolCall("c1", "broken", {}), ToolCall("c2", "crash", {})]),
        Turn(text=["Sorry."]),
    ])
    events = await _run(_ctx(setup, client, _registry([])))
    ops = [e for e in events if isinstance(e, AgentOperationEvent)]
    assert [o.outcome for o in ops] == ["error", "error"]
    assert ops[0].summary["error"] == "nothing to price"
    assert ops[1].summary["error"] == "the operation failed"
    assert events[-1].event == "done"


async def test_session_close_time_stops_the_answer(setup):
    db, user, agent_session, message, _ = setup
    agent_session.closes_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.commit()
    client = ScriptedModelClient([Turn(text=["never"])])
    events = await _run(_ctx(setup, client, _registry([])))
    assert events[-1].kind == "session_closed"
    assert client.calls == []


async def test_cap_check_before_each_model_call(setup):
    client = ScriptedModelClient([
        Turn(tool_calls=[ToolCall("c1", "total", {})]),
        Turn(text=["never"]),
    ])
    checks = []

    async def cap_reached() -> bool:
        checks.append(1)
        return len(checks) > 1

    events = await _run(_ctx(setup, client, _registry([]), cap_reached=cap_reached))
    assert len(client.calls) == 1
    assert events[-1].kind == "global_cap"

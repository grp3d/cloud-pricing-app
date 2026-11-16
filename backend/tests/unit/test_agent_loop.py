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
    assert "architecture A is open" in sent[-1].text
    assert str(arch) not in sent[-1].text  # the model never sees, or repeats, the id
    assert sent[-1].text.endswith("What does it cost?")
    assert "Never write an amount" in client.calls[0].system


async def test_each_architecture_gets_a_label_in_the_order_it_was_opened(setup):
    db, user, agent_session, message, arch = setup
    other = uuid.uuid4()
    message.seq = 10
    db.add(AgentMessage(session_id=agent_session.id, seq=1, role="user", content="before",
                        status="answered", architecture_id=other))
    db.add(AgentMessage(session_id=agent_session.id, seq=2, role="agent", content="ok",
                        status="complete"))
    db.add(AgentMessage(session_id=agent_session.id, seq=3, role="user", content="none open",
                        status="answered"))
    db.add(AgentMessage(session_id=agent_session.id, seq=4, role="agent", content="ok",
                        status="complete"))
    await db.commit()
    client = ScriptedModelClient([Turn(text=["ok"])])
    await _run(_ctx(setup, client, _registry([])))
    sent = [m.text for m in client.calls[0].messages if m.role == "user"]
    assert sent[0].startswith("[App context: architecture A is open.")
    assert sent[1].startswith("[App context: no architecture is open.]")
    assert sent[2].startswith("[App context: architecture B is open.")


async def test_stops_after_the_maximum_rounds(setup):
    db, *_ = setup
    client = ScriptedModelClient(
        [Turn(tool_calls=[ToolCall(f"c{i}", "total", {})]) for i in range(MAX_ROUNDS)]
    )
    events = await _run(_ctx(setup, client, _registry([])))
    assert len(client.calls) == MAX_ROUNDS
    assert isinstance(events[-1], AgentErrorEvent) and events[-1].kind == "too_many_steps"
    db_message = (await db.execute(select(AgentMessage).where(AgentMessage.role == "user"))
                  ).scalar_one()
    assert db_message.error_kind == "too_many_steps"


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


async def test_an_operation_call_written_as_text_fails_and_is_not_kept(setup):
    db, *_ = setup
    written = ('So the function call would be:\n\n{"name": "price_open_architecture", '
               '"parameters": {"duration": "1_year"}}')
    client = ScriptedModelClient([Turn(text=["To answer this, ", written])])
    events = await _run(_ctx(setup, client, _registry([])))
    assert events[-1].kind == "bad_output"
    assert (await _failed(setup)).error_kind == "bad_output"
    assert (await db.execute(select(AgentMessage).where(AgentMessage.role == "agent"))
            ).scalar_one_or_none() is None


def test_ordinary_text_is_not_taken_for_a_written_call():
    from src.agent.loop import writes_a_call

    assert not writes_a_call('The collection is named "web" and costs [[F1]].')
    assert not writes_a_call('{"name": "web"} is a name, not a call.')
    assert writes_a_call('{ "name" : "find_matches", "arguments": {} }')


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


# --- 024: match references, result events, operation time limit, progress -----------------------


def _registry_024(seen: dict) -> Registry:
    import asyncio

    registry = Registry()

    @registry.operation("books", "Sees the per-message books.", NoArgs)
    async def books(ctx: OperationContext, args: NoArgs) -> OperationResult:
        seen.setdefault("books", []).append(id(ctx.matches))
        seen["message"] = ctx.message.id if ctx.message else None
        seen["agent_session"] = ctx.agent_session.id if ctx.agent_session else None
        return OperationResult(data={}, summary={})

    @registry.operation("makes_result", "Saves a result.", NoArgs)
    async def makes_result(ctx: OperationContext, args: NoArgs) -> OperationResult:
        from src.models.orm import AgentResult

        result = AgentResult(
            session_id=ctx.agent_session.id, message_id=ctx.message.id, seq=1,
            kind="category_comparison", title="AWS vs Azure", summary="1 row",
            basis={"question_kind": "category", "duration": "1_month",
                   "reference_side": "aws:us-east-1", "usage": "1 TB stored"},
            sides=[{"id": "aws:us-east-1", "provider": "aws", "region": "us-east-1",
                    "term": "on_demand"}],
            rows=[], totals={}, snapshots={})
        ctx.session.add(result)
        await ctx.session.flush()
        ctx.results.append(result)
        return OperationResult(data={"result_id": str(result.id)}, summary={})

    @registry.operation("slow", "Takes too long.", NoArgs)
    async def slow(ctx: OperationContext, args: NoArgs) -> OperationResult:
        await asyncio.sleep(5)
        return OperationResult(data={}, summary={})

    @registry.operation("progresses", "Reports progress.", NoArgs)
    async def progresses(ctx: OperationContext, args: NoArgs) -> OperationResult:
        for done in range(1, 11):
            ctx.progress(done, 10, "Matching services")
            await asyncio.sleep(0.01)
        return OperationResult(data={}, summary={})

    return registry


async def test_each_message_gets_its_own_match_book_and_sees_its_message(setup):
    _db, _user, agent_session, message, _ = setup
    seen: dict = {}
    client = ScriptedModelClient([
        Turn(tool_calls=[ToolCall("c1", "books", {}), ToolCall("c2", "books", {})]),
        Turn(text=["Done."]),
    ])
    await _run(_ctx(setup, client, _registry_024(seen)))
    assert len(set(seen["books"])) == 1  # one book for the whole message
    assert (seen["message"], seen["agent_session"]) == (message.id, agent_session.id)


async def test_a_result_is_sent_right_after_its_operation(setup):
    from src.models.schemas import AgentResultEvent

    client = ScriptedModelClient([
        Turn(tool_calls=[ToolCall("c1", "makes_result", {})]),
        Turn(text=["See the table."]),
    ])
    events = await _run(_ctx(setup, client, _registry_024({})))
    kinds = [e.event for e in events]
    at = kinds.index("operation")
    assert kinds[at + 1] == "result"
    result = events[at + 1]
    assert isinstance(result, AgentResultEvent) and result.result.title == "AWS vs Azure"


async def test_an_operation_past_the_time_limit_is_stopped_and_the_answer_continues(setup):
    db, *_ = setup
    client = ScriptedModelClient([
        Turn(tool_calls=[ToolCall("c1", "slow", {})]),
        Turn(text=["That took too long; try one category."]),
    ])
    events = await _run(_ctx(setup, client, _registry_024({}),
                             effective=_effective(timeout_seconds=1)))
    op = next(e for e in events if isinstance(e, AgentOperationEvent))
    assert (op.name, op.outcome) == ("slow", "timeout")
    assert events[-1].event == "done"
    logged = (await db.execute(select(AgentOperation))).scalar_one()
    assert logged.outcome == "timeout"
    tool_message = client.calls[1].messages[-1]
    assert tool_message.is_error and "took too long and was stopped" in tool_message.text


async def test_progress_is_streamed_as_status_and_throttled(setup):
    client = ScriptedModelClient([
        Turn(tool_calls=[ToolCall("c1", "progresses", {})]),
        Turn(text=["Done."]),
    ])
    events = await _run(_ctx(setup, client, _registry_024({})))
    progress = [e for e in events if isinstance(e, AgentStatusEvent) and e.total]
    assert progress, "no progress events"
    assert all(e.state == "running_operation" and e.label == "Matching services"
               and e.total == 10 for e in progress)
    assert progress[-1].done == 10  # the last one always gets through
    assert len(progress) < 10  # throttled (one every 250 ms, plus the last)


async def test_at_the_step_limit_an_answer_with_a_result_ends_with_the_apps_note(setup):
    db, *_ = setup
    client = ScriptedModelClient(
        [Turn(text=["Comparing."], tool_calls=[ToolCall("c0", "makes_result", {})])]
        + [Turn(tool_calls=[ToolCall(f"c{i}", "books", {})]) for i in range(1, MAX_ROUNDS)]
    )
    events = await _run(_ctx(setup, client, _registry_024({})))
    assert events[-1].event == "done"
    assert _text(events) == ("Comparing.\n\n(The agent used all its steps before finishing its "
                             "answer. Its results are in the Results pane.)")
    stored = (await db.execute(select(AgentMessage).where(AgentMessage.role == "agent"))
              ).scalar_one()
    assert stored.status == "complete" and stored.content == _text(events)


def test_the_step_limit_note_for_a_proposal():
    from src.agent.loop import _out_of_steps_note

    assert _out_of_steps_note(True, False, False) == (
        "(The agent used all its steps before finishing its answer. Its proposal is in the "
        "Results pane; nothing is saved until you accept it.)")

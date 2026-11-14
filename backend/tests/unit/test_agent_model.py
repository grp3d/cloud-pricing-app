"""The model interface and the scripted test client (023, research R2, contracts/agent-internals)."""

from __future__ import annotations

import pytest

from src.agent.clients.scripted import ScriptedModelClient, ScriptExhausted, Turn
from src.agent.model import ModelMessage, TextDelta, ToolCall, ToolSpec, Usage

TOOLS = [ToolSpec(name="echo", description="Echo.", input_schema={"type": "object"})]


async def _collect(client, messages):
    return [e async for e in client.stream("system prompt", messages, TOOLS)]


async def test_replays_turns_in_order_and_ends_each_call_with_one_usage():
    client = ScriptedModelClient([
        Turn(text=["Let me ", "check."], tool_calls=[ToolCall("c1", "echo", {"x": 1})],
             usage=Usage(12, 3)),
        Turn(text=["Done."]),
    ])
    first = await _collect(client, [ModelMessage(role="user", text="hi")])
    assert first == [TextDelta("Let me "), TextDelta("check."), ToolCall("c1", "echo", {"x": 1}),
                     Usage(12, 3)]
    second = await _collect(client, [ModelMessage(role="user", text="hi")])
    assert second == [TextDelta("Done."), Usage(0, 0)]


async def test_records_what_it_was_sent():
    client = ScriptedModelClient([Turn(text=["ok"])])
    messages = [ModelMessage(role="user", text="what does it cost?")]
    await _collect(client, messages)
    (call,) = client.calls
    assert call.system == "system prompt"
    assert call.messages == messages
    assert call.tools == TOOLS


async def test_raises_when_the_script_runs_out():
    client = ScriptedModelClient([])
    with pytest.raises(ScriptExhausted):
        await _collect(client, [ModelMessage(role="user", text="hi")])


async def test_a_turn_can_raise_or_wait():
    from src.agent.model import ModelUnreachable

    client = ScriptedModelClient([Turn(raises=ModelUnreachable("down"))])
    with pytest.raises(ModelUnreachable):
        await _collect(client, [ModelMessage(role="user", text="hi")])


async def test_the_e2e_demo_compares_when_the_question_names_azure():
    from src.agent.clients.scripted import ScriptedModelClient
    from src.agent.model import ModelMessage, ToolCall

    async def first_call(question: str) -> list:
        client = ScriptedModelClient.demo()
        return [e async for e in client.stream("s", [ModelMessage(role="user", text=question)],
                                               [])]

    compare = [e for e in await first_call("What would this cost on Azure?")
               if isinstance(e, ToolCall)]
    price = [e for e in await first_call("What does it cost?") if isinstance(e, ToolCall)]
    assert [c.name for c in compare] == ["find_matches"]
    assert [c.name for c in price] == ["price_open_architecture"]

"""The Ollama (local model) client (023, research R2), against a mocked HTTP transport."""

from __future__ import annotations

import json

import httpx
import pytest

from src.agent.clients.ollama import OllamaClient
from src.agent.model import (
    ModelBadOutput,
    ModelMessage,
    ModelUnreachable,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
)

TOOLS = [ToolSpec("price_open_architecture", "Price it.",
                  {"type": "object", "properties": {"duration": {"type": "string"}}})]


def _ndjson(*chunks: dict) -> bytes:
    return "".join(json.dumps(c) + "\n" for c in chunks).encode()


async def _run(handler, messages=None):
    client = OllamaClient(base_url="http://ollama.test", model="llama3.1",
                          transport=httpx.MockTransport(handler))
    return [e async for e in client.stream(
        "be helpful", messages or [ModelMessage(role="user", text="hi")], TOOLS
    )]


async def test_sends_system_messages_and_tools_and_streams_text_then_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=_ndjson(
            {"message": {"role": "assistant", "content": "Hel"}, "done": False},
            {"message": {"role": "assistant", "content": "lo"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True,
             "prompt_eval_count": 40, "eval_count": 7},
        ))

    events = await _run(handler)
    assert events == [TextDelta("Hel"), TextDelta("lo"), Usage(40, 7)]
    assert seen["url"] == "http://ollama.test/api/chat"
    body = seen["body"]
    assert body["model"] == "llama3.1" and body["stream"] is True
    assert body["messages"][0] == {"role": "system", "content": "be helpful"}
    assert body["messages"][1] == {"role": "user", "content": "hi"}
    assert body["tools"] == [{"type": "function", "function": {
        "name": "price_open_architecture", "description": "Price it.",
        "parameters": TOOLS[0].input_schema}}]


async def test_tool_calls_become_tool_call_events_and_results_go_back_as_tool_messages():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=_ndjson(
            {"message": {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "price_open_architecture",
                              "arguments": {"duration": "1_month"}}}]}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True,
             "prompt_eval_count": 5, "eval_count": 2},
        ))

    history = [
        ModelMessage(role="user", text="cost?"),
        ModelMessage(role="assistant", tool_calls=[ToolCall("a", "describe", {})]),
        ModelMessage(role="tool", text='{"ok": true}', tool_call_id="a", tool_name="describe"),
    ]
    events = await _run(handler, history)
    assert isinstance(events[0], ToolCall)
    assert events[0].name == "price_open_architecture"
    assert events[0].arguments == {"duration": "1_month"}
    assert events[-1] == Usage(5, 2)
    sent = seen["body"]["messages"]
    assert sent[2] == {"role": "assistant", "content": "",
                       "tool_calls": [{"function": {"name": "describe", "arguments": {}}}]}
    assert sent[3] == {"role": "tool", "content": '{"ok": true}', "tool_name": "describe"}


async def test_connection_error_is_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ModelUnreachable):
        await _run(handler)


async def test_http_error_status_is_unreachable():
    with pytest.raises(ModelUnreachable):
        await _run(lambda request: httpx.Response(404, content=b'{"error":"model not found"}'))


async def test_malformed_chunk_is_bad_output():
    with pytest.raises(ModelBadOutput):
        await _run(lambda request: httpx.Response(200, content=b"not json\n"))

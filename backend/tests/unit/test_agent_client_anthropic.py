"""The hosted (Anthropic) client (023, research R2), with the SDK's stream stubbed out."""

from __future__ import annotations

from types import SimpleNamespace as NS

import anthropic
import httpx
import pytest

from src.agent.clients.anthropic import AnthropicClient
from src.agent.model import (
    ModelBadOutput,
    ModelKeyRejected,
    ModelMessage,
    ModelNoCredit,
    ModelRateLimited,
    ModelUnreachable,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
)

TOOLS = [ToolSpec("price_open_architecture", "Price it.",
                  {"type": "object", "properties": {"duration": {"type": "string"}}})]


class FakeStream:
    def __init__(self, events, final, raise_on_iter=None):
        self._events, self._final, self._raise = events, final, raise_on_iter

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for event in self._events:
            yield event
        if self._raise:
            raise self._raise

    async def get_final_message(self):
        return self._final


def _client(stream_factory, sent):
    client = AnthropicClient(api_key="sk-test", model="claude-haiku-5-5")

    def stream(**kwargs):
        sent.append(kwargs)
        return stream_factory()

    client._client = NS(messages=NS(stream=stream))
    return client


def _final(content, stop="end_turn", usage=(30, 9)):
    return NS(content=content, stop_reason=stop,
              usage=NS(input_tokens=usage[0], output_tokens=usage[1]))


async def _run(client, messages=None):
    return [e async for e in client.stream(
        "be helpful", messages or [ModelMessage(role="user", text="hi")], TOOLS)]


async def test_text_and_usage():
    sent = []
    client = _client(lambda: FakeStream(
        [NS(type="text", text="Hel"), NS(type="text", text="lo")],
        _final([NS(type="text", text="Hello")])), sent)
    assert await _run(client) == [TextDelta("Hel"), TextDelta("lo"), Usage(30, 9)]
    request = sent[0]
    assert request["model"] == "claude-haiku-5-5"
    assert request["system"] == "be helpful"
    assert request["messages"] == [{"role": "user", "content": "hi"}]
    assert request["tools"] == [{
        "name": "price_open_architecture", "description": "Price it.",
        "input_schema": TOOLS[0].input_schema, "eager_input_streaming": True,
    }]


async def test_tool_use_and_the_raw_turn_goes_back_unchanged():
    sent = []
    thinking = NS(type="thinking", thinking="", signature="sig",
                  model_dump=lambda **_: {"type": "thinking", "thinking": "", "signature": "sig"})
    tool_use = NS(type="tool_use", id="tu_1", name="price_open_architecture",
                  input={"duration": "1_month"},
                  model_dump=lambda **_: {"type": "tool_use", "id": "tu_1",
                                          "name": "price_open_architecture",
                                          "input": {"duration": "1_month"}})
    responses = [
        lambda: FakeStream([], _final([thinking, tool_use], stop="tool_use")),
        lambda: FakeStream([NS(type="text", text="ok")], _final([NS(type="text", text="ok")])),
    ]
    client = _client(lambda: responses.pop(0)(), sent)
    first = await _run(client)
    assert first == [ToolCall("tu_1", "price_open_architecture", {"duration": "1_month"}),
                     Usage(30, 9)]

    history = [
        ModelMessage(role="user", text="cost?"),
        ModelMessage(role="assistant", tool_calls=[first[0]]),
        ModelMessage(role="tool", text='{"total": "F1"}', tool_call_id="tu_1",
                     tool_name="price_open_architecture"),
    ]
    await _run(client, history)
    messages = sent[1]["messages"]
    assert messages[1] == {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "tool_use", "id": "tu_1", "name": "price_open_architecture",
         "input": {"duration": "1_month"}},
    ]}
    assert messages[2] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_1", "content": '{"total": "F1"}',
         "is_error": False},
    ]}


async def test_refusal_becomes_a_plain_decline():
    client = _client(lambda: FakeStream([], _final([], stop="refusal")), [])
    events = await _run(client)
    assert isinstance(events[0], TextDelta) and "can't help" in events[0].text


async def test_truncated_tool_input_is_bad_output():
    tool_use = NS(type="tool_use", id="tu", name="x", input={}, model_dump=lambda **_: {})
    client = _client(lambda: FakeStream([], _final([tool_use], stop="max_tokens")), [])
    with pytest.raises(ModelBadOutput):
        await _run(client)


async def test_unparseable_tool_input_is_bad_output():
    client = _client(lambda: FakeStream([], None, raise_on_iter=ValueError("bad json")), [])
    with pytest.raises(ModelBadOutput):
        await _run(client)


async def test_connection_error_is_unreachable():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client = _client(
        lambda: FakeStream([], None, raise_on_iter=anthropic.APIConnectionError(request=request)),
        [])
    with pytest.raises(ModelUnreachable):
        await _run(client)


def _status(cls, code, message):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(message, response=httpx.Response(code, request=request), body=None)


@pytest.mark.parametrize(("error", "raised"), [
    (_status(anthropic.BadRequestError, 400, "Your credit balance is too low to access the "
             "Anthropic API."), ModelNoCredit),
    (_status(anthropic.AuthenticationError, 401, "invalid x-api-key"), ModelKeyRejected),
    (_status(anthropic.PermissionDeniedError, 403, "not allowed"), ModelKeyRejected),
    (_status(anthropic.RateLimitError, 429, "slow down"), ModelRateLimited),
    (_status(anthropic.BadRequestError, 400, "messages: bad shape"), ModelUnreachable),
    (_status(anthropic.InternalServerError, 500, "oops"), ModelUnreachable),
])
async def test_api_status_errors_say_what_went_wrong(error, raised):
    client = _client(lambda: FakeStream([], None, raise_on_iter=error), [])
    with pytest.raises(raised):
        await _run(client)

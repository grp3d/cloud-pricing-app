"""A scripted model client (023-agent-foundation, research R2, R15).

Replays a fixed sequence of turns and records what it was sent. Every automated agent test uses
it, so no test ever calls a live model (constitution Principle V). `demo()` is the reply the
e2e backend uses when the Admin selects the `scripted` provider.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from src.agent.model import (
    ModelEvent,
    ModelMessage,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
)


class ScriptExhausted(AssertionError):
    """The code under test made more model calls than the script has turns."""


@dataclass
class Turn:
    text: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=lambda: Usage(0, 0))
    # Raised instead of replying (to test failures), and a wait before replying (timeouts).
    raises: Exception | None = None
    delay_seconds: float = 0


@dataclass
class RecordedCall:
    system: str
    messages: list[ModelMessage]
    tools: list[ToolSpec]


class ScriptedModelClient:
    provider = "scripted"

    def __init__(self, turns: list[Turn], model: str = "scripted") -> None:
        self.model = model
        self._turns = list(turns)
        self.calls: list[RecordedCall] = []

    @classmethod
    def demo(cls) -> ScriptedModelClient:
        """The e2e model. A question that names Azure compares the open architecture with Azure
        in eastus (024); anything else prices the open architecture for 1 month (023)."""
        return _DemoClient()

    async def stream(
        self, system: str, messages: list[ModelMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[ModelEvent]:
        self.calls.append(RecordedCall(system, list(messages), list(tools)))
        if not self._turns:
            raise ScriptExhausted("the scripted model has no more turns")
        turn = self._turns.pop(0)
        if turn.delay_seconds:
            await asyncio.sleep(turn.delay_seconds)
        if turn.raises is not None:
            raise turn.raises
        for chunk in turn.text:
            yield TextDelta(chunk)
        for call in turn.tool_calls:
            yield call
        yield turn.usage


class _DemoClient(ScriptedModelClient):
    """Chooses its script from the question, on the first call of each answer."""

    def __init__(self) -> None:
        super().__init__([])
        self._chosen = False

    async def stream(self, system, messages, tools):
        if not self._chosen:
            self._chosen = True
            question = next((m.text for m in reversed(messages) if m.role == "user"), "")
            self._turns = _COMPARE() if "azure" in question.lower() else _PRICE()
        async for event in super().stream(system, messages, tools):
            yield event


def _PRICE() -> list[Turn]:
    return [
        Turn(tool_calls=[ToolCall("demo-1", "price_open_architecture",
                                  {"duration": "1_month"})],
             usage=Usage(100, 20)),
        Turn(text=["This architecture costs [[F1]] ", "for 1 month (31 days)."],
             usage=Usage(150, 30)),
    ]


def _COMPARE() -> list[Turn]:
    return [
        Turn(tool_calls=[ToolCall("demo-1", "find_matches",
                                  {"target_providers": ["azure"],
                                   "target_regions": {"azure": "eastus"}})],
             usage=Usage(100, 20)),
        Turn(tool_calls=[ToolCall("demo-2", "price_matches", {})], usage=Usage(150, 30)),
        Turn(text=["On Azure (eastus), the matched services come to [[F2]] against [[F1]] ",
                   "on AWS. The table beside me shows each match."],
             usage=Usage(200, 40)),
    ]

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
        """Prices the open architecture for 1 month, then states the total by reference."""
        return cls([
            Turn(tool_calls=[ToolCall("demo-1", "price_open_architecture",
                                      {"duration": "1_month"})],
                 usage=Usage(100, 20)),
            Turn(text=["This architecture costs [[F1]] ", "for 1 month (31 days)."],
                 usage=Usage(150, 30)),
        ])

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

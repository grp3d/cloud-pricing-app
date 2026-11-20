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
        """The e2e model. A question that says "translate" proposes the open architecture on
        Azure in eastus (026); one that names Azure compares it with Azure in eastus (024); one
        that says "double" proposes doubling its first service (025); anything else prices the
        open architecture for 1 month (023)."""
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
            lowered = question.lower()
            self._turns = (_TRANSLATE() if "translate" in lowered else
                           _COMPARE() if "azure" in lowered else
                           _PROPOSE() if "double" in lowered else _PRICE())
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


def _PROPOSE() -> list[Turn]:
    return [
        Turn(tool_calls=[ToolCall("demo-1", "describe_open_architecture", {})],
             usage=Usage(100, 20)),
        Turn(tool_calls=[ToolCall("demo-2", "propose_changes", {
            "title": "Double the first service",
            "change_services": [{"ref": "V1", "scale": "2"}]})], usage=Usage(150, 30)),
        Turn(text=["Doubling it takes the total from [[F2]] to [[F1]]. It's a proposal beside me; ",
                   "nothing is saved until you accept it."],
             usage=Usage(200, 40)),
    ]



def _TRANSLATE() -> list[Turn]:
    regions = {"eu-west-1": "eastus", "us-east-1": "eastus"}
    return [
        Turn(tool_calls=[ToolCall("demo-1", "find_translation",
                                  {"provider": "azure", "regions": regions})],
             usage=Usage(100, 20)),
        Turn(tool_calls=[ToolCall("demo-2", "propose_translation",
                                  {"provider": "azure", "regions": regions})],
             usage=Usage(150, 30)),
        Turn(text=["On Azure (eastus) the matched services come to [[F4]] against [[F3]] on AWS. ",
                   "The mapping is beside me; nothing is created until you accept."],
             usage=Usage(200, 40)),
    ]

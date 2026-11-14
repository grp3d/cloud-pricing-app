"""The thin model interface (023-agent-foundation, research R2, contracts/agent-internals.md).

Messages and tools go in; text deltas, tool calls and one usage record come out. Each client
converts `ToolSpec` and `ModelMessage` to its provider's wire format, so nothing outside a client
knows that format (constitution Principle VIII: no dependence on one model vendor).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from src.agent.settings_service import EffectiveAgentSettings


@dataclass(frozen=True)
class ToolSpec:
    """A provider-neutral tool: its name, what it does, and a JSON Schema for its inputs."""

    name: str
    description: str
    input_schema: dict


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


ModelEvent = TextDelta | ToolCall | Usage


@dataclass
class ModelMessage:
    """One message of the conversation sent to the model.

    - `user`: the user's text (with the open architecture attached by the loop);
    - `assistant`: the model's earlier text and any tool calls it made;
    - `tool`: one tool result, as JSON text, answering `tool_call_id`.
    """

    role: Literal["user", "assistant", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None
    is_error: bool = False


class ModelClient(Protocol):
    provider: str
    model: str

    def stream(
        self, system: str, messages: list[ModelMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[ModelEvent]:
        """One model call. Yields text deltas and tool calls, then exactly one `Usage`."""
        ...


class ModelError(Exception):
    """A model call failed; `kind` is the error kind shown to the user."""

    kind = "failed"


class ModelUnreachable(ModelError):
    kind = "unreachable"


class ModelNoCredit(ModelError):
    """The hosted model's account has no credit left."""

    kind = "no_credit"


class ModelKeyRejected(ModelError):
    """The hosted model refused the API key."""

    kind = "key_rejected"


class ModelRateLimited(ModelError):
    kind = "rate_limited"


class ModelTimeout(ModelError):
    kind = "timeout"


class ModelBadOutput(ModelError):
    kind = "bad_output"


class AgentUnavailable(Exception):
    """The effective settings can't produce a usable client (no model; a hosted provider with
    no key or token rates; a provider not allowed here)."""


def build_client(effective: EffectiveAgentSettings) -> ModelClient:
    """The client for the effective settings, or `AgentUnavailable`."""
    from src.agent import settings_service

    if not settings_service.provider_allowed(effective.provider):
        raise AgentUnavailable(f"provider {effective.provider} is not allowed")
    if effective.provider == "scripted":
        from src.agent.clients.scripted import ScriptedModelClient

        return ScriptedModelClient.demo()
    if not effective.model:
        raise AgentUnavailable("no model is set")
    if effective.provider == "ollama":
        from src.agent.clients.ollama import OllamaClient

        return OllamaClient(base_url=effective.base_url, model=effective.model)
    if effective.provider == "anthropic":
        key = settings_service.api_key()
        if not key:
            raise AgentUnavailable("no API key is set")
        if (
            effective.price_per_input_token_usd is None
            or effective.price_per_output_token_usd is None
        ):
            raise AgentUnavailable("token rates are not set")
        from src.agent.clients.anthropic import AnthropicClient

        return AnthropicClient(api_key=key, model=effective.model)
    raise AgentUnavailable(f"unknown provider {effective.provider}")

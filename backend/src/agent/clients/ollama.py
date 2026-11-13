"""The local model client: Ollama's `/api/chat` with tools and streaming (023, research R2).

Ollama streams newline-delimited JSON. Text arrives in `message.content`, tool calls in
`message.tool_calls` (with no ids, so ids are generated here), and the final chunk
(`done: true`) carries the token counts. A local model costs $0 (FR-022).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import httpx

from src.agent.model import (
    ModelBadOutput,
    ModelEvent,
    ModelMessage,
    ModelUnreachable,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
)


def _tool(spec: ToolSpec) -> dict:
    return {"type": "function", "function": {
        "name": spec.name, "description": spec.description, "parameters": spec.input_schema,
    }}


def _message(message: ModelMessage) -> dict:
    if message.role == "tool":
        return {"role": "tool", "content": message.text, "tool_name": message.tool_name}
    out: dict = {"role": message.role, "content": message.text}
    if message.tool_calls:
        out["tool_calls"] = [
            {"function": {"name": c.name, "arguments": c.arguments}} for c in message.tool_calls
        ]
    return out


class OllamaClient:
    provider = "ollama"

    def __init__(self, base_url: str, model: str,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/api/chat"
        self._transport = transport

    async def stream(
        self, system: str, messages: list[ModelMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[ModelEvent]:
        body = {
            "model": self.model,
            "stream": True,
            "messages": [{"role": "system", "content": system}, *map(_message, messages)],
            "tools": [_tool(t) for t in tools],
        }
        # The loop applies the agent timeout around the whole call; no separate read timeout.
        async with httpx.AsyncClient(transport=self._transport, timeout=None) as http:
            try:
                async with http.stream("POST", self._url, json=body) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise ModelUnreachable(
                            f"the local model service answered {response.status_code}"
                        )
                    usage = Usage(0, 0)
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ModelBadOutput("the local model sent unreadable output") from exc
                        if "error" in chunk:
                            raise ModelBadOutput(str(chunk["error"])[:200])
                        message = chunk.get("message") or {}
                        if message.get("content"):
                            yield TextDelta(message["content"])
                        for call in message.get("tool_calls") or []:
                            function = call.get("function") or {}
                            arguments = function.get("arguments") or {}
                            if isinstance(arguments, str):
                                try:
                                    arguments = json.loads(arguments)
                                except json.JSONDecodeError as exc:
                                    raise ModelBadOutput("unreadable tool arguments") from exc
                            if not function.get("name") or not isinstance(arguments, dict):
                                raise ModelBadOutput("a tool call without a name or arguments")
                            yield ToolCall(f"call-{uuid.uuid4().hex[:12]}", function["name"],
                                           arguments)
                        if chunk.get("done"):
                            usage = Usage(int(chunk.get("prompt_eval_count") or 0),
                                          int(chunk.get("eval_count") or 0))
                    yield usage
            except httpx.TransportError as exc:
                raise ModelUnreachable("the local model service can't be reached") from exc

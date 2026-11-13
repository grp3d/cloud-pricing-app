"""The hosted model client: Anthropic's Messages API, streamed, with tools (023, research R2).

Uses the official SDK's async `messages.stream`. Text events stream as they arrive; the final
message gives the tool calls and token counts. Within one answer's tool loop the model's own
turn (including any thinking blocks) is sent back unchanged, so this client remembers the raw
content of the turns it produced, keyed by tool-call id. Tool inputs stream as they are
generated (`eager_input_streaming`); the operations registry validates every input before an
operation runs, and an input the SDK can't parse becomes "bad output".
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import anthropic

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

MAX_TOKENS = 16000
DECLINE = "I can't help with that request."


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        # The loop applies the agent timeout; the SDK retries transient failures twice.
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=2)
        self._turns: dict[str, list[dict]] = {}

    def _tool(self, spec: ToolSpec) -> dict:
        return {"name": spec.name, "description": spec.description,
                "input_schema": spec.input_schema, "eager_input_streaming": True}

    def _messages(self, messages: list[ModelMessage]) -> list[dict]:
        out: list[dict] = []
        for message in messages:
            if message.role == "user":
                out.append({"role": "user", "content": message.text})
            elif message.role == "assistant":
                raw = next((self._turns[c.id] for c in message.tool_calls
                            if c.id in self._turns), None)
                if raw is not None:
                    out.append({"role": "assistant", "content": raw})
                elif message.tool_calls:
                    content = ([{"type": "text", "text": message.text}] if message.text else [])
                    content += [{"type": "tool_use", "id": c.id, "name": c.name,
                                 "input": c.arguments} for c in message.tool_calls]
                    out.append({"role": "assistant", "content": content})
                else:
                    out.append({"role": "assistant", "content": message.text})
            else:
                result = {"type": "tool_result", "tool_use_id": message.tool_call_id,
                          "content": message.text, "is_error": message.is_error}
                # All results for one assistant turn go back in a single user message.
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(result)
                else:
                    out.append({"role": "user", "content": [result]})
        return out

    async def stream(
        self, system: str, messages: list[ModelMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[ModelEvent]:
        try:
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=self._messages(messages),
                tools=[self._tool(t) for t in tools],
            ) as stream:
                async for event in stream:
                    if event.type == "text" and event.text:
                        yield TextDelta(event.text)
                final = await stream.get_final_message()
        except ValueError as exc:
            raise ModelBadOutput("the model sent a tool input that couldn't be read") from exc
        except anthropic.APIConnectionError as exc:
            raise ModelUnreachable("the hosted model can't be reached") from exc
        except anthropic.APIStatusError as exc:
            raise ModelUnreachable(f"the hosted model answered {exc.status_code}") from exc

        tool_uses = [b for b in final.content if b.type == "tool_use"]
        if final.stop_reason == "refusal":
            yield TextDelta(DECLINE)
        elif tool_uses and final.stop_reason == "max_tokens":
            raise ModelBadOutput("the model's tool call was cut off")
        elif tool_uses:
            raw = [b.model_dump(exclude_none=True) for b in final.content]
            for block in tool_uses:
                if not isinstance(block.input, dict):
                    raise ModelBadOutput("a tool call without object input")
                self._turns[block.id] = raw
                yield ToolCall(block.id, block.name, block.input)
        yield Usage(int(final.usage.input_tokens or 0), int(final.usage.output_tokens or 0))

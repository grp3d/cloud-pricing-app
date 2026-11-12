# Contract: Agent Internals (model interface, operations, figures)

Internal Python contracts in `backend/src/agent/`. They are what agent-02 to agent-04 build on,
so they are written down here.

## Model interface (`src/agent/model.py`)

```text
ToolSpec      = {name, description, input_schema (JSON Schema)}
ModelMessage  = {role: user|assistant|tool, content: text | tool_calls | tool_result}
ModelEvent    = TextDelta{text} | ToolCall{id, name, arguments} | Usage{input_tokens, output_tokens}

class ModelClient(Protocol):
    provider: str              # "anthropic" | "ollama" | "scripted"
    model: str
    def stream(system: str, messages: list[ModelMessage], tools: list[ToolSpec])
        -> AsyncIterator[ModelEvent]
```

- One `stream` call is one model call and yields exactly one `Usage` at the end (zeros if the
  provider reports none).
- Clients convert `ToolSpec` to their provider's format; nothing outside the client knows the
  provider's wire format.
- Errors raise `ModelUnreachable`, `ModelTimeout` (raised by the loop's timeout) or
  `ModelBadOutput`.
- `build_client(settings)` returns the client for the effective settings, or raises
  `AgentUnavailable(reason)` (no model; hosted with no key or rates).

## Operations (`src/agent/operations.py`)

```text
@operation(name, description, input_model: pydantic.BaseModel)
async def op(ctx: OperationContext, args) -> OperationResult

OperationContext = {session (db), user, open_architecture_id | None, figures: FigureBook}
OperationResult  = {data: dict (sent to the model as JSON), summary: dict, snapshot: dict | None}
```

- `ctx.user` and `ctx.open_architecture_id` come from the request, never from model arguments.
- Every operation is read-only in this feature and goes through the same service functions as
  the app's routes, so ownership and visibility checks are identical.
- The registry produces the `ToolSpec` list from the decorated functions (one source of truth).

## Figures (`src/agent/figures.py`)

```text
FigureBook.add(amount: Decimal, label: str) -> "F7"       # unrounded engine value kept
FigureBook.render(text) -> text                            # [[F7]] → "$1,780.96"
find_model_money(text) -> list[str]                        # money the model wrote itself
```

- Formatting: USD, 2 decimal places, half-up, thousands separators (matching the Pricing tab).
- Totals the agent reports are computed by operations from unrounded values, then added once.
- An unknown reference (`[[F99]]`) is rendered as "[figure unavailable]" and logged.

## Agent loop (`src/agent/loop.py`)

```text
async def answer(ctx, user_message) -> AsyncIterator[StreamEvent]
```

1. Build the model conversation: system prompt, the last 20 messages, the new message with the
   open architecture id attached as context.
2. Up to 6 rounds: check the global cap and the session close time → call the model under the
   timeout → record usage → run any tool calls (log each operation) → feed results back.
3. Stream text through the figure filter as it arrives: references rendered, model-written
   money replaced with "[figure removed]" (research R1).
4. If any figure was rendered, append the footer (duration, snapshot date and revision) built
   from the operation results (research R1).
5. Store the agent message, emit `done`.

Any failure emits one `error` event and marks the user message `failed`.

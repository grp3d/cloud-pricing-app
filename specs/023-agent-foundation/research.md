# Research: Agent Foundation

Decisions behind [plan.md](./plan.md). Each item: decision, rationale, alternatives.

## R1. Figures come from the engine: figure references, not model-written numbers

**Decision:** every monetary figure in an agent answer is written by the app, not the model.
Operations that return money give each amount a reference (`F1`, `F2`, …) alongside its value.
The model writes `[[F3]]` where a figure belongs; the server replaces it with the engine's value,
formatted as USD to 2 decimal places (`$1,780.96`). As the text streams, the server also
checks it for money amounts the model wrote itself (a currency sign or `USD` next to a number);
each one is replaced with "[figure removed]" before it reaches the browser, and the activity log
counts it. Text is held back only as long as needed to recognise a reference or an amount, so
answers still appear progressively (FR-009). A model that keeps doing this fails the evaluation
(R8), which is how it is kept out of use.

Whenever an answer contains at least one rendered figure, the server appends a footer line it
builds itself from the operation results: the duration and the snapshot date and revision (for
example "Prices for 1 month (31 days), snapshot 2026-11-02 r2"; one entry per provider if they
differ). This makes FR-004's "say which duration" and FR-005's "show the snapshot date" hold
regardless of the model (analysis finding U1). Totals and cost-driver sums are computed by the operations (in tested code from the
engine's unrounded values), never by the model.

**Rationale:** constitution Principle I and FR-004 forbid the model calculating, rounding or
recalling a price. Prompting alone can't guarantee that; substitution plus a check can, and the
evaluation checks (R8) can verify it to the cent. Formatting in one place also makes the
2-decimal rule and the Pricing tab match automatic.

**Alternatives:** trusting the prompt and checking afterwards (a wrong figure reaches the user
first); asking the model to rewrite (another paid call, and the first version has already
streamed); structured-only answers with no free text (too rigid for "what drives the cost?").

## R2. A thin model interface and our own agent loop

**Decision:** one small interface, `ModelClient.stream(system, messages, tools) → events`
(text deltas, tool calls, a final usage record with input and output tokens). Three
implementations:

- `AnthropicClient` (hosted), using the official `anthropic` Python SDK's streaming Messages API
  with tool use;
- `OllamaClient` (local), calling Ollama's `/api/chat` with `tools` and `stream: true` over
  `httpx`;
- `ScriptedModelClient` (tests), which replays a script of turns and records what it was sent.

Tool schemas are written once, provider-neutral (name, description, JSON Schema for inputs),
and each client converts them to its provider's format. The agent loop is ours: send the
conversation; if the model calls tools, run them and send the results; repeat up to 6 rounds
per user message; then finish with the model's text.

**Rationale:** Principle VIII (no dependence on one vendor; providers chosen by settings), the
input's planning notes, and Principle VI (two real providers plus a test double, no plugin
system). Owning the loop keeps limits, timeouts, figure checks and the activity log in one
place.

**Alternatives:** an agent framework (adds a large dependency and hides the loop we need to
control); raw HTTP for Anthropic too (the SDK handles streaming and tool-use events reliably).

## R3. Streaming to the browser: server-sent events over a POST

**Decision:** `POST /api/v1/agent/session/messages` returns `text/event-stream`. Events:
`accepted`, `text`, `operation`, `status`, `done`, `error`. The browser reads it with `fetch`
and a stream reader (not `EventSource`, which can't send the `Authorization` header). Caddy's
`reverse_proxy` passes event streams through unbuffered; the Vite dev proxy does too.

**Rationale:** FR-009 (progressive answers) with no new infrastructure; one request per
message; works with the existing bearer-token auth.

**Alternatives:** WebSockets (a second protocol and connection lifecycle for one panel);
polling (no progressive text).

## R4. Sessions, expiry and concurrency

**Decision:** sessions, messages and operations live in Postgres (Principle II: user-defined
data). One session per user is enforced by a unique key on `user_id`. A session's `closes_at`
is `started_at + 3 days`. Expiry is enforced two ways: every agent request checks it first (an
expired session is deleted and treated as absent), and a background task started in the app's
lifespan deletes expired sessions every 15 minutes. The agent loop checks `closes_at` between
steps and stops an answer that runs past it. One message is answered at a time per session; a
second send while one is running gets `409`.

**Rationale:** FR-010–FR-013; deletion must happen even if the user never returns. A lock per
session avoids two tabs interleaving answers.

**Alternatives:** keeping sessions in memory (lost on restart; the server runs as one process
but restarts on deploy); deleting only lazily (conversations would outlive their 3 days).

## R5. Settings: one database row, environment defaults, secrets only in the environment

**Decision:** an `agent_settings` table with one row. Each column is nullable; the effective
value is the row's value if set, otherwise the environment default (`AGENT_*` in `Settings`),
otherwise the built-in default. Settings are read at the start of every message, so a change
applies to the next message (FR-016, SC-004). The hosted API key comes from
`AGENT_ANTHROPIC_API_KEY`, or, in the cloud, from the SSM parameter named by
`AGENT_ANTHROPIC_API_KEY_PARAMETER`, read once at startup (as `ops/params.py` already does for
other parameters). The key is never stored in the database or returned by any endpoint; Agent
settings returns only `api_key_set: true|false` (FR-017).

**Hosted-model rates:** `agent_price_per_input_token_usd` and `..._output_...` have no
built-in default. While either is unset, the hosted provider refuses to run and the panel says
the agent is unavailable. This keeps cost bounded (Principle VIII) without the app guessing a
vendor's prices.

**Built-in defaults:** `agent_enabled` false; `agent_provider` `ollama`; `agent_base_url`
`http://localhost:11434`; `agent_timeout_seconds` 60; `agent_global_monthly_cap_usd` 10;
`agent_default_user_monthly_inputs` 100; `agent_model` none (the agent can't be switched on
until a model is named).

**Alternatives:** environment only (needs a redeploy, against FR-016); a key/value table (loses
typing and validation).

## R6. Access, preview and limits

**Decision:** three new columns on `users`: `agent_enabled_for_user` (false),
`agent_preview_input_counter` (3), `agent_monthly_input_limit` (null = the default). A user
message is **accepted** in one transaction that locks the user row (`SELECT … FOR UPDATE`):

1. agent on globally, and the hosted provider usable (key and rates set) → else `agent_off` or
   `unavailable`;
2. the user is named and active;
3. enabled for the user, or preview counter > 0 → else `preview_used`. Turning the agent off
   for a user sets their preview counter to 0 in the same update (spec FR-020);
4. inputs accepted this month < the user's limit → else `user_limit` (with the reset date);
5. spend this month < the global cap → else `global_cap` (with the reset date);
6. record the input (decrement the preview counter if it was a preview input) and commit.

Before each further model call within that message (tool rounds), step 5 is checked again, so
once the cap is reached no further call is made (SC-003). A call already in flight may finish
and slightly overshoot the cap; the next call is refused. "Month" is the UTC calendar month;
limits reset at 00:00 UTC on the 1st. Retrying a failed message re-runs the same accepted
message and is not charged again.

**Rationale:** FR-019–FR-023; the row lock stops two tabs both spending the last input.

**Alternatives:** counters reset by a scheduled job (needs a job and can drift; counting
records by month can't); per-user settings in `user_preferences` (that's the user's own data;
these are Admin-controlled).

## R7. Usage records

**Decision:** an `agent_usage` table with one row per model call: user, session (nullable,
set to null when the session is deleted), message, provider, model, input tokens, output
tokens, cost (computed at the rates in force at the time; $0 for a local model), whether it
belongs to a preview input, and whether it is the call that counted the input. Spend this
month = sum of cost; inputs this month = count of counted rows. The Admin's usage figures
(FR-022a) come from the same queries. Usage rows are never deleted by this feature.

**Rationale:** FR-013 and FR-022 (keep usage after a session is deleted); one source for both
limits and the Admin's figures.

## R8. Evaluation: fixed checks, scripted by default, live models opt-in

**Decision:** evaluation cases live in `backend/tests/agent_evals/cases/*.yaml`, one per golden
conversation (GC-1 to GC-7). Each states the architecture (from the 022 standard architectures
in the `pricing_parquet_standard` fixture, plus small purpose-built ones), the user messages,
and fixed checks (clarification 3): operations that must be called, figures that must equal
the engine's to the cent, phrases that must or must not appear, and whether it must be
refused. No model grades answers.

Two runs use the same cases:

- **Default test run:** each case also has a scripted model turn sequence; the run checks the
  machinery (operations, permissions, figure substitution, refusals) with
  `ScriptedModelClient`. No network (FR-025, Principle V).
- **Live evaluation (opt-in):** `pytest -m live_model` with `AGENT_EVAL_MODELS` (for example
  `ollama:llama3.1,anthropic:claude-haiku-5-5`) runs each case against each model and writes a
  pass/fail report per model to `backend/agent-eval-report.md` (git-ignored). The marker is
  excluded from the default run.

**Rationale:** reuses the existing test database and fixture setup; one case format for both
runs; SC-005 (two models, a readable report).

**Alternatives:** a separate CLI with its own database setup (duplicates test fixtures); a
model grader (rejected in clarification 3).

## R9. Operations: read-only, scoped to the user, typed once

**Decision:** the agent's operations are typed functions in `src/agent/operations.py` over the
existing services, each taking the current user and the open architecture from the server
side (never from the model):

| Operation | Returns | Built on |
|---|---|---|
| `describe_open_architecture` | collections (name, type, region, nesting) and services (readable name, SKU, quantity, term) | `get_owned_architecture` |
| `price_open_architecture(duration)` | total, unpriceable services, snapshot date and revision, figure references | `calculate_architecture_price` |
| `cost_drivers(duration, top)` | services ranked by price, each with a figure reference, plus the total | the same calculation, summed per service in tested code |
| `list_importable_architectures(provider?)` | groups by owner, Admin first | the importable listing, moved from the route into a service function both use |

Durations are the app's three (`1_day`, `1_month`, `1_year`). The model can't name a user,
another architecture's id or a storage path; there is no parameter for it. Operation output is
passed back to the model as JSON tool results, marked as data (FR-008). An MCP server over the
same operations (mentioned in the input as optional) is **not built** in this feature
(Principle VI); the operations are shaped so it could be added later.

**Rationale:** FR-002, FR-003, FR-006, FR-007; Principle VII. Ownership is enforced by the same
service functions the app uses, so a manipulated model can't reach beyond the user.

## R10. Prompt content and untrusted text

**Decision:** a fixed system prompt (in code, versioned) states the agent's purpose, the
read-only scope, the figure-reference rule, the durations, and that tool results are data. The
open architecture's id is attached to each user message server-side. Architecture names and
other user text reach the model only inside tool results, never in the system prompt. The
conversation sent to the model is the last 20 messages of the session plus fresh tool results;
older messages are kept for display but not sent (the spec's long-conversation edge case).

**Rationale:** Principle VII (content is data); keeps prompts bounded in size and cost.

## R11. Failure handling and the timeout

**Decision:** each model call runs under `asyncio.timeout(agent_timeout_seconds)`. Timeouts,
connection errors, provider errors and unusable output (no text and no valid tool call, or a
tool call naming an unknown operation or invalid input) end the message with an `error` event
carrying a kind (`timeout`, `unreachable`, `bad_output`, `failed`) and leave the user message
stored with status `failed`, so **Retry** re-runs it without a new input charge. Operation
errors are returned to the model as tool errors (it can say so), and recorded in the activity
log. Nothing outside `/agent/*` routes is touched, so the app is unaffected (FR-015).

## R12. The panel in the workspace layout

**Decision:** a new `AgentPanel` in the centre column under the canvas (clarification 1):

- collapsed by default to a thin bar with the agent's name and an open button;
- open, it is separated from the canvas by a horizontal divider built like the inspector's
  split divider (pointer drag, keyboard arrows, `role="separator"`);
- its bottom-right corner has the same resize control style as the canvas
  (`DiagramResizeHandle`), changing the panel's height and width within the column;
- open state, divider position and panel size are saved in account preferences, in a new
  `workspace.agent_panel` section (`open`, `split`, `height`, `width`), validated by the
  existing typed preferences schema (Principle IV).

The panel is rendered only when `GET /agent/status` says the agent is on (clarification 4). Its
top-right shows the session's start and close times. A toggle switches the body between the
conversation and the activity log.

**Rationale:** matches clarification 1 and the existing inspector and canvas behaviour, and
reuses the account-saved preferences from 019.

## R13. Admin page

**Decision:** a new `AgentSettingsSection` above User Management, editing every setting in the
spec's table, showing `API key set: yes/no` and `This month: $x.xx of $y.yy`. The user table
gains three editable columns (Agent on, Preview left, Monthly limit) and a read-only "This
month" column (`n of limit`). Saving goes through new admin endpoints with server-side
validation; invalid values return `422` with a field message and leave the old value.

## R14. New dependencies

- Backend: `anthropic` (hosted model client), and `httpx` moved from dev to main dependencies
  (Ollama client). `pyyaml` added to dev dependencies for evaluation cases.
- Frontend: none.

## R15. An end-to-end check without a real model

**Decision:** the e2e backend (`frontend/e2e/start-backend.sh`) sets
`AGENT_ALLOW_SCRIPTED_PROVIDER=1`, which allows a third provider value, `scripted`, that is
refused everywhere else. One Playwright spec switches it on through the Admin API, runs a
scripted reply (a figure reference and an operation), and checks the panel, streaming, the
activity log and the layout persistence. All other e2e specs run with the agent off, unchanged.

**Rationale:** the panel and streaming are only really tested in a browser, and Principle V
forbids live models in automated tests.

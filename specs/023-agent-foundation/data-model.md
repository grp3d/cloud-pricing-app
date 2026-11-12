# Data Model: Agent Foundation

All new data is Postgres application data (constitution Principle II). Nothing here stores a
vendor price: figures are computed by the pricing engine when an operation runs, and only
their values as shown (with the snapshot date) are kept in the conversation and activity log.
One Alembic revision, **0010** (`0010_agent_foundation.py`), adds everything below.

## 1. `agent_settings` (one row)

App-wide settings the Admin changes at run time (spec Story 5, research R5). A null column
means "use the environment default, else the built-in default".

| Column | Type | Built-in default | Validation |
|---|---|---|---|
| `id` | int PK | 1 (CHECK `id = 1`) | |
| `agent_enabled` | bool null | false | |
| `agent_provider` | text null | `ollama` | `anthropic` or `ollama` |
| `agent_model` | text null | none | 1–200 chars; required before the agent can be switched on |
| `agent_base_url` | text null | `http://localhost:11434` | http(s) URL; used only for `ollama` |
| `agent_timeout_seconds` | int null | 60 | 5–600 |
| `agent_global_monthly_cap_usd` | numeric(10,2) null | 10.00 | ≥ 0 |
| `agent_default_user_monthly_inputs` | int null | 100 | ≥ 0 |
| `agent_price_per_input_token_usd` | numeric(14,10) null | none | ≥ 0; required for `anthropic` |
| `agent_price_per_output_token_usd` | numeric(14,10) null | none | ≥ 0; required for `anthropic` |
| `updated_at` | timestamptz | now | |

- Switching `agent_enabled` on is refused while `agent_model` is unset, or, for `anthropic`,
  while the key or either rate is missing.
- The API key is **not** a column (FR-017).

## 2. `users` (three new columns)

| Column | Type | Default | Validation |
|---|---|---|---|
| `agent_enabled_for_user` | bool not null | false | |
| `agent_preview_input_counter` | int not null | 3 | ≥ 0 |
| `agent_monthly_input_limit` | int null | null (= the default) | ≥ 0 |

Existing users get the defaults. Guests (`username IS NULL`) keep the columns but can never use
the agent (FR-001).

## 3. `agent_sessions`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → users, **unique**, on delete cascade | one session per user (FR-010) |
| `started_at` | timestamptz | |
| `closes_at` | timestamptz | `started_at + 3 days` (FR-011) |
| `busy_message_id` | uuid null | set while a message is being answered; a second send gets 409 |

**Lifecycle:** none → open (New agent session) → deleted (replaced after confirmation, or
`closes_at` passed: deleted on the next agent request or by the 15-minute sweep). Deleting a
session cascades to its messages and operations, and sets `agent_usage.session_id` to null.

## 4. `agent_messages`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `session_id` | uuid FK → agent_sessions, cascade | |
| `seq` | int | order within the session |
| `role` | text | `user` or `agent` |
| `content` | text | for `agent`, the final text after figure substitution (research R1) |
| `architecture_id` | uuid null | the architecture open when the user sent it (FR-012); no FK, as the architecture may later be deleted |
| `status` | text | user messages: `accepted`, `answered`, `failed`; agent messages: `complete`, `stopped` |
| `error_kind` | text null | `timeout`, `unreachable`, `bad_output`, `failed`, `session_closed` |
| `is_preview` | bool | user messages: whether it used a preview input |
| `created_at` | timestamptz | |

Unique (`session_id`, `seq`).

## 5. `agent_operations`

The activity log (FR-024, Principle VII).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `session_id` | uuid FK → agent_sessions, cascade | |
| `message_id` | uuid FK → agent_messages, cascade | the user message it answered |
| `seq` | int | order within the message |
| `name` | text | one of the operations in research R9 |
| `inputs` | jsonb | as validated (for example `{"duration": "1_month"}`) |
| `outcome` | text | `ok` or `error` |
| `summary` | jsonb | short result: total, counts, error reason; never the full price list |
| `snapshot` | jsonb null | `{provider: {date, revision}}` behind any figure |
| `figures_removed` | int | money amounts the model wrote itself that were removed (research R1) |
| `started_at`, `duration_ms` | timestamptz, int | |

## 6. `agent_usage`

One row per model call (research R7). Kept when the session is deleted (FR-013).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → users, cascade | |
| `session_id` | uuid FK → agent_sessions, **set null** | |
| `message_id` | uuid null | no FK (the message may be deleted) |
| `created_at` | timestamptz | index with `user_id`; month queries use UTC |
| `provider`, `model` | text | as configured at the time |
| `input_tokens`, `output_tokens` | int | from the provider; 0 if it didn't report |
| `cost_usd` | numeric(12,6) | tokens × the rates at the time; 0 for `ollama` |
| `counts_as_input` | bool | true on the first call for an accepted user message |
| `is_preview` | bool | the input was a preview input |

**Derived values (UTC calendar month):**

- user's inputs this month = count of `counts_as_input` rows for the user;
- spend this month = sum of `cost_usd`;
- reset date = the 1st of next month.

## 7. Preferences: `workspace.agent_panel`

Added to the existing typed account preferences (019), so it follows the user across devices
(clarification 1).

| Field | Type | Validation |
|---|---|---|
| `open` | bool | |
| `split` | float | 0.2–0.8: the canvas's share of the centre column when the panel is open |
| `height` | int null | ≥ 120 px; the panel's own height after a corner resize |
| `width` | int null | ≥ 320 px; the panel's own width after a corner resize |

## 8. Evaluation case (file, not a table)

`backend/tests/agent_evals/cases/<id>.yaml` (research R8):

| Field | Meaning |
|---|---|
| `id`, `title` | `GC-1` … |
| `architecture` | a seeded standard architecture by provider and name, or an inline small one |
| `messages` | the user messages, in order |
| `expect.operations` | operations that must be called (subset, in any order) |
| `expect.figures` | `{duration, total \| service}` values that must appear, equal to the engine's to the cent |
| `expect.contains` / `expect.not_contains` | phrases (case-insensitive) |
| `expect.refused` | true when the request must be declined |
| `script` | the scripted model turns used in the default (no-network) run |

# Contract: Agent API

All routes are under `/api/v1`, use the existing `Authorization: Bearer <user-id>` header, and
are defined with Pydantic models so the OpenAPI schema and the generated TypeScript types stay
in sync (Principle IV). Error bodies use the existing `{"detail": …}` shape unless shown.

## User routes

### `GET /agent/status`

What the panel needs to decide whether to render and what to show. Guests get
`{"available": false, "reason": "guest"}` and the panel is never rendered.

```json
{
  "enabled": true,                // agent on globally; false → no panel (clarification 4)
  "available": false,             // this user can send a message now
  "reason": "user_limit",         // null | guest | agent_off | unavailable | preview_used | user_limit | global_cap
  "resets_on": "2026-12-01",      // for user_limit and global_cap only
  "preview_inputs_left": 0,       // shown while the user is on the preview
  "on_preview": false,
  "session": { "id": "…", "started_at": "…", "closes_at": "…" } // or null
}
```

`unavailable` means the agent is on but can't run (for example a hosted provider with no key or
rates). The message says why only (clarification 4).

### `POST /agent/session`

Start a new session. Body: `{"replace": true|false}`. If a session exists and `replace` is
false → `409 {"detail": "session_exists"}` (the panel then asks the user to confirm). With
`replace: true`, the old session is deleted and a new one returned. `201` with the session.

### `GET /agent/session`

The open session with its messages in order, or `404` if none (an expired session is deleted
first). Each message: `id, role, content, status, error_kind, is_preview, created_at,
architecture_id`.

### `POST /agent/session/messages` → `text/event-stream`

Body: `{"content": "…" (1–4000 chars), "architecture_id": "…" | null}`.

Before streaming, the request is checked and the input accepted (research R6). Refusals are
plain JSON, not a stream:

| Status | Body `detail` | When |
|---|---|---|
| 403 | `guest` | not a named user |
| 404 | `no_session` | no open session |
| 409 | `busy` | a message is already being answered in this session |
| 423 | `{reason, resets_on}` | `agent_off`, `unavailable`, `preview_used`, `user_limit`, `global_cap` |

Then the stream, one JSON object per `data:` line:

| `event` | `data` |
|---|---|
| `accepted` | `{message_id, is_preview, preview_inputs_left}` |
| `operation` | `{name, inputs, outcome, summary, snapshot}` as each operation finishes |
| `text` | `{delta}`: answer text as produced, figure references already replaced |
| `status` | `{state: "thinking" \| "running_operation" \| "writing"}` |
| `done` | `{agent_message_id}` |
| `error` | `{kind: "timeout" \| "unreachable" \| "bad_output" \| "failed" \| "session_closed" \| "global_cap", message}` |

A stream always ends with `done` or `error`. After `error`, the user message is stored as
`failed`. The first two events are always `accepted` then `status`, sent before the model is
called, so the user sees a status at once.

The route declares the event models in its OpenAPI `responses` (`200` → `text/event-stream`,
schema: a discriminated union of the event models), so the generated TypeScript types include
them (Principle IV).

### `POST /agent/session/messages/{message_id}/retry` → `text/event-stream`

Re-runs a `failed` user message. Same stream as above; no new input is charged (research R6).
`409` if the message isn't `failed`.

### `GET /agent/session/operations`

The activity log: every operation in the session, in order, with `message_id, name, inputs,
outcome, summary, snapshot, figures_removed, started_at, duration_ms`.

## Admin routes (Admin only, `403` otherwise)

### `GET /admin/agent/settings`

```json
{
  "agent_enabled": false,
  "agent_provider": "ollama",
  "agent_model": null,
  "agent_base_url": "http://localhost:11434",
  "agent_timeout_seconds": 60,
  "agent_global_monthly_cap_usd": "10.00",
  "agent_default_user_monthly_inputs": 100,
  "agent_price_per_input_token_usd": null,
  "agent_price_per_output_token_usd": null,
  "api_key_set": false,
  "spend_this_month_usd": "0.00",
  "resets_on": "2026-12-01"
}
```

Values are the effective ones (database, else environment, else built-in). Never the key.

### `PUT /admin/agent/settings`

Body: the editable fields above (not `api_key_set` or the usage figures). `200` with the new
effective settings, or `422` with the field and reason (for example a negative cap, a timeout
outside 5–600, or `agent_enabled: true` with no model). Nothing is saved on `422`.

### `GET /admin/users` (extended)

Each `AdminUserOut` gains:

```json
{
  "agent_enabled_for_user": false,
  "agent_preview_input_counter": 3,
  "agent_monthly_input_limit": null,
  "agent_effective_monthly_limit": 100,
  "agent_inputs_this_month": 0
}
```

### `PATCH /admin/users/{user_id}/agent`

Body: any of `agent_enabled_for_user`, `agent_preview_input_counter` (≥ 0),
`agent_monthly_input_limit` (≥ 0 or null). Setting `agent_enabled_for_user` to false also sets
`agent_preview_input_counter` to 0. `200` with the updated `AdminUserOut`; `422` on an invalid
value; `404` for a guest or unknown user.

## Preferences (extended)

`WorkspacePreferences` gains `agent_panel: {open, split, height, width} | null` (data-model §7),
through the existing `GET/PATCH /preferences`.

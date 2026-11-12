# Implementation Plan: Agent Foundation (Session, Safe Operations, Model Settings, Limits)

**Branch**: `023-agent-foundation` | **Date**: 2026-11-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/023-agent-foundation/spec.md`

## Summary

A logged-in named user gets an agent panel under the canvas and can ask read-only questions
about the open architecture (contents, cost, cost drivers) and about what they can import.
Technically:

- **Backend agent package** (`src/agent/`): a thin model interface with Anthropic, Ollama and
  scripted clients; our own agent loop (up to 6 tool rounds, a per-call timeout); four
  read-only operations over the existing services; and figure references, so every amount is
  written by the app from the pricing engine, not by the model (research R1, R2, R9).
- **Streaming**: one POST per message returning server-sent events (research R3).
- **Data**: revision 0010 adds `agent_settings`, `agent_sessions`, `agent_messages`,
  `agent_operations`, `agent_usage`, and three columns on `users` (data-model.md).
- **Settings and limits**: settings read from the database at every message, with environment
  defaults; the key only in the environment or SSM; access, preview, per-user and global limits
  checked under a row lock before any model call (research R5, R6).
- **Frontend**: an `AgentPanel` in the centre column with a divider and a corner resize, saved
  in account preferences; an Agent settings section and four new user-table columns on the
  Admin page (research R12, R13).
- **Evaluation**: YAML golden conversations run scripted in the default test run and against
  real models only on request (research R8).

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 5.6 with React 18 (frontend).

**Primary Dependencies**: FastAPI, SQLAlchemy 2 (async) and Alembic, Pydantic 2; new: the
`anthropic` SDK, and `httpx` promoted to a main dependency for the Ollama client. Frontend:
TanStack Query, Radix UI and Tailwind (no new packages).

**Storage**: PostgreSQL (new tables in revision 0010); pricing data unchanged (Parquet via
DuckDB through the existing engine).

**Testing**: pytest (unit, integration with the real Postgres, contract), the scripted model
client for every agent test; Vitest for components; Playwright e2e unchanged with the agent off,
plus one agent e2e with the scripted model behind a test-only provider setting; opt-in
`pytest -m live_model` evaluations.

**Target Platform**: the existing Docker Compose stack (Caddy, FastAPI, Postgres) on a 2 GiB
EC2 instance, and local dev on macOS. In the cloud the agent is off or uses a hosted model.

**Project Type**: web application (`backend/` + `frontend/`).

**Performance Goals**: the first text or status reaches the browser within the timeout setting
(SC-007); otherwise none beyond the existing app.

**Constraints**: no live model calls in the default test run; no model keys in the database or
the browser; no further model calls once any limit is reached; the app unchanged with the agent
off.

**Scale/Scope**: a handful of named users; one session per user; tens of messages per session.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Pricing Data Integrity | Figures come only from `calculate_architecture_price` through operations; the model writes references, model-written money is removed (R1); USD to 2 dp, totals from unrounded values; unpriceable services named; snapshot date shown. | Pass |
| II. Data-Layer Separation | All new data in Postgres; no vendor price stored as source data (the conversation keeps shown text only; operations keep summaries and snapshot dates). | Pass |
| III. Multi-Provider | Operations work for AWS, GCP and Azure architectures through the shared engine; no provider-specific agent code. | Pass |
| IV. Type-Safe Contract | All new routes use Pydantic models; generated TS types regenerated; stream events typed in the schema (as models referenced by an OpenAPI-documented endpoint). | Pass |
| V. Test-First | Tests first for limits, figure rendering, operations, the loop (scripted model) and the migration; no live model in the default run; golden conversations GC-1–GC-7 in the spec and as eval cases. | Pass |
| VI. Simplicity | Two real clients and one test double; no agent framework; MCP server deferred (R9). | Pass |
| VII. Agent acts as the user | Operations take user and architecture from the request; read-only; content passed as tool data; activity log with inputs, outcome and snapshot date. | Pass |
| VIII. Models, cost, secrets | Provider and model by settings; agent off by default and the app unchanged without it; per-user and global limits enforced before every call; key from environment/SSM, never stored or sent. | Pass |

No violations; Complexity Tracking is empty.

**Post-design re-check (after Phase 1):** unchanged, all pass. The one design point to watch is
the stream-event schema (Principle IV): the event payloads are Pydantic models exported in the
OpenAPI components so the frontend reads them through generated types.

## Project Structure

### Documentation (this feature)

```text
specs/023-agent-foundation/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── agent-api.md
│   └── agent-internals.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── agent/                         # new
│   │   ├── __init__.py
│   │   ├── model.py                   # ModelClient protocol, events, build_client
│   │   ├── clients/anthropic.py
│   │   ├── clients/ollama.py
│   │   ├── clients/scripted.py
│   │   ├── operations.py              # the four read-only operations + registry
│   │   ├── figures.py                 # FigureBook, rendering, money filter
│   │   ├── prompt.py                  # system prompt
│   │   ├── loop.py                    # the agent loop
│   │   ├── limits.py                  # access, preview, monthly limits, global cap
│   │   ├── settings_service.py        # effective settings, validation, API key
│   │   └── sessions.py                # sessions, expiry sweep
│   ├── api/agent.py                   # new: user routes, SSE
│   ├── api/admin_agent.py             # new: settings, per-user fields
│   ├── api/admin_users.py             # AdminUserOut gains agent fields
│   ├── api/architectures.py           # importable listing moved to a service function
│   ├── services/importable.py         # new: shared importable listing
│   ├── models/orm.py                  # new tables, user columns
│   ├── models/schemas.py              # agent schemas; WorkspacePreferences.agent_panel
│   ├── config.py                      # AGENT_* defaults, key and key parameter
│   ├── main.py                        # routers; expiry sweep in lifespan
│   └── db/migrations/versions/0010_agent_foundation.py
└── tests/
    ├── unit/test_agent_figures.py, test_agent_limits.py, test_agent_settings.py,
    │   test_agent_loop.py, test_agent_operations.py, test_agent_clients.py
    ├── integration/test_agent_api.py, test_admin_agent_api.py, test_migration_0010.py,
    │   test_agent_sessions.py
    ├── contract/ (agent routes in the OpenAPI snapshot)
    └── agent_evals/
        ├── cases/gc-1.yaml … gc-7.yaml
        ├── test_golden_scripted.py    # default run
        └── test_golden_live.py        # -m live_model, writes the report

frontend/
├── src/
│   ├── components/agent/AgentPanel.tsx, AgentConversation.tsx, AgentActivityLog.tsx,
│   │   AgentSessionHeader.tsx
│   ├── components/admin/AgentSettingsSection.tsx
│   ├── lib/agentStream.ts             # fetch + stream reader → typed events
│   ├── lib/agentPanelLayout.ts        # divider/corner sizes, preference mapping
│   ├── pages/WorkspacePage.tsx        # centre column: canvas, divider, panel
│   ├── pages/AdminPage.tsx            # settings section, user-table columns
│   └── api/client.ts, api/generated/schema.d.ts
└── e2e/agent.spec.ts                  # scripted provider, test-only

deploy/app                             # pass AGENT_ANTHROPIC_API_KEY_PARAMETER when set
docs/features/agent.md                 # new feature page; README index, admin.md, CHANGELOG
```

**Structure Decision**: the existing web-application layout. Agent code is one backend package
so later agent features (02–04) add operations to it without touching the loop or limits.

## Complexity Tracking

None.

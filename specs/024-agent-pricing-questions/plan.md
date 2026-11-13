# Implementation Plan: Agent Pricing Questions and Comparisons (Read-Only)

**Branch**: `024-agent-pricing-questions` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/024-agent-pricing-questions/spec.md`

## Summary

The agent from 023 learns to compare prices:
- a service category across providers (US1);
- the open architecture against one or both other providers (US2);
- a single price (US5).

It's honest about non-equivalent products (US3) and never estimates (US4). Comparisons appear
as an app-drawn table in a Results pane beside the conversation, with CSV download (US6).

Technically:

- **Matching** (`src/agent/matching/`): profiles of catalog products, fixed quality rules, the
  usage conversions allowed by 022's rule, and region guesses. A batch candidate finder serves
  every source product in one call (research R1–R4, R6; clarifications 1–3).
- **Five new read-only operations** in the 023 registry: `find_matches`, `price_matches`,
  `search_products`, `price_products` and `list_regions`.
  - The model picks candidates by reference (`S…` / `C…`) and never names a SKU.
  - Prices come from `calculate_architecture_price` over transient architectures (R5).
  - Differences and percentages are app figures (R7).
- **Results**: migration `0011` adds `agent_results`. A `result` stream event, results in
  `GET /agent/session`, and a server-built CSV route (R8).
- **Frontend**:
  - `AgentPanel` splits into the conversation and an `AgentResultsPane`, with a vertical
    divider (saved in preferences) that stacks below 700 px (R11);
  - result cards in the conversation;
  - Download CSV.
- **Operation time limit and progress**: every operation runs under the agent timeout
  setting. An overrun ends as a tool error and the message still completes. `find_matches`
  reports progress through the status event ("Matching services (12 of 20)…") (R13).
- **Prompt and evaluation**: prompt v024.1; golden conversations GC-1 to GC-8 as eval cases
  `gc-10`–`gc-17`, with new checks (R12).

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 5.6 with React 18.3 (frontend).

**Primary Dependencies**: FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic 2 and DuckDB (via
the existing provider adapters). Frontend: TanStack Query, Radix UI and Tailwind. No new
packages; CSV uses Python's `csv` module.

**Storage**:
- PostgreSQL: the new `agent_results` table (migration 0011), plus one new
  `WorkspacePreferences` field.
- Pricing data: Parquet through DuckDB, read-only and unchanged.

**Testing**:
- pytest, as unit, integration (real Postgres) and contract tests, with provider fixtures for
  AWS, Azure and GCP;
- the scripted model client for every agent test;
- YAML golden conversations, scripted by default and live with `-m live_model`;
- Vitest for components and layout logic;
- Playwright: one new e2e, `agent-results.spec.ts`, using the scripted provider.

**Target Platform**: the existing Docker Compose stack, and local dev on macOS. There's no
deploy until the agent features are done (owner).

**Project Type**: web application (`backend/` + `frontend/`).

**Performance Goals**:
- `find_matches` for a 20-service architecture against 2 targets aims to finish in under 10 s
  on the dev machine (bounded concurrency of 4, R1). This is a target measured in the
  quickstart, not a limit and not a test assertion.
- A comparison fits within 023's 6 rounds per message (FR-009a).
- **Hard limit**: any operation that runs longer than the agent timeout setting (default
  60 s) is stopped and returned to the model as a tool error, so a message can't hang (R13).

**Constraints**:
- no live model calls in the default test run;
- no estimated, converted-by-model or carried-over prices;
- the open architecture is never modified;
- the app is unchanged when the agent is off.

**Scale/Scope**:
- a handful of named users, one session each;
- tens of results per session;
- results of up to about 50 rows × 3 providers.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Pricing Data Integrity | Every amount comes from `calculate_architecture_price` over transient architectures (R5). Differences and percentages are computed by the app from unrounded values and shown as figure references (R7). Usage is converted only by fixed app factors (R4). Anything unconvertible, unpriced or unoffered is "unavailable", with no figure. Snapshot date and revision are shown per provider, and each provider's snapshot is read on its own. | Pass |
| II. Data-Layer Separation | `agent_results` stores a record of what was shown, with each provider's snapshot revision, as `agent_messages.content` already does in 023. It's never read as a price source: every comparison prices afresh from Parquet. No vendor attributes are copied into mapping tables (agent-04's concern). | Pass (see the note below) |
| III. Multi-Provider | Matching works through the shared adapter interface (`search`, `describe`, `price`) with per-provider profile tables. There's no provider-specific logic in operations or the UI, and all three providers can be the source or a target. | Pass |
| IV. Type-Safe Contract | `AgentResultOut`, its event and the preference field are Pydantic models in OpenAPI, and the generated TS types are regenerated. The CSV route is documented with a `text/csv` response. | Pass |
| V. Test-First | Tests come first for profiles, quality rules, usage conversion, the candidate finder (deterministic order), operations (scripted model), the results API and CSV, the migration, and the pane's layout logic. GC-1 to GC-8 are eval cases. No live model runs in the default run. | Pass |
| VI. Simplicity | No new packages, no agent framework, and no mapping store (agent-04). The candidate finder is a ranked search over existing adapters, and the CSV is the standard library. One divider component; `SplitTabPane` isn't stretched to fit. | Pass |
| VII. Agent acts as the user | The operations use the request's user and open architecture, and are read-only. Picks are by reference only, and the model can't raise a quality label. The activity log records inputs, resolved SKUs and snapshots. Assumptions and guesses are stated. | Pass |
| VIII. Models, cost, secrets | No model-specific code. 023's limits apply to every round. A comparison fits in the existing round limit, with no extra model calls. Works with Ollama and Anthropic. | Pass |

**Principle II note**: Principle II forbids "writing derived pricing values into Postgres as if
they were source data". A result row is derived, but it's stored as a record of an answer,
with its provenance (provider, snapshot date, revision). Nothing reads it to price anything.
This is the same judgement 023 made for message text with rendered figures. It's recorded here
so a later feature doesn't reuse `agent_results` as a price cache.

**Post-design re-check (after Phase 1)**: unchanged, all pass. Two design points to watch:
- the quality rules and usage factors are tables that will grow, so each addition needs a
  test (Principle V);
- the CSV and the pane must share one rounding function (SC-008).

## Project Structure

### Documentation (this feature)

```text
specs/024-agent-pricing-questions/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── agent-operations.md
│   ├── agent-api.md
│   └── results-pane-ui.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── agent/
│   │   ├── matching/                    # new
│   │   │   ├── __init__.py
│   │   │   ├── profiles.py              # ProductProfile + per-provider tables (R2)
│   │   │   ├── quality.py               # fixed quality rules + differences (R3)
│   │   │   ├── usage.py                 # allowed unit conversions, GCP/Azure sizing (R4)
│   │   │   ├── regions.py               # nearest-region guesses (R6)
│   │   │   ├── candidates.py            # batch candidate finder, ranking (R1)
│   │   │   └── book.py                  # MatchBook: S…/C… references (R7)
│   │   ├── compare.py                   # new: pricing picks via transient architectures,
│   │   │                                #      differences, result building (R5, R8)
│   │   ├── operations_compare.py        # new: the five operations, registered in the registry
│   │   ├── results.py                   # new: result persistence + CSV writer (R8)
│   │   ├── figures.py                   # percent figures (R7)
│   │   ├── operations.py                # OperationContext gains matches, progress, results
│   │   ├── loop.py                      # MatchBook per message; `result` events; operation
│   │   │                                #   time limit; progress status events (R13)
│   │   └── prompt.py                    # v024.1 (R12)
│   ├── api/agent.py                     # results in session detail; CSV route; result event
│   ├── models/orm.py                    # AgentResult
│   ├── models/schemas.py                # AgentResult* schemas, event, AgentResultsPreferences
│   └── db/migrations/versions/0011_agent_results.py
├── scripts/build_provider_fixtures.py   # rows the new cases need
└── tests/
    ├── unit/test_agent_matching.py, test_agent_quality.py, test_agent_usage_conversion.py,
    │   test_agent_regions.py, test_agent_figures.py (percent), test_agent_results_csv.py
    ├── integration/test_agent_compare_operations.py, test_agent_results_api.py,
    │   test_migration_0011.py, test_preferences.py (agent_results)
    ├── contract/ (OpenAPI snapshot: results, CSV route, event)
    └── agent_evals/cases/gc-10.yaml … gc-17.yaml; runner.py (new checks)

frontend/
├── src/
│   ├── components/agent/AgentPanel.tsx          # conversation | divider | results
│   ├── components/agent/AgentResultsPane.tsx    # new: header, basis, table, footer
│   ├── components/agent/AgentResultCard.tsx     # new
│   ├── components/agent/AgentConversation.tsx   # cards under agent messages
│   ├── components/layout/VerticalSplit.tsx      # new: divider + stacking below 700 px
│   ├── lib/agentResults.ts                      # new: pane state, CSV download, formatting
│   ├── lib/agentStream.ts                       # `result` event
│   └── api/client.ts, api/generated/schema.d.ts
└── e2e/agent-results.spec.ts                    # new, scripted provider

docs/features/agent.md                           # comparisons, Results pane, CSV
docs/features/workspace-and-preferences.md       # saved results split
CHANGELOG.md                                     # Unreleased
```

**Structure Decision**: the existing web-application layout. Matching sits in its own
sub-package of `src/agent/` so agent-04 can replace the candidate source with reviewed mappings
without touching operations, results or the UI.

## Complexity Tracking

None.

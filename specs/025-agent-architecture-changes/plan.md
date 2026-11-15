# Implementation Plan: Agent-Built Architectures (Create and Change)

**Branch**: `025-agent-architecture-changes` | **Date**: 2026-11-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/025-agent-architecture-changes/spec.md`

## Summary

The agent from 023 and 024 learns to propose saved changes:
- create a new architecture (US1);
- change the open architecture, or one the user names (US2);
- import a public architecture as a private copy (US5);
- refine a pending proposal, preview a what-if, and handle several changes at once (US6–US8).

Every change is a **proposal** the user reviews in the Results pane, with the pricing engine's
before and after cost (US3). Nothing is saved until the user accepts; one accepted message can be
undone and redone as a unit (US4).

Technically:

- **One set of edit rules** (`src/services/architecture_rules.py`): the checks the edit routes
  make inline today become functions over an architecture state, used by the routes and by
  proposals (R1).
- **Architecture state** (`src/services/architecture_state.py`): read, fingerprint and apply a
  state that keeps row ids. Accept, undo and redo all apply a state; fingerprints detect manual
  edits and stale proposals (R2, R3).
- **Proposals** (`src/agent/proposals.py`): build the target state from change items, validate
  it, price before and after through `calculate_architecture_price`, compute differences and
  per-change contributions (R5), and run the lifecycle (R6).
- **Seven new operations** (`src/agent/operations_change.py`): `list_my_architectures`,
  `open_architecture`, `find_products`, `find_region_equivalents`, `propose_changes`,
  `propose_new_architecture`, `propose_import`. The model uses references only (R4).
- **API**: `proposal` and `open_architecture` stream events; proposals in `GET /agent/session`;
  `POST /agent/proposals/{id}/accept|reject|undo|redo` (contracts/agent-api.md). Migration `0012`
  adds `agent_proposals` (R11).
- **Frontend**: a proposal view in the Results pane, proposal cards with Undo and Redo, the
  undo-ended notice, and the unsaved-work dialog before opening another architecture (R7, R8).
- **Prompt and evaluation**: prompt v025.1; GC-1 to GC-10 as eval cases `gc-19` to `gc-28` with
  proposal checks and scripted user actions; live runs on Claude Haiku 5.5 only (R10).

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 5.6 with React 18.3 (frontend).

**Primary Dependencies**: FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic 2 and DuckDB through
the provider adapters. Frontend: TanStack Query, Radix UI and Tailwind. No new packages.

**Storage**:
- PostgreSQL: the new `agent_proposals` table (migration 0012). Architecture rows are unchanged;
  collections and connectors already have `deleted_at`, and architectures too (used for undoing a
  creation).
- Pricing data: Parquet through DuckDB, read-only and unchanged.

**Testing**:
- pytest: unit (rules, state, fingerprint, applier, proposal pricing and contributions),
  integration on real Postgres (operations with the scripted model, the proposal API, accept,
  undo and redo exactness, stale and superseded proposals, the migration), contract (OpenAPI);
- the existing edit-route tests unchanged, as the guard for the rules refactor;
- YAML golden conversations `gc-19`–`gc-28`, scripted by default and live with `-m live_model`
  on Claude Haiku 5.5 only;
- Vitest for the proposal view, cards, the notice and the unsaved-work registry and dialog;
- Playwright: one new e2e, `agent-proposals.spec.ts`, with the scripted provider (propose,
  accept, undo, redo, and the manual-edit notice).

**Target Platform**: the existing Docker Compose stack, and local dev on macOS. No deploy until
the agent features are done (owner).

**Project Type**: web application (`backend/` + `frontend/`).

**Performance Goals**:
- building, validating and pricing a proposal of up to 100 change items aims to finish in under
  5 s on the dev machine (a target measured in the quickstart, not a test assertion);
- a proposal fits within 023's 6 rounds per message: one batch search, one proposal, the answer
  (R4);
- accept, undo and redo are single transactions and aim to finish in under 1 s for a standard
  architecture.

**Constraints**:
- nothing is written to architectures before the user accepts (FR-003), checked by tests that
  compare the saved state before and after every proposal path;
- no live model calls in the default test run;
- the model never sends ids or SKUs, only references;
- the app is unchanged when the agent is off; manual editing behaves as before the refactor.

**Scale/Scope**: a handful of named users, one session each; proposals of at most 100 items;
architectures of up to about 50 services.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Pricing Data Integrity | Before and after totals come from `calculate_architecture_price` over the current and target states (R5). Differences, percentages and contributions are app figures from unrounded values, shown through figure references. Unpriceable items are named and totals labelled partial. A stale proposal is re-priced before acceptance. | Pass |
| II. Data-Layer Separation | `agent_proposals` stores states and a cost summary as a record of what was shown, with its snapshot; nothing prices from it (R11 note). Architecture rows stay the only source of saved content. | Pass |
| III. Multi-Provider | Operations, rules and the applier work through the shared adapters and the provider-neutral state. A new architecture can be on any of the three providers; cross-provider translation stays in agent-04. | Pass |
| IV. Type-Safe Contract | Proposal schemas, events and actions are Pydantic models in OpenAPI; the generated TS types are regenerated. | Pass |
| V. Test-First | Tests come first for the rules (against the current route behaviour), state and fingerprint, the applier and undo exactness, proposal pricing and contributions, the operations, the API and the migration. GC-1 to GC-10 are eval cases. Scripted model only in the default run. | Pass |
| VI. Simplicity | No new packages and no agent framework. One applier serves accept, undo and redo; fingerprints replace per-route edit tracking. The rules refactor is the one structural change, and it removes duplication rather than adding a second rule set. | Pass |
| VII. Agent acts as the user | Operations act as the request's user, with ownership checks; the model can't change another user's architecture or name a SKU. Propose then apply: every change is a proposal, saved only on the user's accept, and one message's changes undo as a unit. Architecture text stays data. Accept, reject, undo and redo are in the activity log. | Pass |
| VIII. Models, cost, secrets | No model-specific code; works with Ollama and Anthropic. Proposals fit in the existing round limit. Accept, reject, undo and redo make no model call. Live evaluation runs on Claude Haiku 5.5 only, under the paid-usage rules (SC-006). | Pass |

**Post-design re-check (after Phase 1)**: unchanged, all pass. Points to watch:
- the rules refactor must not change any route's errors or messages; the route tests are the
  guard and stay as they are;
- the state must include every saved field of collections, services and connectors, or undo stops
  being exact: a test compares the state's fields with the ORM columns;
- checking only Haiku means "no feature may require a specific model" rests on the provider-neutral
  code and the scripted tests; other models' results are reported, not required (SC-006).

## Project Structure

### Documentation (this feature)

```text
specs/025-agent-architecture-changes/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── agent-operations.md
│   ├── agent-api.md
│   └── proposal-ui.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── services/
│   │   ├── architecture_rules.py        # new: edit rules over a state (R1)
│   │   ├── architecture_state.py        # new: ArchitectureState, read, fingerprint, apply (R2)
│   │   └── architecture_import.py       # unchanged; reused by import proposals
│   ├── api/collections.py, sku_selections.py, connectors.py, architectures.py
│   │                                    # call architecture_rules; behaviour unchanged
│   ├── agent/
│   │   ├── proposals.py                 # new: build, validate, price, lifecycle (R5, R6)
│   │   ├── operations_change.py         # new: the seven operations (R4)
│   │   ├── operations.py                # A…/V…/K…/P… references in describe output
│   │   ├── loop.py                      # `proposal` and `open_architecture` events
│   │   └── prompt.py                    # v025.1 (R10)
│   ├── api/agent.py                     # proposals in session detail; accept/reject/undo/redo
│   ├── models/orm.py                    # AgentProposal
│   ├── models/schemas.py                # proposal schemas and events
│   └── db/migrations/versions/0012_agent_proposals.py
└── tests/
    ├── unit/test_architecture_rules.py, test_architecture_state.py, test_agent_proposals.py
    ├── integration/test_agent_change_operations.py, test_agent_proposals_api.py,
    │   test_agent_undo_redo.py, test_migration_0012.py
    ├── contract/ (OpenAPI snapshot: proposal routes and events)
    └── agent_evals/cases/gc-19.yaml … gc-28.yaml; runner.py (proposal checks, user actions)

frontend/
├── src/
│   ├── components/agent/AgentResultsPane.tsx    # results and proposals in one sequence
│   ├── components/agent/AgentProposalView.tsx   # new: changes, cost, assumptions, actions
│   ├── components/agent/AgentProposalCard.tsx   # new: card with Undo/Redo and notices
│   ├── components/agent/AgentConversation.tsx   # proposal cards under agent messages
│   ├── components/workspace/UnsavedWorkDialog.tsx # new
│   ├── lib/unsavedWork.ts                       # new: registry the editors report to
│   ├── lib/agentStream.ts                       # `proposal`, `open_architecture` events
│   └── api/client.ts, api/generated/schema.d.ts
└── e2e/agent-proposals.spec.ts                  # new, scripted provider

docs/features/agent.md                           # proposals, accept, undo, redo
docs/features/architectures-and-canvas.md        # creating and changing through the agent
CHANGELOG.md                                     # Unreleased
```

**Structure Decision**: the existing web-application layout. Rules and state are services, not
agent code, because manual editing uses them too; agent-04 (translation) will produce target
states for the same applier.

## Complexity Tracking

None.

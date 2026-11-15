---

description: "Task list for 025 agent-built architectures (create and change)"
---

# Tasks: Agent-Built Architectures (Create and Change)

**Input**: Design documents from `specs/025-agent-architecture-changes/`

**Prerequisites**: plan.md, spec.md (US1–US8, clarifications Q1–Q4 and SC-006), research.md
(R1–R11), data-model.md, contracts/ (`agent-operations.md`, `agent-api.md`, `proposal-ui.md`),
quickstart.md

**Tests**: Included. Constitution Principle V requires tests first for Postgres reads and writes
of user data and for anything that computes a price, and forbids live models in the default run.
Write each test before its implementation and see it fail. Every agent test uses the scripted
model client (`backend/src/agent/clients/scripted.py`).

**Organization**: grouped by user story (spec.md).
- Paths are relative to the repo root.
- Backend commands run from `backend/` with `uv run`; backend tests need
  `PATH=/opt/homebrew/opt/postgresql@18/bin:$PATH`.
- Frontend commands run from `frontend/`.
- Never run a formatter on a whole folder. Format only the files you touch.
- **Paid runs**: no live Anthropic run without an approved estimate (`CLAUDE.md`, "Paid API
  usage"). Live evaluation is Claude Haiku 5.5 only (SC-006).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US8 from spec.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: fixtures and test scaffolding the later phases use.

- [ ] T001 Add the GCP us-central1 products GC-1 needs (an e2 machine, Cloud SQL for PostgreSQL, Cloud Storage standard, a load balancer) and the AWS us-west-2 counterparts of the seeded Active-Standby architecture's services (for replication, GC-2/GC-4) to the provider fixtures via `backend/scripts/build_provider_fixtures.py`, rebuild them, and note the additions in each provider fixture's README under `backend/tests/fixtures/`
- [ ] T002 [P] Add test helpers in `backend/tests/helpers/architectures.py`: build an owned architecture from a compact spec, and `assert_state_equal(a, b)` that compares two `ArchitectureState`s field by field with a readable diff
- [ ] T003 [P] Add an `unsavedWork` test harness stub and fixtures for proposals (one pending change proposal, one accepted create) in `frontend/src/test/fixtures/agentProposals.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: shared edit rules, architecture state, the proposal model, accept and reject, and
the proposal view. Every user story needs these.

**⚠️ CRITICAL**: no user story work can begin until this phase is complete.

### Edit rules (research R1)

- [ ] T004 Write `backend/tests/unit/test_architecture_rules.py`: one test per rule in data-model.md "Validation rules" (provider, region availability, nesting and same-region parent, region lock with content, connector ends, SKU in region, price type, purchase option, provider options, name in use, 100-item cap), each asserting the exact message the edit routes return today
- [ ] T005 Implement `backend/src/services/architecture_rules.py`: the rule functions over an `ArchitectureState` (or the relevant part of it), returning the first failure as `(field, message)`
- [ ] T006 Make `backend/src/api/collections.py`, `backend/src/api/sku_selections.py`, `backend/src/api/connectors.py` and `backend/src/api/architectures.py` call `architecture_rules` instead of their inline checks, with the same HTTP status, field and message; `validate_selection` in `backend/src/services/architecture_service.py` delegates to it. Run `tests/contract/test_collections.py`, `test_collection_nesting.py`, `test_sku_selections.py`, `test_connectors.py`, `test_connector_sku_selection.py`, `test_architectures.py` and `tests/integration/test_us1_*`, `test_us2_connectors.py`, `test_us3_lifecycle.py` unchanged: all must pass

### Architecture state (research R2, R3)

- [ ] T007 Write `backend/tests/unit/test_architecture_state.py`: `read_state` covers every saved column (compare the state's fields with the ORM columns of `Collection`, `SKUSelection`, `DataConnector`, ignoring `updated_at`/`deleted_at`); fingerprints are equal for equal content and differ for any field change, including the name, but not for `is_public`
- [ ] T008 Write `backend/tests/integration/test_architecture_apply_state.py` (real Postgres): `apply_state` adds, changes and removes collections, services and connectors keeping ids and `created_at`; applying a before state after an after state gives `read_state == before` exactly; removed collections and connectors are soft deleted, removed services deleted; one transaction (a failure leaves nothing applied)
- [ ] T009 Implement `backend/src/services/architecture_state.py`: `ArchitectureState` (pydantic), `read_state`, `fingerprint` (SHA-256 of canonical JSON), `apply_state`, and `to_transient(state)` building an unsaved ORM graph for `calculate_architecture_price`

### Proposal storage (data-model.md §4)

- [ ] T010 Write `backend/tests/integration/test_migration_0012.py`: upgrade and downgrade, check constraints on `kind`, `status`, `undo_status`, unique `(session_id, seq)`, cascade delete with the session
- [ ] T011 Add `AgentProposal` to `backend/src/models/orm.py` and migration `backend/src/db/migrations/versions/0012_agent_proposals.py` per data-model.md §4
- [ ] T012 [P] Add `AgentProposalOut`, `ProposalItemOut`, `ProposalCostOut`, `ProposalUndoOut`, the `proposal` and `open_architecture` stream events and the action bodies to `backend/src/models/schemas.py` per contracts/agent-api.md

### Proposal core (research R5, R6)

- [ ] T013 Write `backend/tests/unit/test_agent_proposals.py`: building a target state from change items (adds with `new…` refs, changes, removes, a resize, a rename); validation failure names the item and rule; before and after totals equal `calculate_architecture_price` on the two states; differences and percentages from unrounded totals; by-service and by-region rows; unpriceable items make the total partial; contributions in group order sum exactly to the total difference; no database writes to architecture rows
- [ ] T014 Implement `backend/src/agent/proposals.py`: `build_change_proposal`, `build_new_architecture_proposal`, the cost summary and contributions, figure references for the model, and persistence (`create_proposal` superseding any pending one in the session, one pending at most)
- [ ] T015 Write `backend/tests/integration/test_agent_proposals_api.py` (accept and reject part): accept applies the target state exactly and re-prices; reject changes nothing; accept refused (409) when not pending, when a message is being answered, or when `architecture_id` doesn't match the proposal's; stale proposal: 409 `stale` with re-priced figures, then accept with `confirm_restaled`; no longer valid: 422 with the rule; neither action calls the model nor uses the allowance; a user can't act on another user's proposal (404)
- [ ] T016 Implement accept and reject in `backend/src/agent/proposals.py` and the routes `POST /agent/proposals/{id}/accept` and `/reject` in `backend/src/api/agent.py`; proposals in `GET /agent/session` with computed `stale`; activity-log rows `accept_proposal` and `reject_proposal` (data-model.md §5)
- [ ] T017 Emit the `proposal` stream event from `backend/src/agent/loop.py` when a `propose_*` operation succeeds, and keep a proposal created before an `error`
- [ ] T018 [P] Update the OpenAPI snapshot test in `backend/tests/contract/test_agent_contract.py` for the new routes, schemas and events; regenerate `frontend/src/api/generated/schema.d.ts` with `npm run generate-api-types`

### Evaluation scaffolding (research R10)

- [ ] T019 Extend `backend/tests/agent_evals/runner.py`: a `proposal` expectation (kind, item counts by op, validation passed, every figure equal to the engine's, nothing saved before accept) and scripted `actions` (`accept`, `reject`, `undo`, `redo`, `manual_edit`) run through the service functions, with state checks after each; add runner unit tests in `backend/tests/agent_evals/test_runner_proposals.py`

### Frontend base (contracts/proposal-ui.md)

- [ ] T020 [P] Handle `proposal` and `open_architecture` events in `frontend/src/lib/agentStream.ts`, with tests in `frontend/src/lib/agentStream.test.ts`
- [ ] T021 Write `frontend/src/components/agent/AgentProposalView.test.tsx`: header and status badges, Added/Changed/Removed groups, cost table, partial total and "Not priced", assumptions with "(guess)", Accept/Reject, Accept disabled with the reason when the architecture isn't open or a message is running, stale text and "Accept updated proposal"
- [ ] T022 Implement `frontend/src/components/agent/AgentProposalView.tsx` and show proposals with results in one ◀ ▶ sequence (creation order) in `frontend/src/components/agent/AgentResultsPane.tsx`; accept and reject in `frontend/src/api/client.ts`, invalidating the session and architecture queries
- [ ] T023 [P] Implement `frontend/src/components/agent/AgentProposalCard.tsx` (title, item count, difference or total) and show it under agent messages in `frontend/src/components/agent/AgentConversation.tsx`, with tests in `AgentProposalCard.test.tsx`

**Checkpoint**: rules shared, state exact, a scripted proposal can be shown, accepted and
rejected. User stories can begin.

---

## Phase 3: User Story 1 - Create a new architecture through conversation (Priority: P1) 🎯 MVP

**Goal**: from a description, the agent proposes a complete, priced new architecture; accepting
creates it, private, and opens it.

**Independent Test**: for GC-1 and GC-3 (scripted), the proposal passes the rules, uses only
catalog SKUs, its price equals the engine's, and accepting creates exactly the proposed
architecture.

### Tests for User Story 1

- [ ] T024 [P] [US1] Write `backend/tests/integration/test_agent_change_operations.py` (create part): `find_products` returns up to 5 `C…` candidates per part (1–8 parts) or `none` with the reason; `propose_new_architecture` with references creates a pending `create` proposal; an unknown reference, a name in use, an invalid region or nesting returns a tool error naming the item; the model never receives a SKU or id
- [ ] T025 [P] [US1] Add eval cases `backend/tests/agent_evals/cases/gc-19.yaml` (GC-1: questions, then a priced proposal with real SKUs) and `gc-21.yaml` (GC-3: "use your best defaults", defaults stated, proposal, plus a second conversation where the user declines the questions and the defaults: no proposal, and the answer says what it needs) with scripts
- [ ] T026 [P] [US1] Add a second conversation to `gc-19.yaml` for US1 scenario 4: a requested part the catalog has no SKU for is said and left out of the proposal, never invented

### Implementation for User Story 1

- [ ] T027 [US1] Implement `find_products` and `propose_new_architecture` in `backend/src/agent/operations_change.py` and register them (contracts/agent-operations.md)
- [ ] T028 [US1] Accepting a `create` proposal builds the architecture with `build_architecture` in `backend/src/agent/proposals.py`, private and owned by the user, sets `architecture_id`, and returns it to open (contracts/agent-api.md)
- [ ] T029 [US1] Open the new architecture after accepting a create in `frontend/src/components/agent/AgentProposalView.tsx` (as picking it in the menu does), boxes placed automatically
- [ ] T030 [US1] Prompt v025.1 part 1 in `backend/src/agent/prompt.py`: what the agent can create; propose, never claim to have saved; at most three questions then offer defaults; if the user declines both the questions and the defaults, propose nothing and say what's needed; one batch search then propose; say when the catalog has no SKU; update `backend/tests/unit/test_agent_prompt.py`

**Checkpoint**: US1 works end to end with the scripted model.

---

## Phase 4: User Story 2 - Change an existing architecture (Priority: P1)

**Goal**: the agent proposes additions, changes and removals for the open architecture, or one
the user names, as one pending proposal.

**Independent Test**: for change requests on seeded architectures (scripted GC-2), the proposal
lists exactly the affected items, passes the rules, and accepting gives the described
architecture.

### Tests for User Story 2

- [ ] T031 [P] [US2] Write tests in `backend/tests/unit/test_agent_operations.py` for `A…`/`V…`/`K…` references and the ownership flag in `describe_open_architecture`
- [ ] T032 [P] [US2] Extend `backend/tests/integration/test_agent_change_operations.py` (change part): `propose_changes` with adds, changes, removes and `new…` refs; region equal to the source refused; not the user's architecture refused; more than 100 items refused; `find_region_equivalents` returns the same product in the target region or `none`; `list_my_architectures` with none, one or several matches; `open_architecture` checks ownership and emits the event; a scaled or replicated service keeps its pricing term and purchase option unless the change sets them
- [ ] T033 [P] [US2] Add eval cases `gc-20.yaml` (GC-2: replication questions, then additions with before and after cost and drivers, with the replicated services on the source's term and the answer naming the term), `gc-22.yaml` (GC-4: a component with no replication option in the catalog is said, nothing invented), `gc-23.yaml` (GC-5: cross-region transfer unpriceable, total partial) and `gc-28.yaml` (GC-10: "Set up a Kubernetes cost alert" refused with the list of abilities)
- [ ] T034 [P] [US2] Write `frontend/src/lib/unsavedWork.test.ts` and `frontend/src/components/workspace/UnsavedWorkDialog.test.tsx`: registry reports dirty sources; dialog shows the names, offers only **Save and continue** and **Discard and continue**, ignores Escape, shows a save error and stays

### Implementation for User Story 2

- [ ] T035 [US2] Add references and the ownership flag to `describe_open_architecture` in `backend/src/agent/operations.py`
- [ ] T036 [US2] Implement `list_my_architectures`, `open_architecture`, `find_region_equivalents` and `propose_changes` in `backend/src/agent/operations_change.py`; emit `open_architecture` from `backend/src/agent/loop.py`
- [ ] T037 [US2] Implement `frontend/src/lib/unsavedWork.ts` and register the Service tab (`frontend/src/components/workspace/ServiceConfigPanel.tsx`), the Architecture Editor's name fields (`CollectionsPanel.tsx`) and the connector form with it
- [ ] T038 [US2] Implement `frontend/src/components/workspace/UnsavedWorkDialog.tsx` and, in `frontend/src/pages/WorkspacePage.tsx`, handle `open_architecture`: check unsaved work, show the dialog, save or discard, then open the architecture; on a failed save keep the current one open
- [ ] T039 [US2] Prompt v025.1 part 2 in `backend/src/agent/prompt.py`: changes, replication only through `find_region_equivalents`, say it's opening a named architecture, never change one that isn't the user's; update `backend/tests/unit/test_agent_prompt.py`

**Checkpoint**: US1 and US2 work independently.

---

## Phase 5: User Story 3 - Review the proposal and its cost (Priority: P1)

**Goal**: the proposal shows the changes and the engine's before and after cost by service and
region, what drives it, and what couldn't be priced.

**Independent Test**: for every scripted proposal, each before, after and difference figure equals
the engine's result for the two states.

- [ ] T040 [P] [US3] Extend `backend/tests/unit/test_agent_proposals.py`: a create or import has no before figures; by-region rows for a multi-region change; a removed item's service row has an after of 0 and is listed under Removed
- [ ] T041 [US3] Add the eval check "every proposal figure equals the engine's" to all proposal cases in `backend/tests/agent_evals/runner.py` (SC-001) and the check that the answer names the main cost drivers for GC-2
- [ ] T042 [US3] Complete the cost section of `frontend/src/components/agent/AgentProposalView.tsx`: by service and by region tables, "Total (partial)", "Not priced", duration and snapshot under the table; rounding with 024's shared function

**Checkpoint**: proposals can be reviewed with exact figures.

---

## Phase 6: User Story 4 - Accept, reject, undo, redo (Priority: P1)

**Goal**: one accepted message undoes and redoes as a unit; a manual edit ends undo and the user
is told.

**Independent Test**: accept a many-item proposal, undo, compare with the saved state before
accept (equal); redo, compare with the accepted state (equal).

### Tests for User Story 4

- [ ] T043 [P] [US4] Write `backend/tests/integration/test_agent_undo_redo.py`: undo and redo exactness for change, create and import proposals (create/import: soft delete and restore with the same ids); undo only for the latest accepted proposal; ended by a manual edit (any route: collection, service, connector, rename) with reason `edited`; not ended by making it public or private; ended by a later accepted proposal (`superseded`), by the user deleting the architecture (`deleted`) and by the session ending; 409 while a message is being answered; neither undo nor redo uses the allowance; both work after a limit is reached
- [ ] T044 [P] [US4] Add eval cases `gc-24.yaml` (GC-6: reject, nothing changes), `gc-25.yaml` (GC-7: many changes, accept, undo equals before, redo equals after) and `gc-26.yaml` (GC-8: accept, manual edit, undo unavailable)
- [ ] T045 [P] [US4] Write frontend tests: Undo/Redo on the accepted proposal in `AgentProposalView.test.tsx` and on the card in `AgentProposalCard.test.tsx`; the end-of-undo reasons; the toast shown once when a refetch flips undo to `edited`

### Implementation for User Story 4

- [ ] T046 [US4] Implement undo and redo in `backend/src/agent/proposals.py` (apply the before or after state; create/import soft delete and restore), the undo status computed from fingerprints, and the routes `POST /agent/proposals/{id}/undo` and `/redo` in `backend/src/api/agent.py`, with activity-log rows `undo_proposal` and `redo_proposal`
- [ ] T047 [US4] Expire pending proposals and end undo when the session ends, in `backend/src/agent/sessions.py`
- [ ] T048 [US4] Add Undo/Redo and the end-of-undo text to `AgentProposalView.tsx` and `AgentProposalCard.tsx`, and the one-time toast in `frontend/src/components/agent/AgentPanel.tsx`; undo and redo in `frontend/src/api/client.ts`
- [ ] T049 [US4] Show `accept_proposal`, `reject_proposal`, `undo_proposal` and `redo_proposal` as the user's actions in `frontend/src/components/agent/AgentActivityLog.tsx`, with a test

**Checkpoint**: the P1 safety story is complete: nothing saved without accept, exact undo.

---

## Phase 7: User Story 5 - Import a public architecture through the agent (Priority: P1)

**Goal**: the agent proposes importing a public architecture with "My <name>"; accepting creates
the same private copy as the menu's Import.

**Independent Test**: an import accepted through the agent produces the same copy as the menu's
Import with the same name (SC-005).

- [ ] T050 [P] [US5] Extend `backend/tests/integration/test_agent_change_operations.py` (import part): `propose_import` with an `I…` reference and the default name; several matches listed; name in use refused; accepting gives a state equal to `import_architecture`'s copy (ids aside)
- [ ] T051 [P] [US5] Add eval case `gc-27.yaml` (GC-9: "Import the serverless back-end", proposal "My Serverless Microservices Back-End", accept creates a private copy)
- [ ] T052 [US5] Add `I…` references to `list_importable_architectures` in `backend/src/agent/operations.py`, implement `propose_import` in `backend/src/agent/operations_change.py`, and accept an import through `import_architecture` in `backend/src/agent/proposals.py`
- [ ] T053 [US5] Prompt v025.1 part 3: imports replace 023's "use the menu" answer; update `backend/tests/unit/test_agent_prompt.py` and 023's GC-7 case (`backend/tests/agent_evals/cases/gc-7.yaml`) to expect an import proposal instead of the refusal

**Checkpoint**: all P1 stories work.

---

## Phase 8: User Story 6 - Adjust the proposal in conversation (Priority: P2)

**Goal**: a refinement replaces the pending proposal with an updated, re-priced one that says
what changed.

**Independent Test**: a refinement produces a proposal that differs from the previous one only in
what was asked, with re-priced figures; the earlier one is superseded.

- [ ] T054 [P] [US6] Write tests in `backend/tests/integration/test_agent_change_operations.py`: describing the pending proposal gives `P…` references in a later message; a refinement supersedes the pending proposal; the new one differs only in the refined item
- [ ] T055 [US6] Describe the pending proposal with `P…` references (in `describe_open_architecture` output) and accept `P…` references in `propose_changes` in `backend/src/agent/operations_change.py`; prompt: say what changed; add a refinement turn to `gc-20.yaml` ("make the standby half the size")
- [ ] T056 [US6] Show "Superseded" and link to the newer proposal in `AgentProposalView.tsx`, with a test

---

## Phase 9: User Story 7 - Preview without saving (Priority: P2)

**Goal**: what-ifs are proposals the user doesn't have to accept; another user's public
architecture can't be changed, only imported.

**Independent Test**: a what-if gives a proposal with before and after cost and leaves the
architecture unchanged; a change request on another user's public architecture is refused with an
import offer.

- [ ] T057 [P] [US7] Write tests: a what-if proposal left pending leaves the state unchanged (`test_agent_change_operations.py`); `propose_changes` on a public architecture the user doesn't own returns the "not yours" tool error
- [ ] T058 [US7] Prompt: a what-if is a proposal that won't be saved unless accepted; offer to import a copy of another user's architecture; add a what-if turn and a not-owned turn to `backend/tests/agent_evals/cases/gc-24.yaml`

---

## Phase 10: User Story 8 - Several changes in one request (Priority: P3)

**Goal**: each change's cost contribution is shown, and they add up to the total difference.

**Independent Test**: a request with two distinct changes gives one proposal whose contributions
add up to the total difference.

- [ ] T059 [P] [US8] Add a two-group request to `gc-25.yaml` with a check that the contributions sum to the difference, and a frontend test in `AgentProposalView.test.tsx` for the contributions list (shown only with more than one group, in order)
- [ ] T060 [US8] Show contributions in `AgentProposalView.tsx` and pass them to the model as figure references in `backend/src/agent/proposals.py`

---

## Phase 11: Polish & Cross-Cutting Concerns

- [ ] T061 [P] Write `frontend/e2e/agent-proposals.spec.ts` with the scripted provider: create and accept, change and reject, accept then undo and redo, a manual edit ending undo with the toast, the unsaved-work dialog; run it in the agent Playwright project
- [ ] T062 [P] Update `docs/features/agent.md` (what the agent can change, proposals, accept/reject, undo/redo and when it ends, opening a named architecture, unsaved work) and `docs/features/architectures-and-canvas.md` (creating and changing through the agent); add the 025 line to `CHANGELOG.md` under Unreleased
- [ ] T063 [P] Update `docs/development.md` ("The agent"): the new eval cases, and that 025's live evaluation is Claude Haiku 5.5 only
- [ ] T064 Run the whole backend suite (`uv run pytest`), `uv run ruff check src/ tests/`, `npm test`, `npm run lint`, `npm run build` and `npm run check-api-types`; fix failures
- [ ] T065 Run the quickstart's manual walk-through (quickstart.md §3) with Ollama and record the results, including the proposal-building time for about 100 items and the SC-007 message count, in this file's notes
- [ ] T066 Give the user an estimate for one live run of gc-19 to gc-28 on Claude Haiku 5.5 (calls and cost from the scripted runs' call counts and Haiku's prices) and wait for approval; then run it once with `AGENT_EVAL_APPROVED_USD` set to the approved amount, record pass counts and cost here, and report failing cases with excerpts rather than loosening them (SC-006)

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup. Blocks every story. Within it: T004 → T005 → T006
  (rules); T007/T008 → T009 (state); T010 → T011; T013 → T014; T015 → T016 → T017; T021 → T022.
- **US1 (Phase 3)**: after Foundational. The MVP.
- **US2 (Phase 4)**: after Foundational; independent of US1 except the shared prompt file.
- **US3 (Phase 5)**: after Foundational; builds on the proposal view from T022.
- **US4 (Phase 6)**: after Foundational; uses accept from T016.
- **US5 (Phase 7)**: after Foundational; independent.
- **US6–US8 (Phases 8–10)**: after US2 (refinements and groups are change proposals).
- **Polish (Phase 11)**: after the stories wanted for the release. T066 needs the user's approval.

### Within each story

Tests first and failing; then operations and services; then routes; then the UI; prompt edits
last, since `prompt.py` is shared.

### Parallel opportunities

- Phase 1: T002 and T003.
- Phase 2: T012, T018, T020 and T023 alongside the backend chain once their inputs exist.
- Each story's [P] tests and eval cases together.
- US1, US2, US4 and US5 can proceed in parallel after Phase 2, except for edits to `prompt.py`,
  `operations_change.py` and `proposals.py`, which go one at a time.

## Parallel Example: User Story 4

```bash
Task: "Write backend/tests/integration/test_agent_undo_redo.py"        # T043
Task: "Add eval cases gc-24, gc-25, gc-26"                               # T044
Task: "Write frontend Undo/Redo and toast tests"                         # T045
```

## Implementation Strategy

### MVP first (User Story 1)

1. Phases 1 and 2: shared rules, exact state, proposals with accept and reject.
2. Phase 3: create through conversation.
3. Stop and validate with GC-1 and GC-3 (scripted), then show it.

### Incremental delivery

1. + US2 (changes) and US3 (cost review): the agent can change saved work.
2. + US4 (undo/redo): the safety story; the release shouldn't ship without it.
3. + US5 (import).
4. + US6–US8 as time allows.
5. Polish, then one approved live run on Claude Haiku 5.5.

## Notes

- The rules refactor (T004–T006) is the riskiest step; keep the route tests unchanged and run
  them before moving on.
- Eval case numbering: GC-1 → `gc-19` … GC-10 → `gc-28`, after 024's `gc-18`.
- Commit only when the user runs `/speckit-git-commit`.

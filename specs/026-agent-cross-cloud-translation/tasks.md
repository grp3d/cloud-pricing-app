---

description: "Task list for 026 agent cross-cloud architecture translation"
---

# Tasks: Agent Cross-Cloud Architecture Translation

**Input**: Design documents from `specs/026-agent-cross-cloud-translation/`

**Prerequisites**: plan.md, spec.md (US1–US6, clarifications of 2026-11-19), research.md
(R1–R11), data-model.md, contracts/ (`agent-operations.md`, `agent-api.md`,
`translation-ui.md`), quickstart.md

**Tests**: Included. Constitution Principle V requires tests first for Postgres reads and writes,
DuckDB query logic and anything that computes a price, and forbids live models in the default
run. Write each test before its implementation and see it fail. Every agent test uses the
scripted model client (`backend/src/agent/clients/scripted.py`).

**Organization**: grouped by user story (spec.md).
- Paths are relative to the repo root.
- Backend commands run from `backend/` with `uv run`; backend tests need
  `PATH=/opt/homebrew/opt/postgresql@18/bin:$PATH`.
- Frontend commands run from `frontend/`.
- Never run a formatter on a whole folder. Format only the files you touch.
- **Paid runs**: no live Anthropic run without an approved estimate (`CLAUDE.md`, "Paid API
  usage"). Live evaluation is Claude Haiku 5.5 only (SC-005).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US6 from spec.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: fixtures and helpers the later phases use.

- [ ] T001 Check that the CI pricing fixtures under `backend/tests/fixtures/` hold every SKU of the AWS, GCP and Azure standard-architecture seeds in their regions (`backend/src/db/seed/standard_architectures*.json`), and, for automatic matching, the exact, close and partial-only candidates GC-2 and GC-7 need (an AWS service with three close Azure candidates; one with only partial candidates; one with none). Add any missing rows with `backend/scripts/build_provider_fixtures.py`, rebuild, and note the additions in each fixture README
- [ ] T002 [P] Add `backend/tests/helpers/translation.py`: import an AWS standard architecture as a user's own, read a translation proposal's rows by `where` and label, and assert one row per source service

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: product keys, seed mappings, the `translate` proposal kind and its schemas. Every
user story needs these.

**⚠️ CRITICAL**: no user story work can begin until this phase is complete.

### Product keys (research R2)

- [ ] T003 Write `backend/tests/unit/test_product_keys.py`: for each provider, rows of the same product in two regions of the fixture give the same key and different products give different keys (AWS `USE1-BoxUsage:t4g.xlarge` and `USW2-BoxUsage:t4g.xlarge`; GCP "E2 Instance Core running in Americas" and "… in EMEA"; an Azure meter in eastus and westeurope); `find_by_key(region, key)` returns that region's row, and `None` where the product isn't sold
- [ ] T004 Add `product_key(item)` and `find_by_key(snapshot, region, key, service_code)` to the adapter contract in `backend/src/pricing_data/providers/base.py` and implement them in `aws.py` (service code + `usagetype` without its region prefix + `operation`), `gcp.py` (service id + display name without the reviewed location-word patterns, kept as a module constant with a comment) and `azure.py` (service, product, SKU and meter names), in `backend/src/pricing_data/providers/`

### Seed mappings (research R3, R4)

- [ ] T005 Write `backend/tests/unit/test_seed_mapping_generator.py`: from small AWS and provider rule sets, the generator pairs rules by (architecture, component, figure); the quantity factor is target ÷ AWS quantity; two target lines become parts 1 and 2; distinct targets for one source key, or the same target with a different factor or options, become separate alternatives each with its 022 note, while identical pairs from several architectures are kept once; an omitted figure becomes a "no equivalent" row with its reason; output is sorted and byte-identical across runs
- [ ] T006 Implement the generator in `backend/scripts/standard_architectures/resolver.py` (`to_service_mappings`) and make `backend/scripts/resolve_standard_architectures.py --provider gcp|azure` also write `backend/src/db/seed/service_mappings_<provider>.json` (`{format, version: 1, source_provider, target_provider, snapshots, mappings: [...]}`, fields as data-model.md §1)
- [ ] T007 Run the resolver for GCP and Azure against the local snapshots 022 used, check the standard-architecture seeds and reports are unchanged (byte-identical), and keep the two new `service_mappings_*.json` files beside the other seeds
- [ ] T008 Write `backend/tests/integration/test_migration_0013.py`: upgrade creates `service_mappings` with the constraints of data-model.md §1 and inserts every row of both seed files once; `agent_proposals` accepts kind `translate` and a `translation` value; downgrade removes both; upgrading twice inserts nothing twice
- [ ] T009 Add `ServiceMapping` and `AgentProposal.translation` to `backend/src/models/orm.py`, and write `backend/src/db/migrations/versions/0013_service_mappings.py` (table, kind check, column, seed insert from the two JSON files)
- [ ] T010 Write `backend/tests/integration/test_seed_mappings.py` (round trip, part 1): every seed mapping's target key resolves with `find_by_key` in each region 022 used to exactly the SKU 022 chose; the lookup in `backend/src/agent/matching/mappings.py` returns a source key's alternatives and parts, and "no equivalent" with 022's reason
- [ ] T011 Implement `backend/src/agent/matching/mappings.py`: `seed_mappings(session, source_provider, source_key, target_provider)` and `seed_version(session)`

### Proposal kind and schemas (research R1; contracts/agent-api.md)

- [ ] T012 [P] Add `ProposalKind` `translate`, `TranslationOut`, `MappingRowOut` and `CostDifferenceOut`, and `AgentProposalOut.translation`, in `backend/src/models/schemas.py`; update the OpenAPI snapshot test under `backend/tests/contract/`; regenerate `frontend/src/api/generated/schema.d.ts`
- [ ] T013 Make `create_proposal` and `to_out` in `backend/src/agent/proposals.py` store and return `translation`, and treat `translate` as `create` in accept, reject, undo and redo (no behaviour change yet beyond the kind); extend the existing proposal API tests in `backend/tests/integration/test_agent_proposals_api.py` with a `translate` proposal that accepts, undoes and redoes like a `create`

**Checkpoint**: product keys, seed mappings and the proposal kind exist; user stories can start.

---

## Phase 3: User Story 1 - Translate an architecture to another provider (Priority: P1) 🎯 MVP

**Goal**: the agent proposes a new architecture on GCP or Azure that keeps the original's
collections, nesting and connections, with every service matched or flagged.

**Independent Test**: each AWS standard architecture translated to GCP and to Azure: every source
service is matched or flagged, and the structure equals the original's.

### Tests for User Story 1

- [ ] T014 [P] [US1] Write `backend/tests/unit/test_translation.py` (matching order, R5): a source with a seed mapping is "seeded"; without one, exact or close candidates are "automatic"; several qualifying give `choose` with the default best quality then lowest engine price; only partial candidates give `partial_only` with no default; none gives `no_equivalent`; a seed target not sold in the region gives `not_sold_in_region`; usage carried by the seed factor or 024's `convert`, and machine sizes by 024's rule
- [ ] T015 [P] [US1] Write `backend/tests/integration/test_seed_mappings.py` (round trip, part 2, SC-006): `translate_architecture` for each of the four AWS standard architectures to GCP and Azure with 022's region map gives the same services (service code, SKU, quantity, provider options) per collection as 022's provider seed, and flags each figure 022 left out with 022's reason. Where a source has one alternative, the defaults must reproduce 022; where it has several, pass 022's choice for that architecture as an explicit pick, and assert separately that the default is the best quality, then the lowest price (research R4)
- [ ] T016 [P] [US1] Write `backend/tests/integration/test_agent_translate_operations.py` (part 1): with the scripted model, `find_translation` refuses no architecture (none open), a source already on the target, GCP or Azure sources and several targets (FR-011), over 100 items, and an unknown target region with the nearest as a guess; it guesses regions with `guessed: true`, one per source region, all in one result for a source with two regions (the Active-Standby architecture); it resolves `A…`, `I…` and the open architecture; `propose_translation` without this message's `find_translation` is refused; a proposal keeps collections, nesting, connectors and arrow styles, uses the original's name by default and a given name otherwise, and a public source gives the user's own proposal (US1 scenario 5)

### Implementation for User Story 1

- [ ] T017 [US1] Implement `backend/src/agent/translation.py`: `match_sources(...)` (R5, reusing `compare.architecture_sources`, `matching.candidates.find_candidates`, `matching.usage.convert`, and the seed lookup) and `build_draft(source, matches, regions, term, name)` (the `propose_import` walk with each service replaced by its match, R1)
- [ ] T018 [US1] Implement `find_translation` and `propose_translation` in `backend/src/agent/operations_translate.py` per contracts/agent-operations.md (inputs, refusals, outputs, activity-log summaries), registered in the operation registry; import the module where `operations_change` is imported
- [ ] T019 [US1] Add the translation rules to `backend/src/agent/prompt.py` and set `PROMPT_VERSION = "026.1"`: call `find_translation` first; ask only for target regions (offering the guesses), the term, and choices among equivalents, at most three questions; state assumptions; never pick a partial candidate the user didn't choose
- [ ] T020 [P] [US1] Add a `translation` check to `backend/tests/agent_evals/runner.py` (expected row statuses and origins by source label, `chosen_by_user` rows, partial flag), with a runner unit test beside the existing ones in `backend/tests/agent_evals/`; write eval cases `backend/tests/agent_evals/cases/gc-32.yaml` (GC-1: "Build the equivalent of 'Prod Web' in Azure", regions and term asked, then mapping and difference; `max_questions: 3`, accepted proposal within three user messages, SC-007) and `gc-33.yaml` (GC-2: three valid equivalents, the user chooses), scripted

**Checkpoint**: US1 works with the scripted model: translations are proposed with the right
structure and matches.

---

## Phase 4: User Story 2 - Review the mapping and the cost difference (Priority: P1)

**Goal**: the proposal shows one row per source service and both totals, with the difference on
matched services, its drivers and snapshots, all from the engine.

**Independent Test**: for each translation in the test set, every amount equals the engine's to
the cent and the table has one row per source service.

### Tests for User Story 2

- [ ] T021 [P] [US2] Extend `backend/tests/unit/test_translation.py` (R6): `cost_difference` gives both whole totals from `price_state`, the compared difference and percentage over rows priced on both sides only, the left-out list, at most three drivers by absolute difference, `not_exact` labels, and both snapshots; an unpriceable or left-out row never counts as a saving
- [ ] T022 [P] [US2] Extend `backend/tests/integration/test_agent_translate_operations.py` (part 2, SC-003): for a translated standard architecture, every row amount and total in `translation` equals `calculate_architecture_price` for the source and target states to the cent; figures reach the model only as references

### Implementation for User Story 2

- [ ] T023 [US2] Implement `mapping_rows(...)` and `cost_difference(...)` in `backend/src/agent/translation.py` (data-model.md §3, §4) and store them in the proposal's `translation` from `propose_translation`, with figure references in its output
- [ ] T024 [P] [US2] Write Vitest tests in `frontend/tests/unit/TranslationTable.test.tsx` for the mapping table and difference summary (columns, origin words, reasons on left-out rows, partial labels, "on N matched services", snapshot dates, 2-decimal rounding) per contracts/translation-ui.md
- [ ] T025 [US2] Implement `frontend/src/components/agent/TranslationTable.tsx` and render it from `frontend/src/components/agent/AgentProposalView.tsx` for kind `translate` (heading, regions and term, table, difference, 025's actions); add the translation line to `frontend/src/components/agent/AgentProposalCard.tsx` and its text helper to `frontend/src/lib/agentProposals.ts`, with Vitest cases in the existing card tests

**Checkpoint**: US1 and US2 together give a reviewable translation in the Results pane.

---

## Phase 5: User Story 3 - Doubtful and missing matches are never guessed (Priority: P1)

**Goal**: services with no candidate are flagged and left out; partial matches are used only
when the user chooses one in a later message, and are disclosed.

**Independent Test**: flagged services are absent from the new architecture and its total, the
total is partial, and a chosen partial match is marked "chosen by you" and named in cost answers.

### Tests for User Story 3

- [ ] T026 [P] [US3] Extend `backend/tests/integration/test_agent_translate_operations.py` (part 3, R7): a partial pick in the same message as the `find_translation` that offered it is refused with the "ask first" message; in a later message of the session it is accepted, the row is `chosen_by_user` with its differences, and `service_mappings` is unchanged; a partial pick never offered is refused; a no-equivalent service is left out and the total partial; an already-unpriceable source is flagged on both sides (FR-014)

### Implementation for User Story 3

- [ ] T027 [US3] Record the partial offers in `find_translation`'s activity-log summary and implement the earlier-message check in `propose_translation` (`backend/src/agent/operations_translate.py`), reading the session's earlier `find_translation` entries
- [ ] T028 [P] [US3] Write eval cases `backend/tests/agent_evals/cases/gc-34.yaml` (GC-3: no equivalent, flagged, left out, partial) and `gc-38.yaml` (GC-7: partial offered, user chooses, "chosen by you", named in the cost answer), scripted

**Checkpoint**: no doubtful match is used without the user's choice.

---

## Phase 6: User Story 4 - Accept, reject, undo (Priority: P1)

**Goal**: accept creates the private translated architecture and opens it; reject creates
nothing; undo and redo as 025; the original never changes; stale translations can't be accepted.

**Independent Test**: across accept, undo, redo and reject of each standard architecture's
translation, the original's saved state is identical, and the new architecture exists only
between accept (or redo) and undo.

### Tests for User Story 4

- [ ] T029 [P] [US4] Write `backend/tests/integration/test_agent_translation_api.py`: accept creates a private architecture owned by the user on the target provider with exactly the proposed state and returns `opened`; reject creates nothing; undo removes it and redo restores it; the original's fingerprint is identical after every step (SC-004); `GET /agent/session` marks a translation stale after the source changes, the seed version changes, or either provider's active pricing snapshot date changes, and accept then answers 409 `stale_translation` and sets `expired` (R9); the activity-log entries carry the mapping version and both snapshots (FR-017)

### Implementation for User Story 4

- [ ] T030 [US4] Implement the translation stale check (source fingerprint and mapping version) in `to_out` and `accept` in `backend/src/agent/proposals.py`, and the 409 body in `backend/src/api/agent.py`; add mapping version and snapshots to the proposal action log summaries
- [ ] T031 [US4] Show the stale message without Accept for a stale translation in `frontend/src/components/agent/AgentProposalView.tsx`, and handle the 409 `stale_translation` beside 025's `stale` handling in `frontend/src/lib/agentProposals.ts` (the accept error helper) and `frontend/src/api/client.ts` (`acceptProposal`'s doc comment), with Vitest cases
- [ ] T032 [P] [US4] Write eval case `backend/tests/agent_evals/cases/gc-37.yaml` (GC-6: the user rejects; nothing created; original unchanged), scripted
- [ ] T033 [US4] Write `frontend/e2e/agent-translation.spec.ts` with the scripted provider: translate a standard architecture, see the mapping table, accept (the new architecture opens under the target provider), undo (it closes), redo

**Checkpoint**: the P1 stories are complete: translate, review, honest gaps, safe accept.

---

## Phase 7: User Story 5 - Adjust the translation in conversation (Priority: P2)

**Goal**: the user swaps a match for another candidate; the proposal is replaced and re-priced;
the mapping data is unchanged.

**Independent Test**: refine a pending translation: the old one is superseded, the swapped row
shows the new match, totals equal the engine's, `service_mappings` unchanged.

- [ ] T034 [P] [US5] Extend `backend/tests/integration/test_agent_translate_operations.py` (part 4): a second `propose_translation` in the session supersedes the pending translation; the swapped row and totals update; a pick that isn't one of the source's candidates (another category, or not sold in the region) is refused and the pending proposal is unchanged
- [ ] T035 [US5] Implement superseding the session's pending translation and the candidate-membership check in `propose_translation` (`backend/src/agent/operations_translate.py`, using 025's supersede helper in `backend/src/agent/proposals.py`)

---

## Phase 8: User Story 6 - Answer "which is cheaper?" honestly (Priority: P2)

**Goal**: the agent answers from the two totals with every caveat that applies.

**Independent Test**: for translations with and without left-out services, the answer gives
both totals and names every left-out service and every match that isn't exact.

- [ ] T036 [P] [US6] Extend `backend/tests/unit/test_translation.py`: `propose_translation`'s `caveats` list every left-out or unpriceable service, partial totals, non-exact matches (chosen partial matches named as chosen by the user), guessed regions and a changed term; none for a complete, exact translation
- [ ] T037 [P] [US6] Extend `backend/tests/integration/test_agent_translate_operations.py` (part 5): in a message after the proposal, `describe_translation` returns the pending translation's totals, compared difference, drivers and caveats as figure references equal to the stored record (no new match or price: the catalog search and pricing functions aren't called); a `Q…` reference selects another translation; with none pending it returns the latest; a stale one says so; with no translation in the session it is refused
- [ ] T038 [US6] Implement `caveats` in `backend/src/agent/translation.py` and return them from `propose_translation`; implement `describe_translation` in `backend/src/agent/operations_translate.py` per contracts/agent-operations.md; add the rule to `backend/src/agent/prompt.py` (for a later question about a translation's cost, call `describe_translation`; answer "which is cheaper" from the totals and state every caveat; never present the compared difference as the whole saving when anything was left out)
- [ ] T039 [P] [US6] Write eval cases `backend/tests/agent_evals/cases/gc-35.yaml` (GC-4: reserved source, the term assumed on the target and why) and `gc-36.yaml` (GC-5: in a second message, "So which is cheaper?": `describe_translation`, then totals and caveats), scripted

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T040 [P] Update `docs/features/agent.md` (translation: directions, mapping origins, partial matches chosen by the user, the cost difference on matched services, follow-up cost questions, stale translations) and add a line to `CHANGELOG.md` under Unreleased
- [ ] T041 [P] Note in `docs/development.md` (the agent section) how the seed mappings are generated from 022's rules and that `service_mappings_*.json` is never hand-edited
- [ ] T042 Run the whole backend suite, the frontend unit tests, type-check and lint on touched files, and the e2e suite; record the results in this file
- [ ] T043 Measure quickstart step 9 (find and price a standard architecture's translation in under 10 s) and record it here
- [ ] T044 Give the user the paid-run estimate for GC-32 to GC-38 plus 025's GC-20 and GC-21B on Claude Haiku 5.5 (from 025's T068 and T069 reports), and stop until it is approved; then run only those cases at the approved amount, and record pass/fail, calls and cost here (SC-005)
- [ ] T045 Run the quickstart manual walk-through with the user (steps 1–8), recording what was checked

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup; blocks every story. T003→T004; T005→T006→T007;
  T007→T008→T009; T004 and T009→T010→T011; T012→T013.
- **US1 (Phase 3)**: after Phase 2. MVP.
- **US2 (Phase 4)**: after US1 (needs `propose_translation`).
- **US3 (Phase 5)**: after US1; independent of US2.
- **US4 (Phase 6)**: after US1; the e2e (T033) after US2's view.
- **US5, US6 (Phases 7, 8)**: after US1; US6's caveats use US2's summary.
- **Polish (Phase 9)**: after the stories wanted in this release; T044 needs every eval case.

### Within Each Story

Tests first and failing; then `translation.py`, then operations, then prompt and eval cases,
then the frontend.

### Parallel Opportunities

- T002 beside T001.
- T012 beside T003–T011 (schemas vs keys and seeds).
- US1 tests T014, T015, T016 together; T020 beside T017–T019.
- T024 (frontend tests) beside T021–T023.
- After US1: US3, US4 and US5 can proceed in parallel (different tests; `operations_translate.py`
  edits in T027, T035 and T038 must be sequential).
- US6 tests T036 and T037 together.
- Docs T040 and T041 together.

### Parallel Example: User Story 1

```bash
# Write the three US1 test files together:
Task: "T014 unit tests for matching order in backend/tests/unit/test_translation.py"
Task: "T015 round trip in backend/tests/integration/test_seed_mappings.py"
Task: "T016 operation tests in backend/tests/integration/test_agent_translate_operations.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 and Phase 2 (keys, seeds, migration, proposal kind).
2. Phase 3: translations proposed with correct structure and matches; the seed round trip passes.
3. Stop and validate with the scripted model.

### Incremental Delivery

1. + US2: the mapping table and cost difference in the Results pane.
2. + US3: partial matches by the user's choice only.
3. + US4: stale handling and e2e; the P1 set is complete and shippable.
4. + US5, US6: refinement and the honest "which is cheaper".
5. Polish, then the one approved paid run.

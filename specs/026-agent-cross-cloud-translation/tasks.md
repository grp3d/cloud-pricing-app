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

- [X] T001 Check that the CI pricing fixtures under `backend/tests/fixtures/` hold every SKU of the AWS, GCP and Azure standard-architecture seeds in their regions (`backend/src/db/seed/standard_architectures*.json`), and, for automatic matching, the exact, close and partial-only candidates GC-2 and GC-7 need (an AWS service with three close Azure candidates; one with only partial candidates; one with none). Add any missing rows with `backend/scripts/build_provider_fixtures.py`, rebuild, and note the additions in each fixture README
- [X] T002 [P] Add `backend/tests/helpers/translation.py`: import an AWS standard architecture as a user's own, read a translation proposal's rows by `where` and label, and assert one row per source service

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: product keys, seed mappings, the `translate` proposal kind and its schemas. Every
user story needs these.

**⚠️ CRITICAL**: no user story work can begin until this phase is complete.

### Product keys (research R2)

- [X] T003 Write `backend/tests/unit/test_product_keys.py`: for each provider, rows of the same product in two regions of the fixture give the same key and different products give different keys (AWS `USE1-BoxUsage:t4g.xlarge` and `USW2-BoxUsage:t4g.xlarge`; GCP "E2 Instance Core running in Americas" and "… in EMEA"; an Azure meter in eastus and westeurope); `find_by_key(region, key)` returns that region's row, and `None` where the product isn't sold
- [X] T004 Add `product_key(item)` and `find_by_key(snapshot, region, key, service_code)` to the adapter contract in `backend/src/pricing_data/providers/base.py` and implement them in `aws.py` (service code + `usagetype` without its region prefix + `operation`), `gcp.py` (service id + display name without the reviewed location-word patterns, kept as a module constant with a comment) and `azure.py` (service, product, SKU and meter names), in `backend/src/pricing_data/providers/`

### Seed mappings (research R3, R4)

- [X] T005 Write `backend/tests/unit/test_seed_mapping_generator.py`: from small AWS and provider rule sets, the generator pairs rules by (architecture, component, figure); the quantity factor is target ÷ AWS quantity; two target lines become parts 1 and 2; distinct targets for one source key, or the same target with a different factor or options, become separate alternatives each with its 022 note, while identical pairs from several architectures are kept once; an omitted figure becomes a "no equivalent" row with its reason; output is sorted and byte-identical across runs
- [X] T006 Implement the generator in `backend/scripts/standard_architectures/resolver.py` (`to_service_mappings`) and make `backend/scripts/resolve_standard_architectures.py --provider gcp|azure` also write `backend/src/db/seed/service_mappings_<provider>.json` (`{format, version: 1, source_provider, target_provider, snapshots, mappings: [...]}`, fields as data-model.md §1)
- [X] T007 Run the resolver for GCP and Azure against the local snapshots 022 used, check the standard-architecture seeds and reports are unchanged (byte-identical), and keep the two new `service_mappings_*.json` files beside the other seeds
- [X] T008 Write `backend/tests/integration/test_migration_0013.py`: upgrade creates `service_mappings` with the constraints of data-model.md §1 and inserts every row of both seed files once; `agent_proposals` accepts kind `translate` and a `translation` value; downgrade removes both; upgrading twice inserts nothing twice
- [X] T009 Add `ServiceMapping` and `AgentProposal.translation` to `backend/src/models/orm.py`, and write `backend/src/db/migrations/versions/0013_service_mappings.py` (table, kind check, column, seed insert from the two JSON files)
- [X] T010 Write `backend/tests/integration/test_seed_mappings.py` (round trip, part 1): every seed mapping's target key resolves with `find_by_key` in each region 022 used to exactly the SKU 022 chose; the lookup in `backend/src/agent/matching/mappings.py` returns a source key's alternatives and parts, and "no equivalent" with 022's reason
- [X] T011 Implement `backend/src/agent/matching/mappings.py`: `seed_mappings(session, source_provider, source_key, target_provider)` and `seed_version(session)`

### Proposal kind and schemas (research R1; contracts/agent-api.md)

- [X] T012 [P] Add `ProposalKind` `translate`, `TranslationOut`, `MappingRowOut` and `CostDifferenceOut`, and `AgentProposalOut.translation`, in `backend/src/models/schemas.py`; update the OpenAPI snapshot test under `backend/tests/contract/`; regenerate `frontend/src/api/generated/schema.d.ts`
- [X] T013 Make `create_proposal` and `to_out` in `backend/src/agent/proposals.py` store and return `translation`, and treat `translate` as `create` in accept, reject, undo and redo (no behaviour change yet beyond the kind); extend the existing proposal API tests in `backend/tests/integration/test_agent_proposals_api.py` with a `translate` proposal that accepts, undoes and redoes like a `create`

**Checkpoint**: product keys, seed mappings and the proposal kind exist; user stories can start.

---

## Phase 3: User Story 1 - Translate an architecture to another provider (Priority: P1) 🎯 MVP

**Goal**: the agent proposes a new architecture on GCP or Azure that keeps the original's
collections, nesting and connections, with every service matched or flagged.

**Independent Test**: each AWS standard architecture translated to GCP and to Azure: every source
service is matched or flagged, and the structure equals the original's.

### Tests for User Story 1

- [X] T014 [P] [US1] Write `backend/tests/unit/test_translation.py` (matching order, R5): a source with a seed mapping is "seeded"; without one, exact or close candidates are "automatic"; several qualifying give `choose` with the default best quality then lowest engine price; only partial candidates give `partial_only` with no default; none gives `no_equivalent`; a seed target not sold in the region gives `not_sold_in_region`; usage carried by the seed factor or 024's `convert`, and machine sizes by 024's rule
- [X] T015 [P] [US1] Write `backend/tests/integration/test_seed_mappings.py` (round trip, part 2, SC-006): `translate_architecture` for each of the four AWS standard architectures to GCP and Azure with 022's region map gives the same services (service code, SKU, quantity, provider options) per collection as 022's provider seed, and flags each figure 022 left out with 022's reason. Where a source has one alternative, the defaults must reproduce 022; where it has several, pass 022's choice for that architecture as an explicit pick, and assert separately that the default is the best quality, then the lowest price (research R4)
- [X] T016 [P] [US1] Write `backend/tests/integration/test_agent_translate_operations.py` (part 1): with the scripted model, `find_translation` refuses no architecture (none open), a source already on the target, GCP or Azure sources and several targets (FR-011), over 100 items, and an unknown target region with the nearest as a guess; it guesses regions with `guessed: true`, one per source region, all in one result for a source with two regions (the Active-Standby architecture); it resolves `A…`, `I…` and the open architecture; `propose_translation` without this message's `find_translation` is refused; a proposal keeps collections, nesting, connectors and arrow styles, uses the original's name by default and a given name otherwise, and a public source gives the user's own proposal (US1 scenario 5)

### Implementation for User Story 1

- [X] T017 [US1] Implement `backend/src/agent/translation.py`: `match_sources(...)` (R5, reusing `compare.architecture_sources`, `matching.candidates.find_candidates`, `matching.usage.convert`, and the seed lookup) and `build_draft(source, matches, regions, term, name)` (the `propose_import` walk with each service replaced by its match, R1)
- [X] T018 [US1] Implement `find_translation` and `propose_translation` in `backend/src/agent/operations_translate.py` per contracts/agent-operations.md (inputs, refusals, outputs, activity-log summaries), registered in the operation registry; import the module where `operations_change` is imported
- [X] T019 [US1] Add the translation rules to `backend/src/agent/prompt.py` and set `PROMPT_VERSION = "026.1"`: call `find_translation` first; ask only for target regions (offering the guesses), the term, and choices among equivalents, at most three questions; state assumptions; never pick a partial candidate the user didn't choose
- [X] T020 [P] [US1] Add a `translation` check to `backend/tests/agent_evals/runner.py` (expected row statuses and origins by source label, `chosen_by_user` rows, partial flag), with a runner unit test beside the existing ones in `backend/tests/agent_evals/`; write eval cases `backend/tests/agent_evals/cases/gc-32.yaml` (GC-1: "Build the equivalent of 'Prod Web' in Azure", regions and term asked, then mapping and difference; `max_questions: 3`, accepted proposal within three user messages, SC-007) and `gc-33.yaml` (GC-2: three valid equivalents, the user chooses), scripted

**Checkpoint**: US1 works with the scripted model: translations are proposed with the right
structure and matches.

---

## Phase 4: User Story 2 - Review the mapping and the cost difference (Priority: P1)

**Goal**: the proposal shows one row per source service and both totals, with the difference on
matched services, its drivers and snapshots, all from the engine.

**Independent Test**: for each translation in the test set, every amount equals the engine's to
the cent and the table has one row per source service.

### Tests for User Story 2

- [X] T021 [P] [US2] Extend `backend/tests/unit/test_translation.py` (R6): `cost_difference` gives both whole totals from `price_state`, the compared difference and percentage over rows priced on both sides only, the left-out list, at most three drivers by absolute difference, `not_exact` labels, and both snapshots; an unpriceable or left-out row never counts as a saving
- [X] T022 [P] [US2] Extend `backend/tests/integration/test_agent_translate_operations.py` (part 2, SC-003): for a translated standard architecture, every row amount and total in `translation` equals `calculate_architecture_price` for the source and target states to the cent; figures reach the model only as references

### Implementation for User Story 2

- [X] T023 [US2] Implement `mapping_rows(...)` and `cost_difference(...)` in `backend/src/agent/translation.py` (data-model.md §3, §4) and store them in the proposal's `translation` from `propose_translation`, with figure references in its output
- [X] T024 [P] [US2] Write Vitest tests in `frontend/tests/unit/TranslationTable.test.tsx` for the mapping table and difference summary (columns, origin words, reasons on left-out rows, partial labels, "on N matched services", snapshot dates, 2-decimal rounding) per contracts/translation-ui.md
- [X] T025 [US2] Implement `frontend/src/components/agent/TranslationTable.tsx` and render it from `frontend/src/components/agent/AgentProposalView.tsx` for kind `translate` (heading, regions and term, table, difference, 025's actions); add the translation line to `frontend/src/components/agent/AgentProposalCard.tsx` and its text helper to `frontend/src/lib/agentProposals.ts`, with Vitest cases in the existing card tests

**Checkpoint**: US1 and US2 together give a reviewable translation in the Results pane.

---

## Phase 5: User Story 3 - Doubtful and missing matches are never guessed (Priority: P1)

**Goal**: services with no candidate are flagged and left out; partial matches are used only
when the user chooses one in a later message, and are disclosed.

**Independent Test**: flagged services are absent from the new architecture and its total, the
total is partial, and a chosen partial match is marked "chosen by you" and named in cost answers.

### Tests for User Story 3

- [X] T026 [P] [US3] Extend `backend/tests/integration/test_agent_translate_operations.py` (part 3, R7): a partial pick in the same message as the `find_translation` that offered it is refused with the "ask first" message; in a later message of the session it is accepted, the row is `chosen_by_user` with its differences, and `service_mappings` is unchanged; a partial pick never offered is refused; a no-equivalent service is left out and the total partial; an already-unpriceable source is flagged on both sides (FR-014)

### Implementation for User Story 3

- [X] T027 [US3] Record the partial offers in `find_translation`'s activity-log summary and implement the earlier-message check in `propose_translation` (`backend/src/agent/operations_translate.py`), reading the session's earlier `find_translation` entries
- [X] T028 [P] [US3] Write eval cases `backend/tests/agent_evals/cases/gc-34.yaml` (GC-3: no equivalent, flagged, left out, partial) and `gc-38.yaml` (GC-7: partial offered, user chooses, "chosen by you", named in the cost answer), scripted

**Checkpoint**: no doubtful match is used without the user's choice.

---

## Phase 6: User Story 4 - Accept, reject, undo (Priority: P1)

**Goal**: accept creates the private translated architecture and opens it; reject creates
nothing; undo and redo as 025; the original never changes; stale translations can't be accepted.

**Independent Test**: across accept, undo, redo and reject of each standard architecture's
translation, the original's saved state is identical, and the new architecture exists only
between accept (or redo) and undo.

### Tests for User Story 4

- [X] T029 [P] [US4] Write `backend/tests/integration/test_agent_translation_api.py`: accept creates a private architecture owned by the user on the target provider with exactly the proposed state and returns `opened`; reject creates nothing; undo removes it and redo restores it; the original's fingerprint is identical after every step (SC-004); `GET /agent/session` marks a translation stale after the source changes, the seed version changes, or either provider's active pricing snapshot date changes, and accept then answers 409 `stale_translation` and sets `expired` (R9); the activity-log entries carry the mapping version and both snapshots (FR-017)

### Implementation for User Story 4

- [X] T030 [US4] Implement the translation stale check (source fingerprint and mapping version) in `to_out` and `accept` in `backend/src/agent/proposals.py`, and the 409 body in `backend/src/api/agent.py`; add mapping version and snapshots to the proposal action log summaries
- [X] T031 [US4] Show the stale message without Accept for a stale translation in `frontend/src/components/agent/AgentProposalView.tsx`, and handle the 409 `stale_translation` beside 025's `stale` handling in `frontend/src/lib/agentProposals.ts` (the accept error helper) and `frontend/src/api/client.ts` (`acceptProposal`'s doc comment), with Vitest cases
- [X] T032 [P] [US4] Write eval case `backend/tests/agent_evals/cases/gc-37.yaml` (GC-6: the user rejects; nothing created; original unchanged), scripted
- [X] T033 [US4] Write `frontend/e2e/agent-translation.spec.ts` with the scripted provider: translate a standard architecture, see the mapping table, accept (the new architecture opens under the target provider), undo (it closes), redo

**Checkpoint**: the P1 stories are complete: translate, review, honest gaps, safe accept.

---

## Phase 7: User Story 5 - Adjust the translation in conversation (Priority: P2)

**Goal**: the user swaps a match for another candidate; the proposal is replaced and re-priced;
the mapping data is unchanged.

**Independent Test**: refine a pending translation: the old one is superseded, the swapped row
shows the new match, totals equal the engine's, `service_mappings` unchanged.

- [X] T034 [P] [US5] Extend `backend/tests/integration/test_agent_translate_operations.py` (part 4): a second `propose_translation` in the session supersedes the pending translation; the swapped row and totals update; a pick that isn't one of the source's candidates (another category, or not sold in the region) is refused and the pending proposal is unchanged
- [X] T035 [US5] Implement superseding the session's pending translation and the candidate-membership check in `propose_translation` (`backend/src/agent/operations_translate.py`, using 025's supersede helper in `backend/src/agent/proposals.py`)

---

## Phase 8: User Story 6 - Answer "which is cheaper?" honestly (Priority: P2)

**Goal**: the agent answers from the two totals with every caveat that applies.

**Independent Test**: for translations with and without left-out services, the answer gives
both totals and names every left-out service and every match that isn't exact.

- [X] T036 [P] [US6] Extend `backend/tests/unit/test_translation.py`: `propose_translation`'s `caveats` list every left-out or unpriceable service, partial totals, non-exact matches (chosen partial matches named as chosen by the user), guessed regions and a changed term; none for a complete, exact translation
- [X] T037 [P] [US6] Extend `backend/tests/integration/test_agent_translate_operations.py` (part 5): in a message after the proposal, `describe_translation` returns the pending translation's totals, compared difference, drivers and caveats as figure references equal to the stored record (no new match or price: the catalog search and pricing functions aren't called); a `Q…` reference selects another translation; with none pending it returns the latest; a stale one says so; with no translation in the session it is refused
- [X] T038 [US6] Implement `caveats` in `backend/src/agent/translation.py` and return them from `propose_translation`; implement `describe_translation` in `backend/src/agent/operations_translate.py` per contracts/agent-operations.md; add the rule to `backend/src/agent/prompt.py` (for a later question about a translation's cost, call `describe_translation`; answer "which is cheaper" from the totals and state every caveat; never present the compared difference as the whole saving when anything was left out)
- [X] T039 [P] [US6] Write eval cases `backend/tests/agent_evals/cases/gc-35.yaml` (GC-4: reserved source, the term assumed on the target and why) and `gc-36.yaml` (GC-5: in a second message, "So which is cheaper?": `describe_translation`, then totals and caveats), scripted

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T040 [P] Update `docs/features/agent.md` (translation: directions, mapping origins, partial matches chosen by the user, the cost difference on matched services, follow-up cost questions, stale translations) and add a line to `CHANGELOG.md` under Unreleased
- [X] T041 [P] Note in `docs/development.md` (the agent section) how the seed mappings are generated from 022's rules and that `service_mappings_*.json` is never hand-edited
- [X] T042 Run the whole backend suite, the frontend unit tests, type-check and lint on touched files, and the e2e suite; record the results in this file
- [X] T043 Measure quickstart step 9 (find and price a standard architecture's translation in under 10 s) and record it here
- [X] T044 Give the user the paid-run estimate for GC-32 to GC-38 plus 025's GC-20 and GC-21B on Claude Haiku 5.5 (from 025's T068 and T069 reports), and stop until it is approved; then run only those cases at the approved amount, and record pass/fail, calls and cost here (SC-005)
- [X] T045 Run the quickstart manual walk-through with the user (section 3, the [MANUAL] items; it was steps 1–8 before 2026-11-20), recording what was checked
  - 2026-11-21, with the user: items 1 (Prod Web to Azure), 2 (Serverless to GCP) and 3 (accept and undo) done. In item 2 the answer said "Six services have only partial matches" but listed five lines (DynamoDB read and write units merged into one). Fixed in the prompt (026.4): one line per service S…, so a count matches the list; not re-checked on a live model (paid). The europe-west2 guess for eu-west-1 is the nearest region and was accepted as correct.

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

## Coverage

Added 2026-11-20 under constitution 1.3.0 (Principle V). Each acceptance scenario and success
criterion maps to a test, or is `[MANUAL]` in quickstart.md section 3. Backend test files are
under `backend/tests/`, frontend ones under `frontend/`.

| Scenario or criterion | Covered by |
|---|---|
| US1-1 translate: questions, then a proposal | GC-32; `integration/test_agent_translate_operations.py::test_the_proposal_keeps_collections_nesting_and_connectors` |
| US1-2 a guessed region is offered and said | GC-32; `::test_regions_are_guessed_one_per_source_region_in_one_result` |
| US1-3 several valid equivalents: a choice | GC-33; `::test_several_valid_equivalents_are_a_choice_with_the_best_first` |
| US1-4 keeps collections, nesting and connectors | `::test_the_proposal_keeps_collections_nesting_and_connectors` |
| US1-5 a public architecture gives the user's own proposal | `::test_a_public_architecture_gives_the_users_own_proposal` |
| US2-1 one row per service, with match, quality, origin and costs | `unit/TranslationTable.test.tsx`; `integration/test_seed_mappings.py` (round trip) |
| US2-2 both totals and the difference on matched services | `unit/test_translation.py::test_the_difference_is_over_rows_priced_on_both_sides`; `::test_every_amount_equals_the_engine`; `TranslationTable.test.tsx` |
| US3-1 no candidate: flagged, left out, total partial | GC-34; `::test_no_equivalent_is_left_out_and_the_total_partial` |
| US3-2 only partial candidates: offered, left out | GC-37, GC-38; `::test_only_partial_candidates_are_offered_with_no_default` |
| US3-3 a chosen partial match is "chosen by you" | GC-37, GC-38; `::test_a_partial_match_needs_an_earlier_offer`; `unit/test_translation.py::test_not_exact_names_close_and_chosen_partial_matches` |
| US3-4 unpriceable in the original: flagged, never a saving | `unit/test_translation.py::test_the_difference_is_over_rows_priced_on_both_sides` |
| US4-1 reject creates nothing | GC-37; `integration/test_agent_translation_api.py::test_reject_creates_nothing` |
| US4-2 accept creates a private architecture on the target | `test_agent_translation_api.py::test_accept_undo_redo_and_the_original_never_changes`; `e2e/agent.spec.ts` "translate an architecture to Azure…" |
| US4-3 undo and redo | the same API test and browser test |
| US5-1 another valid option replaces the pending translation | GC-33; `::test_a_second_proposal_supersedes_and_a_foreign_pick_is_refused` |
| US5-2 an option that isn't a candidate is refused | `::test_a_second_proposal_supersedes_and_a_foreign_pick_is_refused` |
| US6-1 complete translation: totals and difference | `unit/test_translation.py::test_a_complete_exact_translation_has_no_caveats`; `::test_describe_translation_reads_the_record_in_a_later_message` |
| US6-2 partial translation: caveats, not a whole saving | GC-36, GC-38 (last answer); `unit/test_translation.py::test_caveats_name_everything_a_cost_answer_must_say` |
| FR-002 a seed with no exact or close match doesn't hide a better automatic one (2026-11-20) | `::test_a_better_automatic_match_replaces_a_seeded_partial_one`; `::test_a_seeded_partial_match_stands_when_nothing_better_is_found`; Application Gateway editions: `unit/test_agent_profiles.py::test_application_gateway_v2_editions`, `unit/test_agent_quality.py::test_application_gateway_editions_for_an_application_load_balancer` |
| FR-011 other directions declined | GC-39; `::test_refusals` |
| FR-012 stale translation refused | `test_agent_translation_api.py` (three stale tests); `e2e/agent.spec.ts` "a translation can't be accepted after the original changes"; `unit/translationProposal.test.tsx` |
| SC-001, SC-002 | the US2 and US3 rows above |
| SC-003 amounts equal the engine's | `::test_every_amount_equals_the_engine`; eval translation checks |
| SC-004 the original is unchanged | `test_agent_translation_api.py::test_accept_undo_redo_and_the_original_never_changes`; eval runner's "original is unchanged" check |
| SC-005 golden conversations on Haiku 5.5 | opt-in live run (T044), not a completion gate |
| SC-006 standard architectures reproduce 022 | `integration/test_seed_mappings.py::test_translating_a_standard_architecture_reproduces_022` |
| SC-007 at most 3 messages and under 5 minutes | messages: GC-32 (asks, then proposes in its second message); time: `[MANUAL]` quickstart step 1 |
| plan.md: under 10 s | `::test_a_standard_architecture_is_found_and_priced_in_under_10_seconds` |
| Real snapshots, real model, readability | `[MANUAL]` quickstart section 3 |

`::name` with no file before it means `integration/test_agent_translate_operations.py::name`.

## Results (2026-11-19)

- T033: in `frontend/e2e/agent.spec.ts` (the agent project runs serially), passing.
- T042: backend 1617 passed; frontend unit 647 passed (type-check and lint clean); e2e 25
  passed, 1 skipped; ruff clean.
- T043: find and price a standard architecture's translation, both targets: 0.3–0.6 s on the
  test fixtures, 0.6–1.4 s on the real local data (2026-11-16 snapshots), well under 10 s.
- Found on real data and fixed: Azure lists some meters for both the region and a wider
  geography ("uksouth" and "europe"); the region's own row now wins. Rows nothing tells apart
  (GCP "data transfer from Americas to …" in us-east4) are left out with that reason, not
  "not sold in this region".
- T044 (2026-11-20, Claude Haiku 5.5):
  - Run 1, 9 cases: 3 passed (GC-20, GC-21B, GC-34); 48 calls; $0.100 of $0.25 approved.
  - Run 2, the 6 failed cases: 2 passed (GC-36, GC-38); 32 calls; $0.068 of $0.12 approved.
  - Fixes between the runs (prompt 026.2):
    - propose with the defaults when nothing needs asking;
    - keep the original's name;
    - say "chosen by you";
    - treat counts of executions, messages and the like as quantities, not prices;
    - GC-32's "saved" check now looks for "I saved".
  - Decision after run 2 (user, option A): a seed mapping that is only partial is offered like
    any partial match and left out until the user chooses it. Research R5 said seeded matches
    are used whatever their quality, which contradicted the spec's summary.
  - Changes for option A:
    - matching gives `partial_only` when no seeded alternative is exact or close, and any
      partial pick is "chosen by you";
    - prompt 026.3;
    - GC-32 (12 matched, 4 left out), GC-33 (3 matched, 7 left out; message 2 leaves the
      other partial matches out), GC-35 (adds "Use your defaults.") and GC-37 (adds "Use the
      partial matches.", 6 chosen by you) updated;
    - the 022 round-trip test chooses the partial matches and still reproduces 022 exactly,
      in all 8 cases.
  - Run 3, GC-32, 33 and 35 to 37: 4 passed; 34 calls; $0.071 of $0.10 approved. GC-36
    failed only because the case was out of date: Haiku rightly asked about the partial load
    balancers before proposing, and the case went straight to "So which is cheaper?". GC-36
    now says "Use your defaults." first; this change was checked with the scripted model only.
  - Total paid: $0.239 over 3 runs.
- Fix after the manual walk-through (2026-11-20, user-approved): step 1 offered Azure Load
  Balancer (022's seed, partial: a network load balancer) for the Application Load Balancer and
  never Application Gateway.
  - A seed with no exact or close match no longer hides automatic matching (FR-002 amended,
    spec clarification 2026-11-20, research R5). The seed's other figures for the same service
    follow, so the capacity-unit row no longer carries 022's "Azure Load Balancer" reason.
  - Application Gateway candidates: v2 only (no v1, "for Containers", "Discounted" or WAF
    captcha rows); Standard v2 is exact for an Application Load Balancer, and WAF v2, Basic v2
    and Confidential are close (a new optional `lb_edition` spec).
  - Bug fix: the region-word check matched "apac" inside "capacity"; words now match whole.
  - On the real 2026-11-16 data, two other rows changed by the same rule: Serverless Lambda
    duration → Flex Consumption (exact) and Data Lake Glacier Instant Retrieval → Blob Cold
    ZRS (exact), in place of 022's partial seeds. The test pricing data has no Application
    Gateway, so the round trip (SC-006) still reproduces 022 there.
  - Checked with the scripted model and fixtures only; no paid run.
- Fix after walk-through step 2 (2026-11-20, user-approved; run on the web application to GCP
  with us-east4): transfer between regions (us-east-1 → us-west-2) was a choice of five "exact"
  GCP prices, to Americas, Columbus, Berlin, Bangkok and Kuala Lumpur. A transfer price now has
  a destination (AWS: the destination region; GCP: "to Americas" or one place), and a price
  for another destination is partial ("priced only for transfer to Columbus"). The row is now
  matched to "Virginia to Americas", with no question. Azure's inter-region price names no
  destination and is unchanged. Tests: `unit/test_agent_profiles.py::
  test_transfer_between_regions_has_its_destination`, `unit/test_agent_quality.py::
  test_a_transfer_price_must_be_for_the_destination`, `unit/test_agent_candidate_rules.py::
  test_only_a_transfer_price_for_the_destination_qualifies`. The same run's answer also
  invented an internet transfer the architecture doesn't have: a model error, left to the
  manual judgement (no prompt change).

## Progress note (paused 2026-11-19)

- T001–T032 and T034–T039 done; nothing committed yet.
- T033 (e2e): written in `frontend/e2e/agent.spec.ts` (not a separate file: the agent project
  runs serially), and failing: see `frontend/test-results/agent-translate-an-archite-*`.
  The other 24 e2e tests pass.
- Deviations to record in the docs: T014's matching-order tests are in
  `tests/integration/test_agent_translate_operations.py` (they need the database);
  GC-33 (GC-2) uses the two seeded Azure storage alternatives, since the fixtures have no
  service with three; seed mappings also keep 022's SKU as a first try (`target_sku`), and
  the translation record keeps `snapshot_meta` (date and revision) for the answer footer.
- To do: fix T033; T040–T045 (docs, full test runs, timing, the paid-run estimate, the
  walk-through); update data-model.md (`target_sku`) and the contracts (M…/I… references).

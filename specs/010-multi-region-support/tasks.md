---

description: "Task list for Multi-Region Collections and Region-Grouped Pricing"
---

# Tasks: Multi-Region Collections and Region-Grouped Pricing

**Input**: Design documents from `/specs/010-multi-region-support/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md (all present). This feature touches **both** `backend/` and `frontend/` — see plan.md's Technical Context and Project Structure.

**Tests**: Per Constitution Principle V, test-first applies to: the region-backfill migration, the region-locking logic, `list_available_regions()`, the region-threading through DuckDB query helpers, the region-match `409`s (both on collection creation-with-parent and on `PATCH .../parent_collection_id`), `search_catalog()`'s new `region` param, and `PriceLineItem.region` resolution (all backend pricing/data-relationship logic) — plus the two new/extended frontend pure-logic modules (`regionPricingGroups.ts`, `dropTargetDetection.ts`'s region check), matching the established `lib/`-module convention. `/speckit-analyze` (2026-09-15) found two Foundational tasks initially skipped their paired test-first task (C1, C2 below) — both are corrected in this revision, so every backend pricing/data-relationship task in this file now has a preceding failing-test task. The region-selection dialog, drag-rejection message, diagram region labels, connector arrows, and the label rename are presentational UI, validated live against `quickstart.md` via `claude-in-chrome`, per Principle V's carve-out and 009's precedent.

**Organization**: Tasks are grouped by user story, ordered by priority per spec.md: US1, US2, US3, US7 (P1), then US4, US5, US6, US9 (P2), then US8 (P3). research.md found most stories depend on the Foundational phase's schema/endpoint work but are otherwise isolated to their own files — dependencies between stories are called out explicitly below where they exist (US1→US3/US9 for a real assigned region to nest/label against; US4→US5 share the catalog `region` param plumbing).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1`-`US9`, matching spec.md
- File paths are relative to the repository root and follow plan.md's Project Structure

## Phase 1: Setup

**No tasks.** No new dependencies or project scaffolding are needed — this feature extends the existing `backend/` + `frontend/` split with new files inside already-established directories (see Foundational and per-story phases below).

## Phase 2: Foundational

**Purpose**: The schema, migration, and region-plumbing every user story needs before it can be meaningfully built or tested — must complete before any user story phase starts.

- [ ] T001 [P] Write a failing integration test in `backend/tests/integration/test_region_backfill.py` (new file) for the FR-016 backfill: using Alembic's `command.upgrade`/`command.downgrade` against a scratch schema (or the equivalent mechanism `conftest.py`'s test-DB fixture already supports — check before choosing), seed a `collections` row with `region IS NULL` at the point just before migration `0003_collection_region`, run the upgrade, and assert the row's `region` equals the literal former `settings.aws_pricing_region` value. This is a new test pattern for this repo (research.md notes no existing migration test precedent) — will fail until T002 exists.
- [ ] T002 Create Alembic migration `backend/src/db/migrations/versions/0003_collection_region.py`: add `collections.region` as nullable `String`, `UPDATE collections SET region = '<former settings.aws_pricing_region value>' WHERE region IS NULL` (FR-016 backfill — use the literal current config value), then `alter_column` to `NOT NULL`. Follow `0002_collection_nesting.py`'s structure for the add/index style. Depends on T001.
- [ ] T003 [P] Add `region: Mapped[str]` (NOT NULL) to the `Collection` class in `backend/src/models/orm.py`.
- [ ] T004 [P] Write failing unit test for `list_available_regions()` in `backend/tests/unit/test_regions.py` — asserts it returns the intersection of `region=<code>` partition directories across all 5 tables (`service_dim, product_dim, product_attribute, region_dim, price_fact`) at the latest snapshot date, using the real Parquet data (no mocking, per `test_catalog_search.py`'s convention).
- [ ] T005 Implement `list_available_regions()` in `backend/src/pricing_data/regions.py`, mirroring `snapshot.py`'s `_snapshot_dates()`/`resolve_latest_snapshot_date()` pattern (`Path.iterdir()`, no DuckDB query). Depends on T004.
- [ ] T006 Add `GET /regions` endpoint in `backend/src/api/regions.py` returning `{ "regions": [{ "code": str }] }`; register its router alongside the other routers in the FastAPI app entrypoint. Depends on T005.
- [ ] T007 [P] Write a failing unit test (extend `backend/tests/unit/test_catalog_search.py`, plus a pricing-lookup-focused case alongside the existing pricing unit tests) asserting `_price_fact_path`, `_product_dim_path`, `_service_dim_path`, and their public callers (`search_catalog`, `resolve_attributes`, `lookup_price`, `lookup_reserved_price`, `resolve_units`) require an explicit `region` argument and no longer fall back to `settings.aws_pricing_region`.
- [ ] T008 Thread a required `region: str` parameter through `_price_fact_path` (`backend/src/pricing_data/pricing.py:44`) and `_product_dim_path`/`_service_dim_path` (`backend/src/pricing_data/catalog.py:56,63`) and their public callers listed in T007, removing all reads of `settings.aws_pricing_region` from these paths. Depends on T007.
- [ ] T009 [P] Add `region: str` to `CollectionCreate`/`CollectionOut` and `region: str | None` to `PriceLineItem` in `backend/src/models/schemas.py`.
- [ ] T010 [P] Write failing contract tests in `backend/tests/contract/test_collections.py` for `POST /architectures/{architecture_id}/collections`'s basic region handling (no `parent_collection_id` yet — that's US1): `201` with a valid, currently-available region; `400` when `region` is omitted; `400` when `region` is not in `GET /regions`'s current list.
- [ ] T011 Update `POST /architectures/{architecture_id}/collections` (`backend/src/api/collections.py`) to accept, validate (against T006's `GET /regions` list), and persist a client-supplied `region`. Depends on T003, T006, T009, T010.

**Checkpoint**: Every collection can now be created with an explicit, validated region via the API; pricing/catalog reads are region-parameterized; the migration's backfill behavior is regression-tested. All user story phases below may start. Run `check-api-types` now (Constitution Principle IV) to confirm `CollectionCreate`/`CollectionOut`/`PriceLineItem`'s new fields regenerate cleanly before any story builds on them.

---

## Phase 3: User Story 1 - Assign a region when creating a collection (Priority: P1)

**Goal**: "+Add" in column 2 prompts for a region before creating a VPC or unattached Application; adding an Application while a VPC is selected skips the prompt and inherits that VPC's region.

**Independent Test**: quickstart.md Scenarios 1 and 3.

- [ ] T012 [P] [US1] Write failing contract tests in `backend/tests/contract/test_collections.py`: creating an `application_component` with `parent_collection_id` set ignores any client-supplied `region` and uses the parent VPC's region; `400` if `parent_collection_id` references a non-`vpc` collection.
- [ ] T013 [US1] Extend `POST /architectures/{architecture_id}/collections` (`backend/src/api/collections.py`) to accept `parent_collection_id`, validate it references an existing `vpc`, and override `region` server-side per data-model.md's creation-time resolution. Depends on T011, T012.
- [ ] T014 [P] [US1] Create `RegionSelectDialog.tsx` in `frontend/src/components/workspace/`, using the existing `Dialog` primitive (`frontend/src/components/ui/dialog.tsx`) — a dropdown of regions from `GET /regions`, confirm/cancel.
- [ ] T015 [P] [US1] In `frontend/src/api/client.ts`: extend `createCollection(architectureId, type, name)` to `createCollection(architectureId, type, name, region?, parentCollectionId?)`; add `listRegions()`.
- [ ] T016 [US1] Wire the "+Add" flow in `frontend/src/components/workspace/CollectionsPanel.tsx` / `frontend/src/pages/WorkspacePage.tsx`: show `RegionSelectDialog` before creating a VPC or an unattached Application; when `selectedCollectionId` (`WorkspacePage.tsx:247`) refers to a VPC and the user adds an Application, skip the dialog and pass `parent_collection_id` instead. Depends on T013, T014, T015.
- [ ] T017 [US1] Live-verify quickstart.md Scenarios 1 and 3 via `claude-in-chrome`. Depends on T016.

**Checkpoint**: Every new collection gets a region — chosen explicitly, or inherited when nested at creation.

---

## Phase 4: User Story 2 - A collection's region locks once it has content (Priority: P1)

**Goal**: An empty collection's region is editable; once it has a service (or, for a VPC, a nested Application), it's locked.

**Independent Test**: quickstart.md Scenario 2.

- [ ] T018 [P] [US2] Write failing contract tests in `backend/tests/contract/test_collections.py` for `PATCH /collections/{id}/region`: `200` when the collection has no `SKUSelection` and (for a VPC) no nested Application; `409` when it does.
- [ ] T019 [US2] Implement the `locked(collection)` check (data-model.md) and the new `PATCH /collections/{id}/region` endpoint in `backend/src/api/collections.py`. Depends on T018.
- [ ] T020 [P] [US2] Add `updateCollectionRegion(collectionId, region)` to `frontend/src/api/client.ts`, mirroring `updateCollectionParent`.
- [ ] T021 [US2] Add an editable region control to the selected collection's panel in `frontend/src/components/workspace/CollectionsPanel.tsx`, disabled once locked (surface the `409` as a clear, non-editable state). Depends on T019, T020.
- [ ] T022 [US2] Live-verify quickstart.md Scenario 2 via `claude-in-chrome`. Depends on T021.

**Checkpoint**: Region changes are blocked exactly when content exists, both via the API directly and in the UI.

---

## Phase 5: User Story 3 - Applications can only nest inside same-region VPCs (Priority: P1)

**Goal**: Nesting an Application into a differently-regioned VPC is rejected, both by dragging on the diagram and via the API directly.

**Independent Test**: quickstart.md Scenario 4.

- [ ] T023 [P] [US3] Write a failing integration test in `backend/tests/integration/test_collection_nesting.py` (new file): `PATCH /collections/{id}/parent_collection_id` returns `409` with both regions in the body when the Application's region differs from the target VPC's region.
- [ ] T024 [US3] Implement the region-match check in the `parent_collection_id` update handler in `backend/src/api/collections.py`. Depends on T023.
- [ ] T025 [P] [US3] Write a failing unit test in `frontend/tests/unit/dropTargetDetection.test.ts` for `decideNestingChange` rejecting a region-mismatched nest.
- [ ] T026 [US3] Extend `decideNestingChange` (`frontend/src/pages/dropTargetDetection.ts:19-28`) to accept the dragged Application's region and each candidate VPC's region, and reject on mismatch. Depends on T025.
- [ ] T027 [US3] In `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`'s `onNodeDragStop` (`:1065-1146`), wire a visible rejection message on a T026 rejection and handle the T024 `409` from `onUpdateCollectionParent`. Depends on T024, T026.
- [ ] T028 [US3] Live-verify quickstart.md Scenario 4 via `claude-in-chrome`. Depends on T027.

**Checkpoint**: No architecture can end up with a region-mismatched nesting, enforced client- and server-side.

---

## Phase 6: User Story 7 - Pricing breakdown grouped and subtotaled by region (Priority: P1)

**Goal**: Column 5's per-SKU breakdown is grouped into region sections with subtotals, Total and Data Timestamp unmoved.

**Independent Test**: quickstart.md Scenario 8.

- [ ] T029 [P] [US7] Write a failing unit test (alongside the existing pricing-calculation test file, e.g. `backend/tests/unit/test_price_calculation.py`) asserting each `PriceLineItem.region` resolves to its owning Collection's region, or (for a Connector-owned selection) to `from_collection.region` — including one defensive case asserting the fallback `region: None` path behaves correctly if a selection is ever ownerless (documented in research.md as expected-unreachable today, but still locked in by a test).
- [ ] T030 [US7] Implement that resolution in `calculate_architecture_price` (`backend/src/services/price_calculation.py:68-99,173-183`), alongside the existing `selection_components` lookup. Depends on T009, T029.
- [ ] T031 [P] [US7] Write a failing unit test in `frontend/tests/unit/regionPricingGroups.test.ts` for a pure grouping function: given tagged line items, returns `{region, items, subtotal}[]` preserving price-descending order within each group, with a `"Global"` fallback group for items with `region: null`.
- [ ] T032 [US7] Implement `frontend/src/lib/regionPricingGroups.ts`. Depends on T031.
- [ ] T033 [US7] Update `PricingPanel.tsx`'s `PricePerSkuSection` (`:227-276`) to render one section per `regionPricingGroups.ts` group (reusing the existing `PriceLine` row, `:285-312`), between the unmoved `Total` (`:130`) and `Data Timestamp` (`:170-172`) lines. Depends on T030, T032.
- [ ] T034 [US7] Live-verify quickstart.md Scenario 8 via `claude-in-chrome`. Depends on T033.

**Checkpoint**: A multi-region architecture's pricing breakdown reads as region sections with subtotals; a single-region architecture still shows one labeled section. Run `check-api-types` again now that `PriceLineItem.region` is live end-to-end, rather than waiting until Polish.

---

## Phase 7: User Story 4 - Service search is scoped to the selected collection's region (Priority: P2)

**Goal**: Catalog search results only ever match the selected collection's region.

**Independent Test**: quickstart.md Scenario 5.

- [ ] T035 [P] [US4] Write failing unit tests in `backend/tests/unit/test_catalog_search.py` for `GET /catalog/skus`'s new required `region` query param, distinct from the existing `from_region_code`/`to_region_code` AWSDataTransfer filters.
- [ ] T036 [US4] Add the required `region` query param to `GET /catalog/skus` (`backend/src/api/catalog.py:13-37`) and pass it through to the already-region-aware `search_catalog()` (its signature was already updated by T008 in Foundational — this task is the endpoint-level plumbing only, not a second change to `search_catalog()` itself). Depends on T008, T035.
- [ ] T037 [P] [US4] Add the required `region` param to `searchCatalog(...)` in `frontend/src/api/client.ts:113-119`.
- [ ] T038 [US4] Pass the selected collection's region into every `searchCatalog` call in `frontend/src/components/CatalogSearchPanel.tsx`. Depends on T036, T037.
- [ ] T039 [US4] Live-verify quickstart.md Scenario 5 via `claude-in-chrome`. Depends on T038.

**Checkpoint**: Search results always match the selected collection's region.

---

## Phase 8: User Story 5 - Connector service search and creation follow the "from" collection's region (Priority: P2)

**Goal**: A Connector's service search uses its "from" collection's region; the column-2 select-two-collections connect flow sets from/to by selection order; the pre-existing explicit "Add Connector" From/To designation (FR-007) still works once region-scoping is layered on top.

**Independent Test**: quickstart.md Scenario 6 (parts 1, 2, 4).

- [ ] T040 [US5] Locate and implement first-selected-is-"from"/second-selected-is-"to" behavior for the column-2 two-collection connect action (grep `frontend/src/components/workspace/CollectionsPanel.tsx` and `WorkspacePage.tsx` for the existing connect-selection handling referenced in spec.md FR-008).
- [ ] T041 [US5] Pass `from_collection.region` into the Connector-scoped catalog search inside `AddConnectorDialog` (`frontend/src/components/workspace/ArchitectureDiagramPanel.tsx:521-610`). Depends on T036.
- [ ] T042 [US5] Live-verify quickstart.md Scenario 6 (parts 1, 2, 4) via `claude-in-chrome` — explicitly re-confirm FR-007's pre-existing explicit From/To designation in `AddConnectorDialog` still works correctly now that its service search is region-scoped (T041), not just the new column-2 selection-order behavior (T040). Depends on T040, T041.

**Checkpoint**: Connector service search always resolves via the "from" side, for both connector-creation flows, and the pre-existing explicit From/To picker is confirmed unaffected.

---

## Phase 9: User Story 6 - Connectors display a directional arrow (Priority: P2)

**Goal**: Every connector renders with an arrow pointing from "from" to "to".

**Independent Test**: quickstart.md Scenario 6 (part 3).

- [ ] T043 [US6] Add `markerEnd: { type: MarkerType.ArrowClosed }` to the edge object built in `rawEdges` (`frontend/src/components/workspace/ArchitectureDiagramPanel.tsx:935-981`) — `OffsetEdge` already forwards `markerEnd` to `<BaseEdge>` (`:454,475,502`), it just has no value today.
- [ ] T044 [US6] Live-verify quickstart.md Scenario 6 (part 3) via `claude-in-chrome`. Depends on T043.

**Checkpoint**: Connector direction is visible at a glance on every connector, independent of any other story.

---

## Phase 10: User Story 9 - Region label shown on collection boxes in the diagram (Priority: P2)

**Goal**: VPC boxes always show their region in the bottom-right corner; Application boxes do too, only while unnested.

**Independent Test**: quickstart.md Scenario 7.

- [ ] T045 [US9] Add a `region`-name label (`absolute bottom-1 right-1 ...`) inside `VpcNode`'s existing `relative` wrapper (`frontend/src/components/workspace/ArchitectureDiagramPanel.tsx:386-429`).
- [ ] T046 [US9] Add the same label to `ApplicationComponentNode` (`:324-365`), conditional on `!parent_collection_id`. Same file as T045 — sequential, not parallel.
- [ ] T047 [US9] Live-verify quickstart.md Scenario 7 via `claude-in-chrome`. Depends on T045, T046.

**Checkpoint**: Region is visible on every collection box exactly where the spec says, and disappears from a nested Application as expected.

---

## Phase 11: User Story 8 - "Application Components" is relabeled "Applications" (Priority: P3)

**Goal**: Every user-facing "Application Component(s)" string now reads "Application(s)".

**Independent Test**: quickstart.md Scenario 10.

- [ ] T048 [P] [US8] Replace "Application Component"/"Application Components" with "Application"/"Applications" in `frontend/src/components/workspace/CollectionsPanel.tsx`'s type selector and any other occurrence found via `grep -r "Application Component" frontend/src`.
- [ ] T049 [US8] Live-verify quickstart.md Scenario 10 via `claude-in-chrome`. Depends on T048.

**Checkpoint**: No user-facing "Application Component" text remains.

---

## Phase 12: Polish & Cross-Cutting Concerns

- [ ] T050 [P] Run the full backend (`pytest`) and frontend (`vitest`) suites; confirm green.
- [ ] T051 Run `check-api-types` (Constitution Principle IV) one final time to confirm generated TypeScript types match every schema change in contracts/api.md — this is the comprehensive final gate; T011's and T033's checkpoints already caught drift incrementally.
- [ ] T052 Run all 10 quickstart.md scenarios end-to-end via `claude-in-chrome` in one sitting, on a single multi-region architecture.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: None — no tasks.
- **Foundational (Phase 2)**: No dependencies — BLOCKS every user story phase (T001-T011 must all complete first).
- **User Stories (Phase 3-11)**: All depend on Foundational. Beyond that:
  - US3 (Phase 5) and US9 (Phase 10) are most meaningfully tested once US1 (Phase 3) exists (a UI-created, intentionally-chosen region), though their own API/unit tests can be written and run against Foundational alone.
  - US5 (Phase 8) shares `region`-param catalog plumbing with US4 (Phase 7, T036) — implement T036 before T041.
  - US2, US4, US6, US7, US8 have no dependency on any other story beyond Foundational.
- **Polish (Phase 12)**: Depends on all desired user stories being complete.

### Within Each User Story

- Tests (where included, per Principle V) MUST be written and FAIL before their paired implementation task.
- Backend endpoint/logic before the frontend API-client change that calls it.
- API-client change before the UI wiring that uses it.
- Live-verification task last, after all of that story's implementation tasks.

### Parallel Opportunities

- Foundational: T001 first (nothing else touches the DB); T002 depends on it. T003, T004, T007, T009 can run in parallel with each other (distinct files, no dependency on an incomplete task). T005→T006 and T007→T008 are each sequential pairs. T010 (contract test) can run in parallel with T003/T004/T007/T009; T011 depends on T003, T006, T009, T010.
- Every story's initial test task(s) marked [P] can run in parallel with that story's *other* [P] setup task (e.g. T012 with T014/T015).
- Once Foundational completes, US1, US2, US4, US6, US7, US8 can all start in parallel (if staffed) — US3 and US9 are better started after US1 lands (see above), US5 after US4's T036.

---

## Parallel Example: User Story 1

```bash
# Launch US1's independent starting tasks together:
Task: "Write failing contract tests for parent_collection_id inheritance in backend/tests/contract/test_collections.py"
Task: "Create RegionSelectDialog.tsx in frontend/src/components/workspace/"
Task: "Extend createCollection/add listRegions in frontend/src/api/client.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (CRITICAL — blocks everything).
2. Complete Phase 3: User Story 1.
3. **STOP and VALIDATE**: quickstart.md Scenarios 1 and 3.
4. Every subsequently-created collection now has a real, user-chosen (or inherited) region — the foundation the rest of the feature builds on.

### Incremental Delivery

1. Foundational → US1 (assign region) → US2 (lock) → US3 (same-region nesting) → US7 (region-grouped pricing) — the four P1 stories, each independently demoable.
2. Then US4 (region-scoped search) → US5 (connector region/direction) → US6 (arrows) → US9 (diagram labels) — the P2 stories.
3. Then US8 (label rename) — P3, purely cosmetic, safe to do any time after Foundational.

### Parallel Team Strategy

With multiple developers, after Foundational:
- Developer A: US1 → US3 (both touch collection creation/nesting)
- Developer B: US2 → US7 (both touch region attribution/locking on the backend, then pricing)
- Developer C: US4 → US5 → US6 → US9 (diagram + search surface)
- Developer D: US8 (independent, any time)

---

## Notes

- [P] tasks touch different files with no dependency on an incomplete task.
- [Story] label maps each task to its user story for traceability.
- Test tasks are test-first per Constitution Principle V for backend pricing/data-relationship logic and frontend `lib/`-module pure logic; everything else is live-verified per quickstart.md.
- Commit after each task or logical group.
- Stop at any checkpoint to validate a story independently.

---

description: "Task list for Nest Application Components into VPCs"
---

# Tasks: Nest Application Components into VPCs

**Input**: Design documents from `/specs/002-vpc-component-nesting/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md
(all present). Builds directly on the completed `001-assemble-price-aws-architecture`
implementation — no new infrastructure, only additive changes to existing files.

**Tests**: Included, per Constitution Principle V (test-first for Postgres logic and the API
layer). The two new DB `CHECK` constraints are schema-layer, added in Foundational alongside the
column (mirroring how `001`'s analogous constraints were built), then verified by a dedicated
test in this feature's own Phase 2 — matching the precedent `001`'s `T065` set. Frontend drag
gesture code is exercised via a small extracted pure function (`dropTargetDetection.ts`) so the
actual decision logic is unit-testable without needing to simulate real React Flow drag physics.

**Organization**: This feature is a single user story (spec.md P1), so there is one story phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1` for the one user story phase
- File paths are relative to the repository root and follow `plan.md`'s Project Structure

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: The schema change every other task in this feature depends on

**⚠️ CRITICAL**: No User Story 1 work can begin until this phase is complete

- [x] T001 Add `parent_collection_id` (nullable FK to `collections.id`, `ON DELETE SET NULL`)
      plus the two `CHECK` constraints — `ck_collection_parent_only_app_component`
      (`parent_collection_id IS NULL OR type = 'application_component'`) and
      `ck_collection_no_self_parent` (`parent_collection_id != id`) — to the `Collection` ORM
      model in `backend/src/models/orm.py`
- [x] T002 Generate and apply the Alembic migration for T001's schema change in
      `backend/src/db/migrations/versions/0002_collection_nesting.py` (depends on T001)
- [x] T003 [P] Add `parent_collection_id` to `CollectionOut` and a new
      `CollectionNestingUpdate` request schema (`parent_collection_id: uuid.UUID | None`) in
      `backend/src/models/schemas.py` (depends on T001)

**Checkpoint**: Schema and contract types exist — User Story 1 work can now begin

---

## Phase 2: User Story 1 - Organize Application Components inside a VPC (Priority: P1) 🎯 MVP

**Goal**: A user can nest an Application Component into a VPC, move it between VPCs, or un-nest
it back to top-level, all via drag-and-drop on the existing assembly canvas — with no effect on
its SKUs, its pricing inputs, its Data Connectors, or the Architecture's calculated total.

**Independent Test**: Create an Architecture with one VPC and one Application Component (with a
SKU already added), drag the Application Component onto the VPC, and verify it renders nested
inside while its SKUs and the Architecture's calculated total are unchanged (per
`quickstart.md`).

### Tests for User Story 1 ⚠️

> Write these tests FIRST; ensure they FAIL before implementation (Constitution Principle V)

- [x] T004 [P] [US1] Unit tests for the two new DB `CHECK` constraints — an Application
      Component's `parent_collection_id` may reference a VPC, a VPC's `parent_collection_id`
      must always be `NULL`, and a Collection can never be its own parent — in
      `backend/tests/unit/test_collection_nesting_constraints.py`
- [x] T005 [P] [US1] Add a test case proving price calculation is unaffected by nesting (an
      Architecture's total is identical whether or not an Application Component is nested
      inside a VPC) to `backend/tests/unit/test_price_calculation.py`
- [x] T006 [P] [US1] Contract test for `PATCH /collections/{id}` — nest, move to a different
      VPC, un-nest, reject nesting a VPC as a child (`400`), reject a `parent_collection_id`
      that doesn't reference an existing non-deleted VPC in the same Architecture (`400`),
      `404` for a nonexistent/foreign Collection, and idempotency (setting the same value
      twice) — in `backend/tests/contract/test_collection_nesting.py`
- [x] T007 [US1] Integration test for the full nest → move → un-nest → reject-VPC-in-VPC →
      nest-again → delete-the-VPC-and-confirm-the-child-survives-un-nested flow (per
      `quickstart.md`) in `backend/tests/integration/test_us1_nest_components.py`

### Implementation for User Story 1

- [x] T008 [US1] In `backend/src/services/architecture_service.py`: add a validate-and-set-parent
      helper (the target `parent_collection_id`, when non-null, must reference an existing,
      non-deleted `type = 'vpc'` Collection in the same Architecture as the Collection being
      nested — spec FR-001, FR-002) and extend the existing `soft_delete_collection` cascade to
      also set `parent_collection_id = NULL` on every non-deleted child of a VPC being deleted,
      in the same transaction as its existing Data Connector cascade (spec FR-007) (depends on
      T001)
- [x] T009 [US1] Implement `PATCH /collections/{id}` using T008's helper, returning `400` for
      the two rejection cases and `404` for an unowned/nonexistent/deleted Collection, per
      `contracts/api.md`, in `backend/src/api/collections.py` (depends on T003, T008)
- [x] T010 [P] [US1] Add a pure function computing which VPC node (if any) a dropped
      Application Component node's position overlaps, given the current node list, in
      `frontend/src/pages/dropTargetDetection.ts`
- [x] T011 [P] [US1] Unit tests for T010's helper (no overlap, overlaps its current VPC —
      no-op, overlaps a different VPC — move, was nested but now overlaps nothing — un-nest) in
      `frontend/tests/unit/dropTargetDetection.test.ts`
- [x] T012 [P] [US1] Add an `updateCollectionParent` call (`PATCH /collections/{id}`) to
      `frontend/src/api/client.ts`, and regenerate the OpenAPI-derived types
      (`npm run generate-api-types`) against the running backend from T009 (depends on T009)
- [x] T013 [US1] In `frontend/src/pages/CreateArchitecturePage.tsx`: give nested Application
      Component nodes `parentId` (deliberately without `extent: 'parent'` — see `research.md`
      #1, it would block dragging back out to un-nest), style VPC nodes as containers, and on
      `onNodeDragStop` use T010's helper plus T012's API call to nest/move/un-nest, invalidating
      the architecture query on success (depends on T010, T012)
- [x] T014 [US1] Run the `quickstart.md` validation script end-to-end (API steps plus the
      frontend smoke check) (depends on T007, T013)

**Checkpoint**: User Story 1 is fully functional and independently testable — this is the whole
feature.

---

## Phase 3: Polish & Cross-Cutting Concerns

- [x] T015 [P] Confirm the existing type-drift CI gate
      (`frontend/package.json`'s `check-api-types`, from `001`) fails on the schema drift this
      feature introduces until T012's regeneration is committed, then passes once it is — no
      code change expected beyond what T012 already produced; this task is verification only
- [x] T016 Run the full existing regression suite from `001-assemble-price-aws-architecture`
      (backend `pytest`, frontend `vitest` + `tsc -b` + `eslint` + `build`) to confirm this
      feature introduces no regression

---

## Phase 4: Convergence

- [x] T017 Add a test deleting a *nested* Application Component and asserting its containing
      VPC and any sibling Collections are unaffected, in
      `backend/tests/integration/test_us1_nest_components.py` (or a new test in
      `backend/tests/contract/test_collections.py`), per FR-008 (partial)
- [x] T018 Add a test creating a Data Connector involving a nested Application Component, then
      nesting/moving/un-nesting that component, asserting the connector (and its attached SKU,
      if any) is unchanged throughout, in `backend/tests/integration/test_us1_nest_components.py`,
      per FR-010 / SC-002 (partial)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately. BLOCKS User Story 1.
- **User Story 1 (Phase 2)**: Depends on Foundational only.
- **Polish (Phase 3)**: Depends on User Story 1 being complete.

### Within User Story 1

- Backend contract/unit/integration tests (T004-T007) are written first and must fail before
  their corresponding implementation (T008-T009) — Principle V.
- The frontend drop-target-detection helper and its tests (T010-T011) have no backend
  dependency and can proceed in parallel with the backend tests/implementation.
- T012 (API client + type regeneration) depends on T009 existing and running, since it
  regenerates types from the live schema.
- T013 (the actual canvas wiring) depends on both T010 (the helper it calls) and T012 (the API
  call and types it uses).

### Parallel Opportunities

- T003 can run in parallel with T002 (both depend only on T001).
- T004, T005, T006 (backend tests) can all run in parallel with each other.
- T010, T011 (frontend helper + its tests) can run in parallel with the entire backend test/
  implementation sequence (T004-T009), since neither depends on the other.
- T015 can run in parallel with T016.

---

## Parallel Example: User Story 1

```bash
# Launch the backend tests together:
Task: "Unit tests for the two new DB CHECK constraints in backend/tests/unit/test_collection_nesting_constraints.py"
Task: "Price-unaffected-by-nesting test case in backend/tests/unit/test_price_calculation.py"
Task: "Contract test for PATCH /collections/{id} in backend/tests/contract/test_collection_nesting.py"

# In parallel with the above, the frontend helper and its tests:
Task: "Drop-target-detection helper in frontend/src/pages/dropTargetDetection.ts"
Task: "Unit tests for the helper in frontend/tests/unit/dropTargetDetection.test.ts"
```

---

## Implementation Strategy

Since this feature is a single user story, there is no separate "MVP vs. later stories" framing
— completing Phase 1 + Phase 2 delivers the whole feature. Phase 3 (Polish) is a verification
pass, not additional scope.

1. Complete Phase 1: Foundational (schema + contract types)
2. Complete Phase 2: User Story 1 (tests, then backend, then frontend, then quickstart)
3. **STOP and VALIDATE**: run `quickstart.md` independently
4. Complete Phase 3: Polish (CI gate + full regression confirmation)

---

## Notes

- [P] tasks touch different files with no unmet dependency
- Commit after each task or logical group; verify each test fails before implementing against it
- This feature deliberately introduces zero new tables, services, or dependencies — see
  `research.md` for why the existing patterns from `001` (cascade function, two-layer
  validation, React Flow's built-in parent/child nodes) were reused rather than building new
  ones (Constitution Principle VI)

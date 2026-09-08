---

description: "Task list for Service Selection Improvements"
---

# Tasks: Service Selection Improvements

**Input**: Design documents from `/specs/003-service-selection-improvements/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md
(all present). Builds directly on the completed `001-assemble-price-aws-architecture` and
`002-vpc-component-nesting` implementations — no new infrastructure, no schema change, only
additive/enrichment changes to existing files.

**Tests**: Included, per Constitution Principle V (test-first for the batched-unit-lookup logic
and DuckDB read enrichment) and matching `002`'s precedent of extracting pure, DOM-independent
frontend logic (`nodeLayout.ts`, mirroring `dropTargetDetection.ts`) so it's directly
unit-testable.

**Organization**: Tasks are grouped by the four user stories in `spec.md` (US1/US2 are P1, US3
is P2, US4 is P3). There is no separate Setup or Foundational phase — this feature has no shared
cross-story prerequisite (no schema change, and each story's backend/frontend work is otherwise
independent of the others' — see Dependencies below for the one real exception, US4 building on
US3's height-estimation function).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1`-`US4`, matching `spec.md`
- File paths are relative to the repository root and follow `plan.md`'s Project Structure

## Phase 1: User Story 1 - See what a service actually is before selecting it (Priority: P1) 🎯

**Goal**: Catalog search results and the SKU-selected confirmation step show enough descriptive
detail that a user knows what they're choosing, with a clear fallback when a SKU has none.

**Independent Test**: Search for a service family with several similar results, and verify each
result — and the one currently selected — shows distinguishing descriptive detail beyond a name
and one summary line (per `quickstart.md`).

### Tests for User Story 1 ⚠️

> Write these tests FIRST; ensure they FAIL before implementation (Constitution Principle V)

- [ ] T001 [P] [US1] Unit test for a `parse_attributes` helper — valid JSON → a plain dict,
      `None`/empty/malformed input → `{}` (never an error) — in `backend/tests/unit/test_catalog.py`
      (new file)
- [ ] T002 [P] [US1] Contract test: `GET /catalog/skus` results include a non-empty `attributes`
      map for a SKU known to have rich attributes (e.g. an EC2 Compute Instance), and `{}` (not
      `null`) for one known to be sparse, in `backend/tests/contract/test_catalog.py`

### Implementation for User Story 1

- [ ] T003 [US1] Add `attributes: dict[str, str]` to `CatalogSKUOut` in
      `backend/src/models/schemas.py`
- [ ] T004 [US1] Implement `parse_attributes` and extend `search_catalog` to populate
      `attributes` per result in `backend/src/pricing_data/catalog.py` (depends on T003; makes
      T001/T002 pass)
- [ ] T005 [US1] Regenerate the OpenAPI-derived frontend types (`npm run generate-api-types`)
      against the running backend (depends on T004)
- [ ] T006 [P] [US1] Create `SkuDetail.tsx` — a generic attributes key/value display with a "no
      additional details available" empty state (spec FR-003) — in
      `frontend/src/components/SkuDetail.tsx` (depends on T005)
- [ ] T007 [US1] Wire `SkuDetail` into the SKU-selected confirmation step in both places it
      appears — `frontend/src/pages/CreateArchitecturePage.tsx` (adding a SKU to a Collection)
      and `frontend/src/components/DataConnectorPanel.tsx` (attaching a SKU to a Connector)
      (depends on T006)
- [ ] T008 [US1] Enrich `CatalogSearchPanel`'s per-row detail line using a short summary derived
      from `attributes` (candidate keys per `research.md` #2) in
      `frontend/src/components/CatalogSearchPanel.tsx` (depends on T005)
- [ ] T009 [US1] Run the `quickstart.md` validation for richer SKU detail (API steps 1 and 4,
      plus frontend smoke-check item 1) (depends on T007, T008)

**Checkpoint**: User Story 1 is fully functional and independently testable.

---

## Phase 2: User Story 2 - Know the unit a quantity is measured in (Priority: P1) 🎯

**Goal**: Every place a usage quantity is entered or shown displays that SKU's real billing
unit.

**Independent Test**: Select a SKU, open its pricing inputs, and verify the usage-quantity field
shows that SKU's actual unit; edit an already-added SKU Selection and verify the unit shows
there too (per `quickstart.md`).

### Tests for User Story 2 ⚠️

- [ ] T010 [P] [US2] Unit test for a batched `resolve_units` lookup — multiple SKUs resolved in
      one call, a SKU with no `price_fact` row resolves to `None` without failing the others —
      in `backend/tests/unit/test_pricing_units.py` (new file)
- [ ] T011 [P] [US2] Contract test: `GET /catalog/skus` results, `POST`/`PATCH
      .../sku-selections` responses, and `POST .../connectors/{id}/sku-selection` responses all
      include a correct `unit` — extend `backend/tests/contract/test_catalog.py`,
      `test_sku_selections.py`, and `test_connector_sku_selection.py`
- [ ] T012 [US2] Integration test: `GET /architectures/{id}`'s nested `sku_selections` each
      carry the correct `unit`, proving the batched tree-level resolution (not per-row) works —
      in `backend/tests/integration/test_unit_resolution.py` (new file)

### Implementation for User Story 2

- [ ] T013 [US2] Add `unit: str | None` to `CatalogSKUOut` and `SKUSelectionOut` in
      `backend/src/models/schemas.py`
- [ ] T014 [US2] Implement the batched `resolve_units` lookup in `backend/src/pricing_data/pricing.py`
      (depends on T013; makes T010 pass)
- [ ] T015 [US2] Extend `search_catalog` to include `unit` per result in
      `backend/src/pricing_data/catalog.py` (depends on T014)
- [ ] T016 [US2] Attach `unit` in the `POST`/`PATCH .../sku-selections` responses in
      `backend/src/api/sku_selections.py` (depends on T014)
- [ ] T017 [US2] Attach `unit` in the `POST .../connectors/{id}/sku-selection` response in
      `backend/src/api/connectors.py` (depends on T014)
- [ ] T018 [US2] Add a shared "attach units to a response tree" helper in
      `backend/src/services/architecture_service.py` and use it in `GET /architectures/{id}` in
      `backend/src/api/architectures.py` (depends on T014; makes T012 pass)
- [ ] T019 [US2] Regenerate the OpenAPI-derived frontend types against the running backend
      (depends on T015, T016, T017, T018)
- [ ] T020 [US2] Show the SKU's unit alongside the usage-quantity field, accepting a `unit`
      prop, in `frontend/src/components/PricingInputsForm.tsx` (depends on T019)
- [ ] T021 [US2] Pass the picked/editing SKU's `unit` into `PricingInputsForm` from
      `frontend/src/pages/CreateArchitecturePage.tsx` and
      `frontend/src/components/DataConnectorPanel.tsx` (depends on T020)
- [ ] T022 [US2] Run the `quickstart.md` validation for units (API steps 1-3, plus frontend
      smoke-check item 2) (depends on T016, T017, T018, T021)

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 3: User Story 3 - Application Components show what they contain (Priority: P2)

**Goal**: An Application Component's box on the canvas lists its contained services and
automatically grows or shrinks to fit them.

**Independent Test**: Add several services to an Application Component and verify its box lists
them and grows to fit; remove one and verify it shrinks back down; create an empty one and
verify a small empty state (per `quickstart.md`).

### Tests for User Story 3 ⚠️

- [ ] T023 [P] [US3] Unit tests for `estimateComponentHeight` — zero services → a small default
      height, N services → `baseHeight + N * rowHeight` — in
      `frontend/tests/unit/nodeLayout.test.ts` (new file)

### Implementation for User Story 3

- [ ] T024 [US3] Implement `estimateComponentHeight` in `frontend/src/pages/nodeLayout.ts` (new
      file; makes T023 pass)
- [ ] T025 [US3] Create a custom Application Component node type — rendering its name and its
      SKU Selections (or an empty state when it has none), sized via
      `estimateComponentHeight` — and register it via React Flow's `nodeTypes` prop in
      `frontend/src/pages/CreateArchitecturePage.tsx` (depends on T024)
- [ ] T026 [US3] Run the `quickstart.md` validation for Application Component auto-resize
      (frontend smoke-check item 3) (depends on T025)

**Checkpoint**: User Stories 1-3 all work independently.

---

## Phase 4: User Story 4 - Manually resize Component and VPC boxes (Priority: P3)

**Goal**: Users can manually resize a VPC or Application Component box on the canvas, with a VPC
never shrinking below what its nested children need.

**Independent Test**: Drag a VPC box's resize handle and verify it resizes; do the same for an
Application Component box; verify a manually-shrunk VPC grows back to fit a newly-nested child
(per `quickstart.md`).

### Tests for User Story 4 ⚠️

- [ ] T027 [P] [US4] Unit tests for `estimateVpcHeight` — sums its children's
      `estimateComponentHeight` results plus the VPC's own header/spacing — in
      `frontend/tests/unit/nodeLayout.test.ts` (extends T023's file; depends on T024 existing)

### Implementation for User Story 4

- [ ] T028 [US4] Implement `estimateVpcHeight` in `frontend/src/pages/nodeLayout.ts`, and update
      `CreateArchitecturePage.tsx`'s VPC height computation to use it in place of `002`'s fixed
      50px-per-child formula (depends on T024; makes T027 pass)
- [ ] T029 [US4] Attach React Flow's `NodeResizer` to the VPC node type (`minWidth`/`minHeight`
      from `estimateVpcHeight`, satisfying spec FR-011) and to the Application Component node
      type (minimums from `estimateComponentHeight`) in
      `frontend/src/pages/CreateArchitecturePage.tsx` (depends on T025, T028)
- [ ] T030 [US4] Run the `quickstart.md` validation for manual resize, including the VPC
      minimum-size guard (frontend smoke-check item 4) (depends on T029)

**Checkpoint**: All four user stories are independently functional.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T031 [P] Confirm the existing type-drift CI gate (`001`) catches this feature's
      `attributes`/`unit` schema additions until committed, then passes once staged — same
      verification pattern as `002`'s T015; no code change expected beyond T005/T019's
      regeneration
- [ ] T032 Run the full existing regression suite from `001`/`002` (backend `pytest`, frontend
      `vitest` + `tsc -b` + `eslint` + `build`) to confirm this feature introduces no regression

---

## Dependencies & Execution Order

### Story Dependencies

- **User Story 1 (P1)**: No dependency on other stories.
- **User Story 2 (P1)**: No dependency on other stories. Independent of US1 (different backend
  fields, different frontend components), though both regenerate frontend types — sequence
  their `generate-api-types` steps (T005, T019) rather than running them concurrently to avoid
  clobbering each other's in-progress regeneration.
- **User Story 3 (P2)**: No dependency on other stories.
- **User Story 4 (P3)**: Depends on User Story 3 — `estimateVpcHeight` (T028) sums each child's
  `estimateComponentHeight` (T024), and `NodeResizer`'s VPC minimums (T029) need that VPC height
  to already be computable. This is the one real cross-story dependency in this feature.
- **Polish**: Depends on all four user stories being complete.

### Parallel Opportunities

- T001, T002 (US1 tests) in parallel with each other.
- T010, T011 (US2 tests) in parallel with each other; both can also run in parallel with US1's
  tasks entirely (different files throughout), as long as the two `generate-api-types` steps
  (T005, T019) are sequenced rather than concurrent.
- T023 (US3 test) can start as soon as US1/US2 are done or in parallel with them (no shared
  files).
- T031, T032 (Polish) in parallel with each other.

---

## Parallel Example: User Stories 1 and 2 backend tests

```bash
# US1 and US2 backend tests touch entirely different files and can run together:
Task: "Unit test for parse_attributes in backend/tests/unit/test_catalog.py"
Task: "Contract test for catalog attributes in backend/tests/contract/test_catalog.py"
Task: "Unit test for resolve_units in backend/tests/unit/test_pricing_units.py"
Task: "Contract test for unit fields in backend/tests/contract/test_sku_selections.py"
```

---

## Implementation Strategy

### Incremental Delivery

1. User Story 1 → validate independently → demo (richer selection detail)
2. User Story 2 → validate independently → demo (visible units) — MVP-equivalent for this
   feature's P1 pair, since both US1 and US2 address the same "informed selection" theme
3. User Story 3 → validate independently → demo (components show their contents)
4. User Story 4 → validate independently → demo (manual resize, building on US3)
5. Polish → final regression pass against all four stories

---

## Notes

- [P] tasks touch different files with no unmet dependency
- Commit after each task or logical group; verify each story's tests fail before implementing
  against them
- This feature deliberately introduces zero new tables, endpoints, or dependencies — see
  `research.md` for why the existing patterns from `001`/`002` (batched DuckDB resolution,
  React Flow's built-in `NodeResizer`, extracted pure layout functions) were reused rather than
  building new ones (Constitution Principle VI)

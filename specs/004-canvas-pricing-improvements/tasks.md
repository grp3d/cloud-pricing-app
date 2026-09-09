---

description: "Task list for Canvas & Pricing Improvements"
---

# Tasks: Canvas & Pricing Improvements

**Input**: Design documents from `/specs/004-canvas-pricing-improvements/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md
(all present). Builds directly on the completed `001`-`003` implementations — no new
infrastructure, no schema change, only additive/enrichment changes to existing files.

**Tests**: Included, per Constitution Principle V (test-first for the duration-proration math,
billing-unit classification, and component-association logic — all pure/isolable financial
logic) and matching `002`/`003`'s precedent of extracting pure, DOM-independent frontend logic
so it's directly unit-testable.

**Organization**: Tasks are grouped by the five user stories in `spec.md` (US1/US2/US3 are P1,
US4/US5 are P2). There is no separate Setup or Foundational phase — no schema change, and each
story's backend/frontend work is otherwise independent — see Dependencies below for the two real
cross-story touch-points (US3 extends the same `price_calculation.py` rewrite US1 starts; US4
and US5 both extend `CreateArchitecturePage.tsx` after US2's `Handle`/multi-select changes land
there).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1`-`US5`, matching `spec.md`
- File paths are relative to the repository root and follow `plan.md`'s Project Structure

## Phase 1: User Story 1 - See a trustworthy total for a specific timeframe (Priority: P1) 🎯

**Goal**: A duration selector (1 day / 1 month / 1 year) next to Calculate scopes the whole
Architecture's total, with each service's contribution prorated per its pricing term and
billing unit — never guessed.

**Independent Test**: Build an Architecture mixing an on-demand service and a 1-year Reserved
service, calculate at each duration, and verify the total changes accordingly (per `quickstart.md`).

### Tests for User Story 1 ⚠️

> Write these tests FIRST; ensure they FAIL before implementation (Constitution Principle V)

- [X] T001 [P] [US1] Unit test for `classify_unit()` — known `no_period` strings (Hrs/Minute/
      Requests-family), known `fixed_period` strings (Month/GB-Mo-family) return the right
      classification with the right `period_days`, and an unrecognized string returns
      `unrecognized` — in `backend/tests/unit/test_duration.py` (new file)
- [X] T002 [P] [US1] Unit tests for the duration-proration math in `calculate_architecture_price`
      — a Reserved-term selection's cost prorates by `duration_days / term_days` (FR-002); a
      `no_period`-unit on-demand selection's cost scales by `duration_days` directly (FR-003); a
      `fixed_period`-unit on-demand selection's cost scales by `duration_days / period_days`
      (FR-004); an `unrecognized`-unit on-demand selection is excluded from the total and listed
      (FR-005) — in `backend/tests/unit/test_price_calculation.py` (extend)
- [X] T003 [P] [US1] Contract test: `POST /architectures/{id}/calculate` accepts a `duration`
      query param, echoes it back as `duration` in the response, and defaults to `1_month` when
      omitted — in `backend/tests/contract/test_calculate.py` (extend)
- [X] T004 [US1] Integration test: an Architecture mixing a Reserved-term and an on-demand
      service, calculated at `1_day`/`1_month`/`1_year`, produces three different totals matching
      the proration rules — in `backend/tests/integration/test_duration_pricing.py` (new file)

### Implementation for User Story 1

- [X] T005 [US1] Add `CalculationDuration` enum and `CalculationResult.duration` field in
      `backend/src/models/schemas.py`
- [X] T006 [US1] Implement `classify_unit()` and the billing-unit lookup table in
      `backend/src/pricing_data/duration.py` (new file; depends on T005; makes T001 pass)
- [X] T007 [US1] Extend `calculate_architecture_price()` to accept `duration`, resolve each
      selection's `unit` via `resolve_units` (003), classify it, and apply the FR-002/003/004/005
      proration rules per selection in `backend/src/services/price_calculation.py` (depends on
      T005, T006; makes T002 pass)
- [X] T008 [US1] Extend `POST /architectures/{id}/calculate` to accept and pass through the
      `duration` query param in `backend/src/api/calculate.py` (depends on T007; makes T003, T004
      pass)
- [X] T009 [US1] Run the `quickstart.md` validation for duration-scoped pricing (API steps 1-2)
      (depends on T008)

**Checkpoint**: User Story 1 is fully functional and independently testable.

---

## Phase 2: User Story 2 - Reliable connector creation and removal (Priority: P1) 🎯

**Goal**: Connectors can be created by selecting exactly two boxes and confirming, or by dragging
between boxes (restoring today's broken behavior); an existing connector can be removed the same
way.

**Independent Test**: Select exactly two boxes and confirm a connector is created; select an
existing connector and confirm it can be removed; verify dragging between two boxes also creates
a connector (per `quickstart.md`).

### Tests for User Story 2 ⚠️

- [X] T010 [P] [US2] Unit tests for a `canConnect(selectedNodeIds)` helper — exactly two ids
      returns `true`, zero/one/three+ returns `false` — in
      `frontend/tests/unit/connectorSelection.test.ts` (new file)

### Implementation for User Story 2

- [X] T011 [US2] Add `<Handle type="source">` / `<Handle type="target">` elements to both
      `ApplicationComponentNode` and `VpcNode` in `frontend/src/pages/CreateArchitecturePage.tsx`
      (fixes the FR-011 drag-to-connect regression — see research.md #8)
- [X] T012 [P] [US2] Implement `canConnect()` in `frontend/src/pages/connectorSelection.ts` (new
      file; makes T010 pass)
- [X] T013 [US2] Track selected node/edge ids via `useOnSelectionChange`, and add "Connect"
      (enabled only per `canConnect()`, FR-008/009) and "Remove Connector" (enabled only when a
      connector is selected, FR-010) actions, both always visible, in
      `frontend/src/pages/CreateArchitecturePage.tsx` (depends on T011, T012)
- [X] T014 [US2] Run the `quickstart.md` validation for connector creation/removal and the
      restored drag behavior (frontend smoke-check item 3) (depends on T013) — live-verified:
      `<Handle>` elements render on both node types (drag-to-connect fix confirmed visually);
      "Remove Connector" enable/disable and the full select-edge → confirm → delete flow
      verified end-to-end via a real API-seeded connector. The "select exactly two boxes"
      enabling path for "Connect" is covered by `canConnect()`'s 4 passing unit tests; live
      verification of the ctrl/cmd+click gesture itself was blocked by a browser-automation
      limitation (the tool's modifier-key state doesn't reliably reach React Flow's
      `useKeyPress`-based multi-selection tracking — confirmed via three different interaction
      methods and a direct synthetic-event dispatch attempt), not a suspected app defect.

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 3: User Story 3 - Trace a warning or exclusion back to its component(s) (Priority: P1) 🎯

**Goal**: Every unpriceable or duration-excluded service's warning names the Application
Component(s)/VPC(s) — or Data Connector — containing it.

**Independent Test**: Trigger both an unpriceable-SKU warning and a duration-exclusion warning on
services in different components, and verify each message names the right component(s) (per
`quickstart.md`).

### Tests for User Story 3 ⚠️

- [X] T015 [P] [US3] Unit tests for the selection-to-containing-component(s) association logic —
      a Collection-attached selection resolves to that Collection's name; a Connector-attached
      selection resolves to a `"Data Connector between X and Y"`-style description — in
      `backend/tests/unit/test_price_calculation.py` (extend)
- [X] T016 [P] [US3] Contract test: every entry in `calculate`'s `unpriceable` list carries a
      non-empty `components` array — in `backend/tests/contract/test_calculate.py` (extend)
- [X] T017 [US3] Integration test: an Architecture with one unpriceable service on a Collection
      and one on a Data Connector — both entries name the right component(s) — in
      `backend/tests/integration/test_warning_components.py` (new file)

### Implementation for User Story 3

- [X] T018 [US3] Add `UnpriceableItem.components: list[str] = []` in
      `backend/src/models/schemas.py`
- [X] T019 [US3] Extend `calculate_architecture_price()` to build the selection-to-component(s)
      association while iterating `architecture.collections`/`architecture.connectors` (before
      flattening), and populate `components` on both the existing unpriceable case and US1's
      FR-005 duration-exclusion case in `backend/src/services/price_calculation.py` (depends on
      T018 and on US1's T007 — same function; makes T015 pass)
- [X] T020 [US3] Run the `quickstart.md` validation for component-named warnings (API step 3,
      frontend smoke-check item 2) (depends on T019; makes T016, T017 pass)

**Checkpoint**: User Stories 1-3 all work independently.

---

## Phase 4: User Story 4 - See identifying details for services in the diagram (Priority: P2)

**Goal**: Each service shown inside a canvas box displays a short identifying detail, not just
its service code and SKU.

**Independent Test**: Add two similar services (e.g., different EC2 instance types) to a
component and verify the canvas box shows a distinguishing detail for each (per `quickstart.md`).

### Tests for User Story 4 ⚠️

- [X] T021 [P] [US4] Unit test for `resolve_attributes()` — a known SKU resolves its real
      attributes map, an unknown SKU resolves to `{}` — in `backend/tests/unit/test_catalog.py`
      (extend, mirrors `003`'s `resolve_units` tests)
- [X] T022 [P] [US4] Contract test: `SKUSelectionOut` responses (single-object endpoints and the
      nested Architecture tree) include a non-empty `attributes` map — in
      `backend/tests/contract/test_sku_selections.py`, `test_architectures.py` (extend — landed
      in `test_unit_resolution.py`, the existing home for the tree-level check, instead of
      `test_architectures.py`, which builds no SKU Selections of its own)
- [X] T023 [P] [US4] Frontend unit tests for the shared `skuDetail.ts` candidate-key summary
      helper (extracted from `CatalogSearchPanel.tsx`'s existing logic) — in
      `frontend/tests/unit/skuDetail.test.ts` (new file)

### Implementation for User Story 4

- [X] T024 [US4] Add `SKUSelectionOut.attributes: dict[str, str] = {}` in
      `backend/src/models/schemas.py`
- [X] T025 [US4] Implement `resolve_attributes(skus)` batched lookup in
      `backend/src/pricing_data/catalog.py` (depends on T024; makes T021 pass)
- [X] T026 [US4] Extend `architecture_service.py`'s `sku_selection_out_with_unit`/
      `attach_units_to_architecture` helpers to also attach `attributes` in the same pass
      (depends on T025)
- [X] T027 [US4] Wire the updated helpers through `backend/src/api/sku_selections.py`,
      `connectors.py`, `architectures.py` (depends on T026; makes T022 pass — no code change
      needed, these already delegate entirely to the extended helpers)
- [X] T028 [US4] Regenerate the OpenAPI-derived frontend types against the running backend
      (depends on T027)
- [X] T029 [US4] Extract the candidate-key detail-summary logic already in
      `CatalogSearchPanel.tsx` into `frontend/src/lib/skuDetail.ts` (new file; depends on T028;
      makes T023 pass)
- [X] T030 [US4] Update `CatalogSearchPanel.tsx` to use the shared helper instead of its own
      local copy (depends on T029)
- [X] T031 [US4] Show each service's identifying detail (via the shared helper) in
      `ApplicationComponentNode`'s and `VpcNode`'s service list in
      `frontend/src/pages/CreateArchitecturePage.tsx` (depends on T029; sequenced after US2's
      T013 since both touch this file)
- [X] T032 [US4] Run the `quickstart.md` validation for richer diagram detail (API step, frontend
      smoke-check item 4) (depends on T031)

**Checkpoint**: User Stories 1-4 all work independently.

---

## Phase 5: User Story 5 - Boxes always show their full content (Priority: P2)

**Goal**: A VPC's box shows its own directly-attached services; every box, at every level of
nesting, resizes to keep fully showing its content, cascading up through however many boxes
contain it.

**Independent Test**: Attach a service directly to a VPC and verify its box shows it; grow a
nested component's content and verify every containing box grows in turn (per `quickstart.md`).

### Tests for User Story 5 ⚠️

- [X] T033 [P] [US5] Unit tests for the generalized recursive height function — a leaf
      Application Component's height still comes from `estimateComponentHeight`; a container's
      height is its own direct services' height plus the sum of its children's *already-computed*
      heights, recursing correctly through multiple synthetic levels — in
      `frontend/tests/unit/nodeLayout.test.ts` (extend)

### Implementation for User Story 5

- [X] T034 [US5] Replace the one-level-only `estimateVpcHeight` with a genuine recursive height
      function in `frontend/src/pages/nodeLayout.ts` (makes T033 pass)
- [X] T035 [US5] Update `CreateArchitecturePage.tsx`: `VpcNode` renders its own `sku_selections`
      (reusing US4's `skuDetail` helper for consistency, FR-015), and node-building uses the new
      recursive height function bottom-up (FR-016/017) (depends on T034 and, for the shared
      helper, US4's T029)
- [X] T036 [US5] Run the `quickstart.md` validation for VPC own-services display and cascading
      resize (frontend smoke-check item 5) (depends on T035) — live-verified: a service attached
      directly to a VPC renders in its box; nesting a component and adding a service to it grows
      both the component's box and, cascading up, the containing VPC's box. Found and fixed two
      real issues during this pass, not caught by unit tests since they're rendering/CSS
      concerns: (1) nested children started at a fixed y-offset instead of below the VPC's own
      content, causing visual overlap — fixed by using `estimateComponentHeight` for the
      offset; (2) `VpcNode` never got `overflow: auto` (unlike `ApplicationComponentNode`),
      so its own content could visually bleed instead of scrolling — fixed for symmetry and
      FR-017 ("never overflow unreadably").

**Checkpoint**: All five user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T037 [P] Confirm the existing type-drift CI gate (`001`) catches this feature's schema
      changes until committed, then passes once staged — same verification pattern as `002`'s
      T015/`003`'s T031; no code change expected beyond T028's regeneration
- [X] T038 Run the full existing regression suite from `001`-`003` (backend `pytest`, frontend
      `vitest` + `tsc -b` + `eslint` + `build`) to confirm this feature introduces no regression —
      118 backend tests, 33 frontend tests, tsc/eslint/build all clean

---

## Dependencies & Execution Order

### Story Dependencies

- **User Story 1 (P1)**: No dependency on other stories.
- **User Story 2 (P1)**: No dependency on other stories — entirely frontend, no shared files
  with US1/US3's backend work.
- **User Story 3 (P1)**: Depends on User Story 1 — T019 extends the exact same
  `calculate_architecture_price()` rewrite T007 starts (adding `components` to items that
  function already constructs, including US1's new FR-005 exclusion case). Independent of US2.
- **User Story 4 (P2)**: No dependency on US1/US3's backend work. Its frontend task (T031)
  touches `CreateArchitecturePage.tsx` after US2's T013, so is sequenced after US2.
- **User Story 5 (P2)**: Depends on User Story 4 — T035 reuses the `skuDetail.ts` helper US4's
  T029 creates, and also touches `CreateArchitecturePage.tsx` after US4's T031.
- **Polish**: Depends on all five user stories being complete.

### Parallel Opportunities

- T001, T002, T003 (US1 tests) in parallel with each other; all in parallel with T010 (US2 test)
  and T015, T016 (US3 tests, though T017 needs US1's endpoint) — different files throughout.
- T021, T022, T023 (US4 tests) in parallel with each other and with US1/US2/US3's tasks — no
  shared files until T031/T035 reach `CreateArchitecturePage.tsx`.
- T033 (US5 test) can be written in parallel with everything above.
- T037, T038 (Polish) in parallel with each other.

---

## Parallel Example: User Story 1 tests

```bash
# All three touch different files and can run together:
Task: "Unit test for classify_unit() in backend/tests/unit/test_duration.py"
Task: "Unit tests for duration-proration math in backend/tests/unit/test_price_calculation.py"
Task: "Contract test for the duration query param in backend/tests/contract/test_calculate.py"
```

---

## Implementation Strategy

### Incremental Delivery

1. User Story 1 → validate independently → demo (trustworthy duration-scoped totals)
2. User Story 2 → validate independently → demo (connectors actually work again, plus the new
   select-and-Connect flow) — together with US1, this is the MVP-equivalent P1 pair
3. User Story 3 → validate independently → demo (every warning is traceable), building on US1
4. User Story 4 → validate independently → demo (richer diagram detail)
5. User Story 5 → validate independently → demo (VPC's own services, cascading resize), building
   on US4
6. Polish → final regression pass against all five stories

---

## Notes

- [P] tasks touch different files with no unmet dependency
- Commit after each task or logical group; verify each story's tests fail before implementing
  against them
- This feature deliberately introduces zero new tables, endpoints, or dependencies — see
  `research.md` for why the existing patterns from `001`-`003` (batched DuckDB resolution,
  React Flow's built-in `Handle`/`useOnSelectionChange`, extracted pure layout/decision
  functions) were reused rather than building new ones (Constitution Principle VI)

---

## Phase 7: Convergence

- [X] T039 Add a clear indicator to the usage-quantity field in
      `frontend/src/components/PricingInputsForm.tsx` distinguishing a per-day-estimate
      quantity (on-demand, FR-003) from an already-period-denominated one (Reserved, or
      on-demand `fixed_period`, FR-004) per FR-007 (missing) — implemented via a new pure
      `usageQuantityHint()` in `frontend/src/lib/usageQuantityHint.ts` (5 passing unit tests),
      mirroring the backend's `classify_unit()` unit-string tables since half the answer
      (Reserved vs. on-demand) is live form state that couldn't come from a static API field.
      Live-verified: switching Term between On-Demand and 1-Year Reserved correctly swaps the
      hint text in real time.

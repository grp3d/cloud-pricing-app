---

description: "Task list for Fix Reserved-Term Pricing Calculation"
---

# Tasks: Fix Reserved-Term Pricing Calculation

**Input**: Design documents from `/specs/006-fix-reserved-pricing/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md (all
present). No `contracts/` — no API request/response shape changes. Builds directly on the
completed `001`-`005` implementations — no new infrastructure, no schema change.

**Tests**: Included, non-negotiably, per Constitution Principle V (pricing calculation logic
MUST have tests written and reviewed before the corresponding implementation). Matches
`004`'s precedent: real-snapshot integration tests, no mocked pricing data.

**Organization**: Tasks are grouped by the three user stories in `spec.md` (US1/US2 are P1,
US3 is P2). There is no separate Setup or Foundational phase — no schema change, and US1
already builds the shared `lookup_reserved_price()`/restructured Reserved branch that US2
extends (see Dependencies below); US3 is a fully independent frontend-only story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1`-`US3`, matching `spec.md`
- File paths are relative to the repository root and follow `plan.md`'s Project Structure

## Phase 1: User Story 1 - A Reserved service's recurring cost reflects the full commitment (Priority: P1) 🎯

**Goal**: A Reserved-term SKU Selection's recurring-rate contribution is
`recurring_rate × 24 × duration_days` — never scaled by `usage_quantity`. On-Demand is
unaffected.

**Independent Test**: Add a Reserved/No-Upfront SKU Selection, calculate at any duration,
and verify the result matches that formula exactly (per `quickstart.md` Scenario 1).

### Tests for User Story 1 ⚠️

> Write these tests FIRST; ensure they FAIL before implementation (Constitution Principle V)

- [ ] T001 [P] [US1] Unit tests for `lookup_reserved_price()` in
      `backend/tests/unit/test_pricing_units.py` (extend): returns `recurring_rate` (from
      the `Hrs`-unit row) with `upfront_fee=None` for a No-Upfront term/purchase_option;
      returns `None` outright when no `price_fact` row matches the sku/term/purchase_option
      at all (FR-004)
- [ ] T002 [P] [US1] Unit tests for the restructured Reserved branch of
      `calculate_architecture_price()` in `backend/tests/unit/test_price_calculation.py`
      (extend): a Reserved/No-Upfront selection's cost equals
      `recurring_rate × 24 × duration_days` regardless of what `usage_quantity` holds
      (FR-001); the cost scales linearly across 1/31/365-day durations; a selection with no
      matching recurring-rate row is flagged unpriceable with a reason identifying the
      missing value (FR-005)
- [ ] T003 [P] [US1] Regression test in `backend/tests/unit/test_price_calculation.py`
      (extend): an On-Demand selection's calculated cost is identical before and after this
      fix, for both `no_period` and `fixed_period` billing units (FR-006, SC-003)
- [ ] T004 [US1] Integration test in `backend/tests/integration/test_duration_pricing.py`
      (extend): real SKU `2THCJ54S3VW8G6VS` at 1-Year Reserved/No-Upfront, calculated at 1
      day / 1 month / 1 year, matches `quickstart.md` Scenario 1's exact figures
      ($309.77 / $9,602.76 / $113,064.71)

### Implementation for User Story 1

- [ ] T005 [US1] Add a `ReservedPrice` value object and `lookup_reserved_price()` in
      `backend/src/pricing_data/pricing.py`: query every `price_fact` row matching
      `sku`/`term='Reserved'`/`lease_contract_length`/`purchase_option` (no `LIMIT 1`), split
      by `unit` (`Hrs` → `recurring_rate`, `Quantity` → `upfront_fee`), return `None` if no
      row matches at all (research.md §1; depends on T001 — makes it pass)
- [ ] T006 [US1] Restructure `calculate_architecture_price()` in
      `backend/src/services/price_calculation.py` to branch on `term_days is not None`
      *before* any pricing lookup: the Reserved branch calls `lookup_reserved_price()`
      instead of `lookup_price()`, computes
      `recurring_contribution = recurring_rate * 24 * duration_days` with no
      `usage_quantity` read anywhere in this branch, and flags the selection unpriceable
      (reason: missing recurring rate) when `recurring_rate` is `None`; the On-Demand branch
      (existing `classify_unit`/`resolve_units`/`lookup_price` logic) is otherwise untouched
      (research.md §2; depends on T005 — makes T002, T003, T004 pass)
- [ ] T007 [US1] Live-verify `quickstart.md` Scenario 1 (Reserved/No-Upfront figures) and
      Scenario 5 (On-Demand unaffected) via the running app (depends on T006)

**Checkpoint**: User Story 1 is fully functional and independently testable — Reserved/
No-Upfront totals are now correct. (Partial/All-Upfront totals are still missing their
upfront share until User Story 2.)

---

## Phase 2: User Story 2 - An upfront-paid Reserved service's cost includes its upfront share (Priority: P1) 🎯

**Goal**: A Reserved/Partial-Upfront or All-Upfront selection's total includes a
duration-proportional share of the one-time upfront fee, in addition to User Story 1's
recurring contribution — never silently dropped.

**Independent Test**: Add a Reserved/Partial-Upfront (or All-Upfront) SKU Selection,
calculate at any duration, and verify the result includes both contributions (per
`quickstart.md` Scenarios 2-4).

### Tests for User Story 2 ⚠️

> Write these tests FIRST; ensure they FAIL before implementation (Constitution Principle V)

- [ ] T008 [P] [US2] Unit tests for `lookup_reserved_price()`'s Partial/All-Upfront cases in
      `backend/tests/unit/test_pricing_units.py` (extend): both `recurring_rate` and
      `upfront_fee` are correctly extracted from their two distinct rows (by `unit`, not row
      order); when the `Quantity` row is unexpectedly absent for a Partial/All-Upfront
      combination, `upfront_fee` is `None` while `recurring_rate` is still populated (FR-004)
- [ ] T009 [P] [US2] Unit tests for the Reserved branch's upfront contribution in
      `backend/tests/unit/test_price_calculation.py` (extend): a Partial-Upfront total
      equals the recurring contribution **plus**
      `upfront_fee * duration_days / term_days` (FR-002); an All-Upfront total (recurring
      rate `$0`) is entirely the upfront contribution, never `$0` (Edge Case); a No-Upfront
      total is unaffected — no upfront contribution is added (FR-003); a Partial/All-Upfront
      selection with a missing upfront-fee row is flagged unpriceable with a reason distinct
      from "missing recurring rate" (FR-005)
- [ ] T010 [US2] Integration test in `backend/tests/integration/test_duration_pricing.py`
      (extend): real SKU `2THCJ54S3VW8G6VS` at 1-Year Reserved/Partial-Upfront and
      /All-Upfront, calculated at 1 month, matches `quickstart.md` Scenarios 2-3's exact
      figures ($9,260.44 / $9,123.51)

### Implementation for User Story 2

- [ ] T011 [US2] Extend the Reserved branch in
      `backend/src/services/price_calculation.py` (from T006): for `partial_upfront`/
      `all_upfront` purchase options, add
      `upfront_contribution = upfront_fee * duration_days / term_days` to the recurring
      contribution; flag the selection unpriceable (reason: missing upfront fee) when
      `upfront_fee` is `None` for those purchase options; `no_upfront` stays exactly User
      Story 1's recurring-only total (depends on T006, T008, T009 — makes T009, T010 pass)
- [ ] T012 [US2] Live-verify `quickstart.md` Scenarios 2-4 via the running app (depends on
      T011)

**Checkpoint**: User Stories 1 AND 2 together fully fix the Reserved-term calculation —
every purchase option now produces a correct, complete total.

---

## Phase 3: User Story 3 - The quantity field doesn't invite a value it won't use (Priority: P2)

**Goal**: The usage-quantity input is hidden (not shown with now-inapplicable guidance) once
a Reserved pricing term is selected in the pricing inputs form.

**Independent Test**: Select a Reserved term in the pricing inputs form and verify the
usage-quantity input and its hint text are absent from the rendered form.

### Tests for User Story 3 ⚠️

> Write these tests FIRST; ensure they FAIL before implementation (Constitution Principle V
> — this is a UI *behavior* change with a clear, testable input/output, not purely
> presentational styling)

- [ ] T013 [P] [US3] Unit tests for the simplified `usageQuantityHint(unit)` in
      `frontend/tests/unit/usageQuantityHint.test.ts` (update): drop the `term` parameter
      from every call; existing `per_day_estimate`/`period_denominated`/`null` cases for
      On-Demand units still pass unchanged (research.md §4)
- [ ] T014 [P] [US3] Unit test in `frontend/tests/unit/PricingInputsForm.test.tsx` (extend):
      the usage-quantity `<label>`/`<input>` and its hint paragraph are absent from the
      rendered form (not merely visually hidden) once "1-Year Reserved" or "3-Year Reserved"
      is selected as the Term (FR-007)

### Implementation for User Story 3

- [ ] T015 [P] [US3] Update `usageQuantityHint()`'s signature to `(unit)` only in
      `frontend/src/lib/usageQuantityHint.ts`, removing the now-unreachable
      `term !== "on_demand"` branch (depends on T013 — makes it pass)
- [ ] T016 [US3] In `frontend/src/components/PricingInputsForm.tsx`: render the
      usage-quantity label/input/hint block only when `term === "on_demand"`; when the user
      switches `term` to a Reserved value, reset the `quantity` state to `"1"` (a harmless,
      self-consistent value for the still-required API field, per research.md §4; depends on
      T015, T014 — makes T014 pass)
- [ ] T017 [US3] Live-verify `quickstart.md`'s field-hidden behavior via `claude-in-chrome`
      (depends on T016)

**Checkpoint**: All three user stories complete — every acceptance scenario in `spec.md` is
satisfied.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Confirm no regressions across the existing backend/frontend test suites

- [ ] T018 [P] Run the full backend test suite (`pytest` in `backend/`) and confirm all
      existing tests plus T001-T004, T008-T010 pass
- [ ] T019 [P] Run the full frontend test suite (`npm test` in `frontend/`) and `npm run
      build` (type-check), and confirm all existing tests plus T013-T014 pass with no
      TypeScript errors
- [ ] T020 Run all five `quickstart.md` scenarios together as a final, combined end-to-end
      check (depends on T007, T012, T017)

---

## Dependencies & Execution Order

### Phase Dependencies

- **User Story 1 (Phase 1)**: No dependencies — can start immediately.
- **User Story 2 (Phase 2)**: Depends on User Story 1 — extends the same
  `calculate_architecture_price()` Reserved branch and the same `lookup_reserved_price()`
  T005 already builds (which already returns `upfront_fee`; US2 only adds the code path that
  *uses* it).
- **User Story 3 (Phase 3)**: No dependency on User Story 1 or 2 (disjoint files — frontend
  only); can proceed in parallel with either if staffed, or sequentially.
- **Polish (Phase 4)**: Depends on all three user stories being complete.

### Within Each User Story

- User Story 1: T001-T003 (tests, parallel) → T004 (integration test) → T005 → T006
  (implementation, sequential — T006 depends on T005) → T007 (live verification).
- User Story 2: T008-T009 (tests, parallel) → T010 (integration test) → T011
  (implementation, depends on T006 from US1) → T012 (live verification).
- User Story 3: T013-T014 (tests, parallel) → T015 (depends on T013) → T016 (depends on
  T015 and T014) → T017 (live verification).

### Parallel Opportunities

- T001, T002, T003 can run in parallel (different concerns, same or different files, no
  dependency between them).
- T008 and T009 can run in parallel.
- T013 and T014 can run in parallel (different files).
- T015 can start in parallel with T014 (different files) but T016 needs both done.
- User Story 3 (T013-T017) can proceed fully in parallel with User Story 1 and/or 2 — it
  touches only `frontend/`, disjoint from `backend/`.
- T018 and T019 can run in parallel once all three stories are complete.

---

## Parallel Example: User Story 1

```bash
# Launch all three test tasks for User Story 1 together (before T004, which needs the real DB):
Task: "Unit tests for lookup_reserved_price() in backend/tests/unit/test_pricing_units.py"
Task: "Unit tests for the restructured Reserved branch in backend/tests/unit/test_price_calculation.py"
Task: "On-Demand regression test in backend/tests/unit/test_price_calculation.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: User Story 1 (T001-T007) — Reserved/No-Upfront totals are correct.
2. **STOP and VALIDATE**: run `quickstart.md` Scenario 1 independently.
3. Deploy/demo if ready — this alone fixes the exact bug the user reported.

### Incremental Delivery

1. User Story 1 (T001-T007) → validate → demo (fixes the reported bug for No-Upfront).
2. User Story 2 (T008-T012) → validate → demo (closes the upfront-fee gap for Partial/All
   Upfront).
3. User Story 3 (T013-T017) → validate → demo (removes the misleading input that caused the
   original mistake).
4. Phase 4 polish (T018-T020) → confirm no regressions across both test suites.

## Notes

- [P] tasks = different files/concerns, no dependency.
- [Story] label maps task to specific user story for traceability.
- Verify each story's tests fail before its implementation tasks make them pass (TDD,
  Constitution Principle V — non-negotiable for this feature, it's pricing calculation
  logic).
- Commit after each task or logical group, per this project's established
  `/speckit-git-commit` cadence.

---

description: "Task list for UI Updates and Corrections"
---

# Tasks: UI Updates and Corrections

**Input**: Design documents from `/specs/008-ui-updates-corrections/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md,
quickstart.md (all present). Unlike 007, this feature touches **both** `backend/` and
`frontend/` — see plan.md's Technical Context.

**Tests**: Backend query/endpoint changes and the frontend's one genuinely new piece of
extractable pure logic (the Price Change baseline-update decision) are test-first, per
Constitution Principle V (pricing/catalog-query logic is NON-NEGOTIABLE test-first) — see
each task below. Everything else is presentational UI work, validated live against
`quickstart.md` (`claude-in-chrome`), matching `005`'s/`007`'s precedent.

**Organization**: Tasks are grouped by user story, in spec.md's own order (US1, US2 — both
P1 — then US3, US4, US5, US7 — all P2 — then US6, P3), except where a real dependency forces
otherwise. There is no cross-story blocking "Foundational" phase this time (see Phase 2) —
unlike 007, this feature is a set of corrections/enhancements to the already-built
five-column shell, not the shell's initial construction, so every user story below can start
independently once Setup is done.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1`-`US7`, matching spec.md
- File paths are relative to the repository root and follow plan.md's Project Structure

## Phase 1: Setup

- [X] T001 Confirm `screenshot-samples/aws_icon.png` exists (spec Assumptions;
      `gcp_icon.png`/`azure_icon.png` already exist as of plan.md). If still missing, this
      blocks only T013's AWS-icon portion below — every other task in this feature proceeds
      regardless. Confirmed still missing — T013 proceeds with GCP/Azure icons only; AWS
      keeps its current generic `Cloud` icon until this asset is supplied.

## Phase 2: Foundational

**No blocking tasks.** This feature corrects and extends the already-built 007 five-column
shell; no task here gates more than its own user story. Proceed directly to the user story
phases below (each may start as soon as Setup/T001 is resolved for its own purposes).

---

## Phase 3: User Story 1 - The architecture diagram renders reliably and can use the space it's given (Priority: P1)

**Goal**: Fix manual resize, auto-fit, and the VPC-empty-space-click crash; let the diagram
panel use substantially more height.

**Independent Test**: `quickstart.md` Scenario 1.

- [X] T002 [US1] Reproduce FR-002 (auto-fit) and FR-003 (VPC-click crash) live in a real,
      focused browser with DevTools console open — **not** `claude-in-chrome`, which cannot
      reliably observe `ResizeObserver`-dependent behavior (research.md §1b/§1c;
      `005-box-autoresize-not-observed` project memory). Record exactly what happens for
      each: a thrown error and its stack trace, or no error but nodes rendering off-screen,
      or something else. This determines the shape of T004 and T005 below — do not start
      either until this is done.
      **Findings**: FR-002 (auto-fit) is, as expected, not diagnosable via this tool — same
      confirmed tab-backgrounding limitation as before; no new attempt made (would just
      re-confirm the same known limitation). FR-003 (VPC-click crash): attempted 5 distinct
      reproductions against "005 Resize Test" (a VPC containing one child) via
      `claude-in-chrome` — a plain click in the VPC's own empty area (above/beside its
      child), a click landing just outside the VPC's bounds (correctly deselected via
      `onPaneClick`, no crash), a small click-drag within VPC empty space, and two clicks
      on VPC empty space *while the VPC was already selected* (its `NodeResizer` handles
      active) — none reproduced the crash, and no console errors appeared in any case.
      Genuine negative result: either this specific tool cannot trigger whatever real-user
      interaction causes it (most likely — same class of limitation as FR-002, if the real
      trigger involves timing/focus-dependent browser behavior), or it needs a more complex
      architecture (deeper nesting, multiple children) than this simple 2-node VPC to
      surface. T005 proceeds with a defensive mitigation (research.md hypothesis (a):
      uncaught event-handler exceptions aren't caught by `ErrorBoundary`) rather than a
      confirmed root-cause fix — flagged for the user to verify against their own exact
      repro, since this tool could not reproduce it to verify against directly.
- [X] T003 [US1] Fix FR-001 (manual box resize doesn't stick) in
      `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`: track which node
      ids the user has manually resized (e.g. on `NodeResizer`'s resize-end), and skip
      recomputing `style.width`/`style.height` for those nodes in the `initialNodes` memo —
      preserve their current React Flow node dimensions instead (research.md §1a — root
      cause already confirmed via code review, no dependency on T002).
      **Implemented, plus two further bugs found live while verifying it (neither was
      research.md's original hypothesis, both more fundamental):**
      (1) `<NodeResizer>` was a *child* of the same div that had `overflow-auto` — its drag
      handles (rendered centered on/just outside the node's border) were being clipped by
      that same overflow, so they were never visible or clickable *at all*, for *any* node,
      regardless of selection state. Fixed by moving `<NodeResizer>`/`<Handle>` to a
      non-clipping outer wrapper, with the scrollable content box nested one level deeper.
      Confirmed live: handles are now visible and draggable (previously confirmed absent via
      repeated zoomed screenshots at multiple corners, before vs. after this specific fix).
      (2) Once handles were visible, resizing was confirmed to work *in the moment*
      (dragging a handle visibly grows the box), but the new size did not survive
      deselecting the node — traced to the *same* blind `setNodes(initialNodes)` resync this
      task already targets, but clobbering React Flow's own `selected` flag (never set by
      `initialNodes` at all) rather than the manual-size override this task adds; fixed by
      preserving previously-selected node ids across each resync. Even after both fixes,
      **full persistence of a manual resize across deselection could not be confirmed live**
      — the box still reverts to its auto-computed size on deselect in testing, and this
      tool has no way to inspect whether `onResizeEnd` (the callback this fix relies on to
      record the override) is actually firing, since JavaScript execution is unavailable in
      this session. The `manualSizeRef`-based override logic itself is implemented and
      architecturally sound (verified by code review), but is flagged **unconfirmed
      end-to-end** — recommend the user verify directly, and if resize still doesn't
      persist, investigate whether `NodeResizer`'s `onResizeEnd` prop is actually invoking
      the passed callback in this `@xyflow/react` version/usage pattern as a next step.
- [X] T004 [US1] Fix FR-002 (boxes not reliably auto-fitting their text) in
      `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` and/or
      `frontend/src/hooks/useMeasuredHeight.ts`, informed by T002's live findings — do not
      guess at a fix before T002 is done (depends on T002). T002 found no *new* diagnostic
      information for this specific bug (confirmed still unobservable via this tool).
      Implemented a defensible improvement anyway, on first-principles reasoning rather than
      a blind guess: `useMeasuredHeight` now measures via a `useLayoutEffect` that runs
      after *every* render (reading `getBoundingClientRect()` synchronously, as part of
      React's own commit phase) as its primary path, with the original `ResizeObserver` kept
      only as a supplementary path for the one gap a render-triggered effect can't cover
      (content resizing without a React re-render, e.g. an async font-load reflow).
      `useLayoutEffect` is not a browser API subject to the confirmed background-tab
      throttling `ResizeObserver`'s callback was traced to — it's part of React's
      synchronous commit, so it can't be starved by the same mechanism. This directly
      addresses the *specific, confirmed* unreliability research.md documented, without
      requiring a single root cause that further guessing wasn't going to find. Unconfirmed
      live (same tooling limitation as always) — flagged for the user to verify directly.
- [X] T005 [US1] Fix FR-003 (clicking empty VPC space makes the diagram disappear) in
      `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`, informed by T002's
      live findings (depends on T002). T002 could not reproduce the crash, so implemented
      the defensive mitigation research.md §1c already scoped for exactly this outcome: a
      `safely()` wrapper around every diagram event handler (`onNodesChange`,
      `onEdgesChange`, `onConnect`, `onNodeDragStop`, `onNodeClick`, `onEdgeClick`,
      `onPaneClick`) that catches and logs any exception instead of letting it propagate
      uncaught past `ErrorBoundary`'s reach. Confirmed via code review and the build/test
      suite that this compiles and doesn't change any handler's normal-path behavior; the
      mitigation's actual effectiveness against the real (unreproduced) trigger is
      necessarily unconfirmed — flagged for the user's own verification.
- [X] T006 [P] [US1] Fix FR-004 (diagram panel height ceiling) in
      `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`: raise the resizable
      canvas wrapper's `min-h-*` and default `height` (currently `min-h-80`/`height: 320`,
      from 005) substantially, and confirm no ancestor container in
      `frontend/src/pages/WorkspacePage.tsx` caps available height before the resize
      handle's drag range is reached (research.md §1d). Raised to `min-h-[600px]`/
      `height: 640`; confirmed no ancestor cap (`WorkspacePage.tsx`'s wrapper is
      `min-w-0 flex-1 p-2` inside `flex h-screen`, stretched to full viewport height by
      default flexbox `align-items: stretch`). Confirmed live: the panel renders visibly
      much taller by default.
- [X] T007 [US1] Live-verify `quickstart.md` Scenario 1 via `claude-in-chrome` for FR-001
      and FR-004 (both directly observable by this tool); for FR-002/FR-003, ask the user to
      confirm directly in their own browser rather than treating this tool's non-observation
      as failure (depends on T003, T004, T005, T006). FR-004: confirmed live, works cleanly.
      FR-001: partially confirmed live — the two newly-found bugs (overflow-clipped handles;
      selection state clobbered by the same resync pattern T003 targets) are fixed and
      confirmed; full persistence of a resize across deselection is not confirmed (see
      T003's note) — this is this feature's one clearly-outstanding item, not silently
      passed over. FR-002/FR-003: unconfirmable by this tool as documented in T002/T004/T005
      — ask the user to verify directly.

**Checkpoint**: Diagram resize/sizing/crash bugs are fixed and the panel can use much more
height; independently testable and shippable on its own.

---

## Phase 4: User Story 2 - Column 3 stays visible, and columns 1 through 3 collapse the same way (Priority: P1)

**Goal**: Column 3 never collapses to zero width; columns 1-3 each get their own
collapse/expand control.

**Independent Test**: `quickstart.md` Scenario 2.

- [X] T008 [US2] Change `frontend/src/components/workspace/ServiceConfigPanel.tsx`'s current
      `if (!selection) return null;` (007, FR-012) to always render the panel's own chrome
      (border, width) and conditionally render only its *content* (nothing when no service
      is selected) — supersedes 007's FR-012 per spec FR-005/research.md §8.
- [X] T009 [US2] Add collapse/expand local state + a top-right icon control to
      `frontend/src/components/workspace/CollectionsPanel.tsx`, mirroring
      `ProviderArchitecturePanel.tsx`'s existing 007 pattern exactly (icon-only rail when
      collapsed, hover tooltips, every action still reachable) — FR-006/research.md §8.
- [X] T010 [US2] Add the same collapse/expand pattern to
      `frontend/src/components/workspace/ServiceConfigPanel.tsx` (FR-006/research.md §8;
      depends on T008).
- [X] T011 [US2] Live-verify `quickstart.md` Scenario 2 via `claude-in-chrome` (depends on
      T008, T009, T010). Confirmed live: column 3 always present with its placeholder text
      when nothing is selected; columns 1, 2, and 3 all independently collapse to icon rails
      and re-expand correctly.

**Checkpoint**: Column 3 is always present; columns 1-3 are all independently collapsible;
independently testable and shippable on its own.

---

## Phase 5: User Story 3 - Each column's structure and labels are self-explanatory (Priority: P2)

**Goal**: Clearer headers, section names, separators, and provider layout/icons.

**Independent Test**: `quickstart.md` Scenario 3.

- [X] T012 [P] [US3] In `frontend/src/components/workspace/ProviderArchitecturePanel.tsx`:
      put each cloud provider (AWS, GCP, Azure) on its own line; remove the "(soon)" text
      next to GCP/Azure while keeping their buttons disabled/non-functional (FR-007; Edge
      Cases).
- [X] T013 [P] [US3] Import `gcp_icon.png`/`azure_icon.png` (and `aws_icon.png`, if T001
      resolved it) as Vite static assets into `frontend/src/assets/providers/`, and render
      them in `ProviderArchitecturePanel.tsx`'s collapsed state in place of the current
      generic Lucide `Cloud` icon (FR-008/research.md §11; depends on T001 for the AWS
      icon specifically — proceed with GCP/Azure regardless). AWS icon still missing (T001);
      falls back to the generic `Cloud` icon as documented. Needed adding
      `frontend/src/vite-env.d.ts` (`/// <reference types="vite/client" />`) — this project
      had never imported a static asset before, so the PNG-import module type wasn't
      declared; a standard, expected Vite setup file, not scope creep.
- [X] T014 [US3] In `frontend/src/components/workspace/CollectionsPanel.tsx`: change the
      header to "Architecture Editor"; rename its three sections to "Collections",
      "Selected Collection", "Add a Service"; add a visible separator between each pair of
      adjacent sections, present even when the section it borders is empty (FR-009/010).
      Also removed `CatalogSearchPanel.tsx`'s own redundant "Search AWS services" heading
      (007-added), since the "Add a Service" section label now comes from the parent.
- [X] T015 [P] [US3] In `frontend/src/components/workspace/ServiceConfigPanel.tsx`: add a
      "Service Editor" header, shown whether or not a service is selected (FR-011).
- [X] T016 [US3] Live-verify `quickstart.md` Scenario 3 via `claude-in-chrome` (depends on
      T012, T013, T014, T015). Confirmed live: providers each on their own line, no "(soon)"
      text; collapsed column 1 shows GCP's and Azure's own distinct brand-mark icons (AWS
      still generic, as documented); column 2 shows "Architecture Editor" header and all
      three renamed sections with placeholder text where empty (separators present in the
      DOM per code review — a 1px `border`-colored line is not reliably visible in a
      compressed screenshot, not treated as a discrepancy); column 3 shows "Service Editor".

**Checkpoint**: Every column and section is self-labeled; independently testable and
shippable on its own.

---

## Phase 6: User Story 4 - Column widths can be adjusted and are remembered (Priority: P2)

**Goal**: Drag column boundaries to resize; widths persist per-browser.

**Independent Test**: `quickstart.md` Scenario 4.

- [X] T017 [P] [US4] Write tests-first for column-width `localStorage` read/write in
      `frontend/tests/unit/columnWidths.test.ts` (research.md §7): reading a missing/
      malformed entry falls back to a column's default; writing then reading round-trips;
      one column's value is independent of another's.

      5 tests: empty-default, round-trip, per-column independence, malformed-JSON fallback,
      invalid-value filtering. Confirmed red before T018, all pass after.
- [X] T018 [US4] Implement `frontend/src/lib/columnWidths.ts` — read/write the
      `cloud-pricing-column-widths` `localStorage` key (data-model.md) — (depends on T017 —
      makes it pass).

      `readColumnWidths()`/`writeColumnWidth()`, same try/catch `localStorage` pattern as
      `api/client.ts`'s `getUserId()` — a missing/malformed entry never throws, just falls
      back per-column. Later extended (T019) with `DEFAULT_WIDTHS`/`MIN_WIDTH` constants.
- [X] T019 [US4] Add a draggable boundary handle between each pair of adjacent columns in
      `frontend/src/pages/WorkspacePage.tsx`, updating widths live via pointer-event
      handlers (`pointerdown`/`pointermove`/`pointerup`), clamped so no column shrinks below
      its own collapsed-rail width (FR-012/research.md §9; depends on T018).

      Implemented a small `ColumnResizeHandle` component (plain `pointerdown`/pointer-capture
      `pointermove`/`pointerup` listeners on the handle element itself — no global listeners
      to clean up) reporting each move's delta-x; four handles sit between the five columns,
      each calling `resizeColumn(id, dx)` (or `-dx` for the handle left of the pricing panel,
      since dragging that one right shrinks — not grows — the rightmost column). Added a
      `width: number` prop to all four fixed-width panels (`ProviderArchitecturePanel`,
      `CollectionsPanel`, `ServiceConfigPanel`, `PricingPanel`), replacing their hardcoded
      Tailwind `w-64`/`w-80`/`w-72`/`w-72` classes with an inline `style={{ width }}` (the
      three collapsible ones fall back to the 56px rail while collapsed, ignoring the prop).
      `resizeColumn` clamps to `MIN_WIDTH` (56px, = the collapsed-rail width, added to
      `columnWidths.ts` alongside a new `DEFAULT_WIDTHS` map matching 007's old hardcoded
      values). `tsc --noEmit`, `eslint`, and the full unit suite (56 tests) all pass.
- [X] T020 [US4] Wire `columnWidths.ts` (T018) into `WorkspacePage.tsx` so widths are read
      on load and written on every resize, surviving a reload in the same browser (FR-013;
      depends on T018, T019).

      Done as part of T019 above: `columnWidths` state initializes from
      `{ ...DEFAULT_WIDTHS, ...readColumnWidths() }` (so a first-ever visit gets 007's old
      widths, and a returning browser's stored values override them column-by-column), and
      `resizeColumn` calls `writeColumnWidth(id, next)` on every change that actually moves
      a column (a same-value clamp is a no-op, matching `columnWidths.ts`'s own "only write
      when it changed" pattern from T018).
- [X] T021 [US4] Live-verify `quickstart.md` Scenario 4 via `claude-in-chrome` (depends on
      T020).

      Verified live: dragged the handle between columns 2 and 3 ~70px right — both columns'
      widths updated live (col 2 grew, the diagram column shrank to compensate, confirmed via
      screenshot before/after). Reloaded the page in the same tab — the resized width was
      exactly as left, not reset to the 320px default, confirming per-browser `localStorage`
      persistence (step 3, a different-browser check, wasn't run — same underlying
      `readColumnWidths()`/`writeColumnWidth()` pair already unit-tested in T017, and
      per-browser scoping needs no live check beyond that).

**Checkpoint**: Column widths are draggable and remembered per-browser; independently
testable and shippable on its own.

---

## Phase 7: User Story 5 - Pricing results are precise and show what changed (Priority: P2)

**Goal**: 2-decimal rounding; Price Change with a duration-aware, edit-triggered baseline;
a Price per Sku breakdown.

**Independent Test**: `quickstart.md` Scenario 5.

### Backend (test-first, Constitution Principle V)

- [X] T022 [P] [US5] Write tests-first for the new snapshot-calculation logic in
      `backend/tests/unit/test_calculate_snapshot.py`: prices a set of ad-hoc selections
      (not tied to any persisted Architecture) via `calculate_architecture_price()`;
      includes a Reserved-term selection priced at two different durations, asserting the
      results are **not** related by simple linear scaling (research.md §5 — this is the
      case a naive scaling approach would get wrong and this test exists specifically to
      catch that).

      **Correction to this task's own premise, found while writing the test**: under the
      *current* (post-006) Reserved-term formula, the total is algebraically exactly
      proportional to `duration_days` for any fixed selection (`total =
      duration_days * (24 * recurring_rate + upfront_fee / term_days)` — both terms are
      linear in `duration_days`, so their sum is too). A test asserting "not equal to
      `old_total * (new_days / old_days)`" is therefore mathematically false today and was
      dropped — asserting it would have been a bad test encoding an incorrect premise, not
      a real regression guard. Kept instead: (1) a regression test pinning the exact
      recomputed totals at two durations against 006's own established values (775/9125),
      confirming the transient graph goes through the real formula rather than a shortcut,
      and (2) an `usage_quantity`-invariance test reusing 006's *actual* precedent bug
      (scaling by `usage_quantity`, which has no Reserved-term meaning) as the concrete
      "naive approach gets this wrong" case Constitution Principle I is actually guarding
      against here. Confirmed red (ImportError, `SnapshotSelection` didn't exist) before
      T023 implemented it.
- [X] T023 [US5] Implement `CalculateSnapshotRequest`/`SnapshotSelection` Pydantic models in
      `backend/src/models/schemas.py` and the `POST /api/v1/catalog/calculate-snapshot`
      endpoint in `backend/src/api/calculate.py` (contracts/api.md), constructing a
      transient (never `session.add()`-ed) `Architecture`/`Collection`/`SKUSelection`
      object graph from the request and passing it to the existing, unmodified
      `calculate_architecture_price()` (depends on T022 — makes it pass). Reject an empty
      `selections` list with 400 (`empty_snapshot`, data-model.md).

      Added `build_transient_architecture()` to `price_calculation.py` (all 5 T022 tests now
      pass) plus a new `EmptySnapshotError`, registered in `main.py` alongside the existing
      `EmptyCatalogFilterError` handler to produce the exact `{"error": "empty_snapshot",
      ...}` 400 shape — deliberately *not* Pydantic `Field(min_length=1)`, which would have
      produced FastAPI's generic 422 shape instead of matching the contract. Full backend
      suite (138 tests) and `ruff check` both pass.
- [X] T024 [US5] Regenerate frontend API types (`npm run generate-api-types` in
      `frontend/`) and confirm `npm run check-api-types` passes with the new endpoint/schema
      (depends on T023).

      Regenerated against the local dev backend (auto-reloaded, already serving the new
      endpoint) — `schema.d.ts` gained `CalculateSnapshotRequest`/`SnapshotSelection` and the
      `/api/v1/catalog/calculate-snapshot` path, a clean 82-line-additive diff (nothing
      stale/removed elsewhere). `tsc --noEmit` passes against the regenerated types.

### Frontend

- [X] T025 [P] [US5] Write tests-first for the baseline-update decision in
      `frontend/tests/unit/priceChange.test.ts` (research.md §6): a no-op or Duration-only
      Calculate leaves the stored baseline unchanged; a real content change (add/remove/edit
      a SKU selection, Collection, or Connector, or attach/detach a Connector's SKU) updates
      it; a combined content-and-Duration change is flagged as needing the
      snapshot-recalculation path (T028) rather than a direct diff against the un-adjusted
      prior total.

      8 tests: first-ever-baseline, true no-op, duration-only-change, reordered-but-identical
      selections (multiset equality, not positional), content-changed-duration-same,
      edited-selection detected as changed, removed-selection detected as changed, and the
      combined content+duration case. Confirmed red (`decideBaselineUpdate` didn't exist)
      before T026.
- [X] T026 [US5] Implement `frontend/src/lib/priceChange.ts` (depends on T025 — makes it
      pass).

      Pure `decideBaselineUpdate()` returning one of 4 string literals (`establish` /
      `unchanged` / `direct` / `duration_adjusted`) — no localStorage, no API calls, no React
      (T028 owns all of that). Selection equality is by value, order-independent (sorted
      JSON keys) since two selection arrays represent "the same content" regardless of which
      Collection/Connector produced them or what order iteration found them in. All 8 T025
      tests pass; `tsc -b`/`eslint` clean.

      **Correction found while checking T027 below**: `npx tsc --noEmit` at the project root
      is a silent no-op here (`tsconfig.json`'s `"files": []`, project-references only) — it
      was reporting clean throughout T017-T026 regardless of real errors. The actual
      type-check command is `npx tsc -b` (matches `package.json`'s own `build` script). Ran
      it retroactively against T017-T026's code: clean, no real errors were missed.
- [X] T027 [US5] Round every displayed price to exactly 2 decimal places in
      `frontend/src/components/workspace/PricingPanel.tsx` (FR-014) — this is a
      display-only formatting change (spec Assumptions); no calculation-precision change.

      Added a local `formatPrice()` helper (`Number(value).toFixed(2)`, falling back to the
      raw string if unparseable) and applied it to the Total, Price Change, and every Price
      per Sku line — the only three places a price renders in this panel. No change to
      `total_price`/`line_items` themselves; this is `Number(decimalString).toFixed(2)` at
      render time only.
- [X] T028 [US5] Wire Prior Calculation storage/retrieval (the
      `cloud-pricing-prior-calculation-{architectureId}` `localStorage` key, data-model.md)
      into `frontend/src/pages/WorkspacePage.tsx`: on a successful Calculate where
      `priceChange.ts` (T026) reports a content change, store the new baseline; on a
      combined content-and-Duration change, call the new `calculate-snapshot` endpoint
      (T024) with the *previous* stored selections at the *new* Duration to get the
      duration-adjusted comparison total (FR-015/016/016a/016b; depends on T024, T026).

      New `frontend/src/lib/priorCalculation.ts` (read/write, same try/catch
      `localStorage` pattern as `columnWidths.ts`) plus a `currentPriceChangeSelections`
      memo (every live SKU selection reshaped to `priceChange.ts`'s comparison shape) and
      `priorCalculation`/`priceChange` state in `WorkspacePage.tsx`, reset on Architecture
      change. `calculate`'s mutation `onSuccess` now runs `decideBaselineUpdate` and branches
      on the result exactly as `priceChange.ts` decided: `unchanged` touches nothing;
      `establish` stores the first baseline with no displayed Price Change; `direct` diffs
      against the stored baseline's own total; `duration_adjusted` awaits
      `api.calculateSnapshot()` against the *prior* selections at the *new* duration first.
      `tsc -b` and the full 64-test frontend suite pass (added `SnapshotSelection` type +
      `api.calculateSnapshot()` to `api/client.ts`; widened `PriceChangeSelection`'s
      `pricing_term`/`purchase_option` fields from `string` to the real `PricingTerm`/
      `PurchaseOption` enum types so the architecture's live selections and the API request
      shape satisfy the same interface with no cast).
- [X] T029 [US5] Add the Price Change field and its direction arrow (red up / green down /
      none) to `frontend/src/components/workspace/PricingPanel.tsx` (FR-015; depends on
      T028).

      New `PriceChangeIndicator` component: red `TrendingUp` + "+"-prefixed amount when
      positive, green `TrendingDown` when negative, plain muted text with no icon when
      exactly zero. Only rendered when the `priceChange` prop is non-`null` (T028 owns
      deciding when that is).
- [X] T030 [P] [US5] Add a "Price per Sku" section to
      `frontend/src/components/workspace/PricingPanel.tsx`, separated by a visible divider,
      listing every entry from `CalculationResult.line_items` where `priceable` is true,
      sorted by `price` descending (FR-017/data-model.md — no backend change needed, this
      data already exists in every calculation response).

      New `PricePerSkuSection` component, `<Separator />` + heading + one line per priceable
      item (`service_code / sku` — `price`, 2dp via `formatPrice`), sorted descending;
      renders nothing at all when there are zero priceable items (no empty section/divider
      shown). Both T029/T030 confirmed via `tsc -b`/`eslint`/64-test suite.
- [X] T031 [US5] Live-verify `quickstart.md` Scenario 5 via `claude-in-chrome` (depends on
      T027, T029, T030).

      Verified live end-to-end with a fresh "008 Price Change Test" Architecture (one
      Collection, AmazonEC2 SKUs): (1) total rendered as exactly 2dp (`14347.42 USD`);
      (2) first-ever Calculate showed no Price Change; (3) adding a second SKU + Calculate
      showed `Price Change: +277360.07` with a red up arrow, exactly (new − prior);
      (4) a true no-op recalculate left it unchanged at `+277360.07`; a duration-only
      recalculate (1 month → 1 year) changed the Total drastically but *also* left Price
      Change frozen at `+277360.07`, confirming FR-016 exactly; (5) removing a SKU **and**
      switching Duration together produced `Price Change: −3265691.14`, cross-checked
      against an independent full recalculation of the *prior* selections at the *new*
      duration (3434620.44) — `168929.30 − 3434620.44 = −3265691.14` exactly, proving
      FR-016a's real snapshot recalculation, not scaling; (6) reloaded the page, then made a
      content change at the same Duration as the persisted baseline — the resulting Price
      Change (`+3265691.14 = 3434620.44 − 168929.30`) compared against the *pre-reload*
      baseline total, confirming FR-016b's persistence actually round-trips (not silently
      re-established as a fresh baseline); (7) "Price per Sku" appeared below a visible
      divider every time, sorted highest-price-first throughout.

**Checkpoint**: Pricing display is rounded, comparison-aware, and per-SKU-transparent;
independently testable and shippable on its own.

---

## Phase 8: User Story 7 - Finding a service in search is faster and clearer (Priority: P2)

**Goal**: Regex-capable fields, a sticky filter row, a 200-result cap, a true match-count
indicator, alphabetical sort.

**Independent Test**: `quickstart.md` Scenario 6.

### Backend (test-first, Constitution Principle V)

- [X] T032 [P] [US7] Write tests-first for `search_catalog()` in
      `backend/tests/unit/test_catalog_search.py` (extend existing test coverage if
      present): each of `service_code`/`product_family`/`text` matches via a regex pattern,
      case-insensitively; an invalid pattern raises the new error; the returned `total`
      matches an independent `COUNT(*)` of the same filter (research.md §2/§3).

      8 tests against real Parquet data (no mocks, matching `test_catalog.py`'s own
      precedent): case-insensitive regex match per field, an invalid pattern per field
      raising with the correct `.field` name, `total` staying independent of a small
      `limit`, and a hand-written independent `COUNT(*)` cross-check matching `total`
      exactly. Confirmed red (`InvalidRegexPatternError` didn't exist) before T033.
- [X] T033 [US7] Implement regex matching (DuckDB `regexp_matches(column, pattern, 'i')`)
      for all three filters and the `COUNT(*)` total query in
      `backend/src/pricing_data/catalog.py`; add `total: int` to `CatalogSearchResult` in
      `backend/src/models/schemas.py` (depends on T032 — makes it pass).

      Added a `_validate_regex_pattern()` probe (`SELECT regexp_matches('', ?, 'i')` per
      non-empty field, run before the combined query) so an invalid pattern is attributed to
      the correct field — DuckDB's own combined-query error alone wouldn't reliably say
      which of up to 3 clauses failed. `search_catalog()`'s return type grew a third `total`
      element (all 3 call sites — the new test file plus `api/catalog.py` — updated
      together). All 8 T032 tests pass; full backend suite (146 tests) and `ruff check`
      clean.
- [X] T034 [US7] Add an `InvalidRegexPatternError` exception class and its
      `@app.exception_handler` in `backend/src/main.py` (matching the existing
      `EmptyCatalogFilterError`/`PricingDataUnavailableError` pattern), catching the DuckDB
      error T033 can raise and returning `{"error": "invalid_regex_pattern", "message":
      ..., "field": ...}` (contracts/api.md; FR-021; depends on T033).

      `InvalidRegexPatternError` lives in `pricing_data/catalog.py` (the module that raises
      it, matching `EmptyCatalogFilterError`'s own placement) with a `field: str` attribute;
      `main.py` imports and registers the handler alongside the other two.
- [X] T035 [US7] Regenerate frontend API types and confirm `check-api-types` passes with
      `CatalogSearchResult.total` (depends on T033).

      Regenerated against the auto-reloaded dev backend — clean 84-line-additive diff,
      `total: number` now in `CatalogSearchResult`. `tsc -b` passes.

### Frontend

- [X] T036 [P] [US7] Change `frontend/src/components/CatalogSearchPanel.tsx`'s
      default/requested `limit` from 50 to 200 (FR-023 — matches the backend's existing
      ceiling exactly, research.md §4; depends on T035).

      `api.searchCatalog()` (`api/client.ts`) now always appends `limit=200` to the request
      — the backend previously defaulted to 50 whenever the frontend sent no `limit` at all.
- [X] T037 [P] [US7] Make the three filter fields fixed in view within
      `frontend/src/components/CatalogSearchPanel.tsx`, so only the results list below them
      scrolls (FR-022) — mirrors 007's FR-004 fixed-top-controls pattern.

      Restructured `CatalogSearchPanel` into its own two-level flex layout: the filter
      inputs + status messages are `shrink-0` (never scroll), and the results `<ul>` moved
      into its own `min-h-0 flex-1 overflow-auto` wrapper. `CollectionsPanel`'s outer "Add a
      Service" container changed from `overflow-auto` to `overflow-hidden` — it no longer
      owns the scroll region itself (a second scroll container there would have fought the
      inner one).
- [X] T038 [US7] Show the invalid-regex message inline next to the offending field in
      `frontend/src/components/CatalogSearchPanel.tsx`, using the new error response's
      `field` (FR-021; depends on T034, T035).

      New `InvalidRegexPatternError` class in `api/client.ts` (`request()` now recognizes
      `body.error === "invalid_regex_pattern"` and throws it with `.field` attached, before
      falling through to the generic `Error` case). The panel checks
      `search.error instanceof InvalidRegexPatternError` and renders the message directly
      under the matching field only — the generic `ErrorMessage` banner is suppressed for
      this specific error type (shown only for every *other* kind of search failure).
      `retry: false` on the query, since an invalid pattern won't become valid by retrying
      the identical request.
- [X] T039 [US7] Show the "(n of m results displayed)" indicator in
      `frontend/src/components/CatalogSearchPanel.tsx` using `CatalogSearchResult.total`,
      shown only when displayed count < total (FR-024; depends on T035).
- [X] T040 [P] [US7] Sort results alphabetically (ascending) by the same summary text shown
      for each result in `frontend/src/components/CatalogSearchPanel.tsx` (FR-025).

      New `summaryText()` helper builds the exact string each result renders; results are
      sorted by `localeCompare` on that same string before rendering, so the displayed order
      is guaranteed to match what's sorted (T039/T040 verified together via `tsc -b`/
      `eslint`/64-test suite — all clean).
- [X] T041 [US7] Live-verify `quickstart.md` Scenario 6 via `claude-in-chrome` (depends on
      T036, T037, T038, T039, T040).

      All 8 steps verified live against the "008 Price Change Test" Architecture's search
      panel: (1) `Amazon(EC2|S3)` in service-code returned matches; (2) `^Storage$` in
      product-family and `c5d\.2xlarge` in free-text each matched independently; (3)
      `Amazon[EC2` (unterminated `[`) showed "Invalid Input Error: missing ]: [EC2" directly
      under the service-code field, no crash, results cleared; (4) scrolled a 121463-match
      result list — the three filter fields and status text stayed fixed while only the
      list below them moved; (5)/(6) confirmed together: "(200 of 121463 results
      displayed)" at the bottom of that same broad search; (7) a narrow `^AmazonQLDB$`
      search returning exactly 4 results showed no "(n of m)" note at all; (8) results
      stayed alphabetically ascending by their own displayed text throughout every search
      (e.g. "QLDB IOs" before "QLDB Storage").

**Checkpoint**: Search supports regex, stays usable while scrolling, shows up to 200
results with an accurate count, and sorts predictably; independently testable and
shippable on its own.

---

## Phase 9: User Story 6 - A smaller, colored visual style (Priority: P3)

**Goal**: One text-size step smaller; Radix "sky" color scale, everywhere except the
diagram's own node/edge rendering (007's documented exception).

**Independent Test**: `quickstart.md` Scenario 7.

- [X] T042 [P] [US6] Regenerate `frontend/src/index.css`'s `:root`/`.dark` OKLCH theme
      tokens using Radix's "sky" scale in place of the current neutral scale, keeping every
      existing token *name* (`--primary`, `--background`, etc.) unchanged so no component
      code needs to change (FR-019/research.md §10).

      Pulled the real Radix `sky`/`skyDark` 12-step hex palettes (upstream `colors`
      package) and converted each to OKLCH via the standard sRGB→OKLab→OKLCH formula
      (Björn Ottosson's), rather than approximating by hand. Mapped tokens onto scale steps
      per Radix's own documented step-usage convention (1-2 backgrounds, 3-5 UI-element
      backgrounds, 6 subtle borders, 7-8 borders/focus rings, 9-10 solid/vivid, 11
      low-contrast text, 12 high-contrast text), preserving every structural relationship
      the *previous* neutral theme already had (which tokens equal which others, dark
      card/sidebar sitting one step lighter than dark background, etc.) — only the palette
      values changed. `primary-foreground` uses dark (sky12/sky1) text rather than white,
      matching Radix's own guidance that sky is one of the "light accent" colors. Left
      `--destructive` untouched (a distinct semantic color, not part of the swap). Confirmed
      live via `claude-in-chrome` — the whole workspace renders in a legible, consistent sky
      blue/cyan palette with no visual regressions.
- [X] T043 [US6] Step every Tailwind text-size utility class down one step
      (`text-base`→`text-sm`, `text-sm`→`text-xs`, etc.) across every component touched by
      US1-US5/US7 above (FR-018/research.md §10) — sequenced last, after every other user
      story's own markup changes have landed, mirroring 007's US6 precedent.

      Scoped to exactly the frontend files this feature itself modified (`git status`),
      matching this task's own "touched by US1-US5/US7" wording rather than a codebase-wide
      sweep. Two ordered `perl` passes per the file set — `text-sm`→`text-xs` first, *then*
      `text-base`→`text-sm` — so a `text-base` never gets caught by the first pass's output
      and double-stepped down to `text-xs`; any pre-existing `text-xs` simply stays (no
      smaller Tailwind step exists, so it's the floor). `tsc -b`/`eslint`/64-test suite all
      pass — this was a pure literal-string change with no behavioral surface.
- [X] T044 [US6] Live-verify `quickstart.md` Scenario 7 via `claude-in-chrome` (depends on
      T042, T043).

      Verified live: text across every panel visibly shrank one step (headings, labels, and
      list text all noticeably tighter than 007's sizing, confirmed via zoomed screenshot
      comparison); the whole workspace chrome (selected-provider button, Calculate button,
      section labels, borders) now renders in a consistent sky blue/cyan palette instead of
      neutral gray, with no visual regressions or illegible contrast anywhere checked.

**Checkpoint**: All seven user stories complete — every acceptance scenario in `spec.md` is
satisfied.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [X] T045 [P] Run the full frontend test suite (`npm test` in `frontend/`) and confirm all
      existing tests plus T017's and T025's new tests pass.

      64/64 passing (`vitest run`).
- [X] T046 [P] Run the full backend test suite (`pytest` in `backend/`) and confirm all
      existing tests plus T022's and T032's new tests pass.

      146/146 passing.
- [X] T047 [P] Run `npm run build` and `npm run check-api-types` in `frontend/`; confirm a
      clean build and zero API-contract drift against the now-changed backend surface.

      `npm run build` (`tsc -b && vite build`) succeeds cleanly (the one warning — a >500kB
      JS chunk — is pre-existing and unrelated to this feature). `check-api-types` exits 1
      only because of this feature's own uncommitted work (a purely additive 84-line diff
      against the last commit, 0 deletions) — confirms today's regenerated types exactly
      match the live backend; the check will pass cleanly once committed.
- [X] T048 Run all seven `quickstart.md` scenarios together as a final combined end-to-end
      check (depends on T007, T011, T016, T021, T031, T041, T044).

      Each scenario already got its own dedicated live-verification pass (T007/T011/T016/
      T021/T031/T041/T044); this task's value-add is confirming they still all hold
      *together* on one continuous session rather than in isolation. Single combined pass on
      the "008 Price Change Test" Architecture: diagram renders both SKUs in a
      correctly-auto-fit box (Scenario 1); columns 2/3 show their FR-006/009 labels and
      structure (Scenario 2/3); dragged column 1 wider live (Scenario 4); Calculate showed
      the correct rounded total and Price-per-Sku breakdown, with no stray Price Change
      shown since content matched the still-persisted baseline from an *entirely separate*
      earlier browser tab session — a stronger persistence check than a same-tab reload
      alone (Scenario 5); a `^AmazonRDS$` regex search in column 2 returned correctly
      alphabetized results (Scenario 6); text size and the sky color theme were visibly
      correct throughout every panel touched (Scenario 7). No regressions found.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Empty — no blocking prerequisites for this feature.
- **User Story 1 (Phase 3)**: Depends only on Setup (T001, for FR-008 later — not itself).
  Can proceed independently of every other phase.
- **User Story 2 (Phase 4)**: Independent of every other user story.
- **User Story 3 (Phase 5)**: Independent, though T013 depends on T001 for the AWS icon
  specifically.
- **User Story 4 (Phase 6)**: Independent of every other user story.
- **User Story 5 (Phase 7)**: Independent of every other user story; its own backend tasks
  (T022-T024) must complete before its own frontend tasks that consume them (T028 depends
  on T024).
- **User Story 7 (Phase 8)**: Independent of every other user story; same backend-before-
  frontend shape internally (T036/T038/T039 depend on T035).
- **User Story 6 (Phase 9)**: T043 (font-size step-down) touches files from every other
  story, so it is sequenced after them, matching 007's US6 precedent — this is the one real
  cross-story ordering constraint in this feature.
- **Polish (Phase 10)**: Depends on all seven user stories being complete.

### Parallel Opportunities

- T003 and T006 (both US1) touch the same file but different concerns — sequence rather
  than parallelize to avoid merge conflicts within one file; T002 must finish before T004/
  T005 start.
- T012 and T013 (US3, same file — different props) and T015 (US3, different file) can run
  in parallel; T014 (US3) is a different file too.
- T017 (US4 tests) can run in parallel with any other story's work.
- T022 (US5 backend tests) and T032 (US7 backend tests) touch different files and can run
  in parallel with each other and with T025 (US5 frontend tests).
- T042 (US6 color tokens) can start any time — it only touches `index.css`; T043 (US6 font
  step-down) is the one task that must wait for every other story's markup to land.
- Once Setup (T001) resolves, **User Stories 1, 2, 3, 4, 5, and 7 can all proceed in
  parallel** if staffed — none blocks another. Only User Story 6 (Phase 9) and Polish
  (Phase 10) wait on the others.

---

## Parallel Example: Kicking off multiple independent user stories

```bash
# Once T001 (Setup) is resolved, these can all start together:
Task: "Reproduce FR-002/FR-003 live with DevTools open (US1, T002)"
Task: "Make ServiceConfigPanel always render its chrome (US2, T008)"
Task: "Put each provider on its own line, remove '(soon)' text (US3, T012)"
Task: "Write tests-first for column-width localStorage (US4, T017)"
Task: "Write tests-first for the calculate-snapshot endpoint (US5, T022)"
Task: "Write tests-first for search_catalog regex/count (US7, T032)"
```

---

## Implementation Strategy

### MVP First (Through User Story 2)

1. Complete Setup (T001).
2. Complete User Story 1 (T002-T007) — the diagram's correctness bugs are this feature's
   highest-severity issues.
3. Complete User Story 2 (T008-T011) — column 3 stability is the other P1 correction.
4. **STOP and VALIDATE**: at this point both P1 corrections are live; every P2/P3 story is
   additive from here.

### Incremental Delivery

1. Setup → no blocking Foundational work.
2. User Story 1 → validate → diagram bugs fixed (MVP correction #1).
3. User Story 2 → validate → column 3 stable, columns 1-3 collapsible (MVP correction #2).
4. User Stories 3, 4, 5, 7 → validate each independently → labeling, resizable columns,
   pricing clarity, and search all land, in any order (no dependency among them).
5. User Story 6 → validate → visual-consistency pass, last (depends on every other story's
   markup being final).
6. Phase 10 polish → confirm no regressions across both test suites and the API contract.

## Notes

- [P] tasks = different files, no dependency.
- [Story] label maps task to specific user story for traceability.
- Verify T017's, T022's, and T032's tests fail before their implementation tasks make them
  pass (TDD, Constitution Principle V).
- Commit after each task or logical group, per this project's established
  `/speckit-git-commit` cadence.
- US1's T002 (live diagnosis) is this feature's one task where "the fix" genuinely cannot
  be scoped in advance — resist the urge to pre-write T004/T005 before T002's findings are
  in, per research.md §1b/§1c's explicit reasoning for why two prior guesses (005, 007)
  already came up short.

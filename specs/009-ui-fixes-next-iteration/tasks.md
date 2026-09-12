---

description: "Task list for UI Fixes and Enhancements — Next Iteration"
---

# Tasks: UI Fixes and Enhancements — Next Iteration

**Input**: Design documents from `/specs/009-ui-fixes-next-iteration/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md,
quickstart.md (all present). Like 009's immediate predecessor (008), this feature touches
**both** `backend/` and `frontend/` — see plan.md's Technical Context.

**Tests**: Per Constitution Principle V, test-first applies to: the Connector-conflict `409`
(backend, pricing/data-relationship logic), the two new region-code DuckDB filters (backend,
catalog-query logic), and every new/changed pure-logic module under `frontend/src/lib/`
(`priceChange.ts`'s new branch, `diagramLayout.ts`, `awsDataTransfer.ts`, `edgeOffset.ts`) — the
same convention `serviceConfigSelection.ts`/`nodeLayout.ts` already established. US1 and US3 are
correctness bugs whose actual faulty code is not yet identified (research.md §1/§3 both found
the obvious candidate logic does *not* reproduce the failure in isolation) — each gets a live
reproduction task before any fix, and a regression test only once the real failure point is
confirmed (not written against a guess). Everything else is presentational UI work, validated
live against `quickstart.md` via `claude-in-chrome`, matching 007/008's precedent.

**Organization**: Tasks are grouped by user story, in spec.md's own priority order — US1, US2,
US3 (P1), then US4, US5, US6 (P2), then US7, US8, US9 (P3) — except where a real dependency
forces otherwise (none found: research.md confirms every story's changes are isolated to their
own files, so all nine are independently implementable and independently testable, matching
each story's own "Independent Test" in spec.md).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1`-`US9`, matching spec.md
- File paths are relative to the repository root and follow plan.md's Project Structure

## Phase 1: Setup

**No tasks.** This feature is a bug-fix-and-polish pass over the already-built 008 five-column
shell — research.md confirms every change lands inside already-existing files/modules (plus a
small number of new sibling files within already-established directories:
`frontend/src/lib/{diagramLayout,awsDataTransfer,edgeOffset}.ts`,
`frontend/src/components/ui/dialog.tsx`, each created within its own user story phase below).
No shared project-initialization work is needed before any story can start.

## Phase 2: Foundational

**No blocking tasks.** Research.md confirms all nine stories touch disjoint sets of files with
no cross-story data or type dependency — every story phase below may start immediately, in any
order, once its own dependencies (an earlier task within the *same* story) are satisfied.

---

## Phase 3: User Story 1 - A specific SKU prices successfully (Priority: P1)

**Goal**: SKU `2AB37QDFJZBGQ5YP` prices successfully (or is clearly reported as unpriceable),
never a hard failure.

**Independent Test**: `quickstart.md` US1 scenario.

- [X] T001 [US1] Live-reproduce the failure via `claude-in-chrome` against the running dev app:
      search for SKU `2AB37QDFJZBGQ5YP`, add it to a Collection, configure it, and run a
      calculation — repeat across on-demand and at least two Reserved term/purchase-option
      combinations. Capture the exact failure point and any console error
      (`read_console_messages`). Research.md §1 already ruled out
      `calculate_architecture_price()` itself (direct backend reproduction succeeded for all
      seven combinations against the live snapshot) — this task's job is to find where in the
      live app the failure actually occurs. Do not start T002 until this is recorded.
      **Findings**: Added the exact SKU directly (`POST /collections/{id}/sku-selections`) and
      calculated via the real, persisted-Architecture endpoint and via the live browser UI
      (search → select service → set Term/Purchase option in the Service Editor → Save →
      Calculate): on-demand ($105,433.17/mo) and all three 1-year Reserved purchase options
      (No/Partial/All Upfront: $2,621.11 / $2,779.87 / $2,524.76 per month) all price
      successfully with zero errors, zero console errors, zero unpriceable entries — confirming
      research.md §1's calculation-engine finding end-to-end through the real app, not just in
      isolation. **The actual defect is a search-discoverability gap, not a pricing failure**:
      `search_catalog()`'s free-text filter (`backend/src/pricing_data/catalog.py`) only
      matches `service_name`/`attributes_json`, never the `sku` column itself. Searching the
      free-text field for `2AB37QDFJZBGQ5YP` (a natural thing to do when you have a SKU ID in
      hand) returns **zero results for the SKU itself** — instead it incidentally matches two
      *different* SKUs (`2C4ZUG7R49UEMPGV`, `K4VFPXXYQNRNMN6P`, both Capacity-Reservation
      variants of the same instance type) that happen to reference `2AB37QDFJZBGQ5YP` inside
      their own `attributes.instancesku` field. A user pasting this SKU into search cannot find
      or select the actual SKU at all — a real, reproducible usability failure that plausibly
      reads as "failure to price this SKU" from the user's side. Redirecting T002 accordingly.
- [X] T002 [US1] Based on T001's findings, implement the minimal fix at the actual failure point
      identified (frontend or backend file, whichever T001 pointed to). **If the fix lands in
      backend pricing-calculation or DuckDB-query logic, write a failing test for that specific
      defect first (Constitution Principle V — NON-NEGOTIABLE for this category) before
      implementing** — only presentational/frontend fixes may skip straight to implementation.
      If T001 finds no reproducible failure (consistent with research.md §1's own
      direct-backend finding), document that explicitly in this task's notes rather than
      guessing at a fix — matching 008's T002 precedent for an unreproducible bug. Depends on
      T001.
      **Done**: T001 found the defect in `search_catalog()`'s DuckDB text filter (catalog-query
      logic) — wrote two failing tests first
      (`test_text_regex_matches_the_skus_own_sku_column`,
      `test_text_regex_sku_match_is_additive_not_a_replacement` in
      `backend/tests/unit/test_catalog_search.py`), confirmed both failed, then added
      `OR regexp_matches(p.sku, ?, 'i')` to the text filter's clause in
      `backend/src/pricing_data/catalog.py::search_catalog`. Both new tests pass; all 8
      pre-existing tests in the file still pass. Verified live against the running dev backend:
      `GET /catalog/skus?q=2AB37QDFJZBGQ5YP` now returns `total: 3` including the SKU itself
      (previously `total: 2`, neither being the SKU itself).
- [X] T003 [P] [US1] Add a regression test in `backend/tests/unit/test_price_calculation.py`
      asserting SKU `2AB37QDFJZBGQ5YP` prices successfully (non-null total, no unpriceable
      entry) for on-demand and at least two Reserved combinations, locking in research.md §1's
      confirmed-working calculation-engine behavior against the known upstream duplicate-row
      data anomaly regressing silently. Depends on T002 (so a fix, if T001/T002 found one
      outside this function, is captured too).
      **Done, with a corrected file target**: `test_price_calculation.py` mocks/monkeypatches
      DuckDB entirely (confirmed by reading it) — the wrong place for a real-data regression
      test. Added `test_duplicate_row_sku_on_demand_still_prices` and
      `test_duplicate_row_sku_every_reserved_combination_still_prices` (parametrized, all 6
      Reserved combinations) to `backend/tests/unit/test_pricing_units.py` instead, which
      already runs `lookup_price`/`lookup_reserved_price` against real Parquet data (matching
      006's own precedent file for exactly this kind of regression). All 17 tests in that file
      pass.

**Checkpoint**: SKU `2AB37QDFJZBGQ5YP` prices correctly (or is explicitly reported
unpriceable), with a regression test locking in the confirmed-working path.

---

## Phase 4: User Story 2 - Price Change reflects a duration-only adjustment (Priority: P1)

**Goal**: Switching Duration alone (no content change) updates Price Change to the real
duration-adjusted comparison.

**Independent Test**: `quickstart.md` US2 scenario.

- [X] T004 [P] [US2] Test-first: add `"duration_only"` cases to
      `frontend/tests/unit/priceChange.test.ts` per data-model.md — (a) content unchanged,
      `prior.duration !== newDuration` → `"duration_only"`; (b) a second call after the
      baseline has already advanced to the new duration, switching back to the original
      duration with content still unchanged → `"duration_only"` again (not `"unchanged"` —
      data-model.md/research.md §2's correction). Confirm these fail against the current
      implementation before proceeding.
- [X] T005 [US2] Implement the `"duration_only"` branch in
      `frontend/src/lib/priceChange.ts`'s `decideBaselineUpdate()` per data-model.md's
      decision table. Depends on T004 (tests must fail first, then pass).
- [X] T006 [US2] Wire the new outcome into `frontend/src/pages/WorkspacePage.tsx`: on
      `"duration_only"`, call the existing `calculate-snapshot` endpoint with the prior
      selections at the new duration (the same call already made for `"duration_adjusted"`),
      update the displayed Price Change from that real result, and advance the stored
      `PriorCalculation.duration`. Depends on T005.
      **Done**: no new branch was actually needed — the existing `calculate.onSuccess` logic
      already special-cased only `"unchanged"` (early return) and `"direct"` (compare against
      the stored total directly); every other decision, including the new `"duration_only"`,
      already fell through to the real `calculateSnapshot()` recalculation generically. Updated
      the surrounding comment to name `"duration_only"` explicitly so this isn't a silent
      coincidence for the next reader. `tsc -b` clean.
- [X] T007 [US2] Live-verify via `quickstart.md` US2 scenario (establish baseline at 1 month,
      switch to 1 year with no other change, confirm Price Change updates; switch back to 1
      month, confirm it returns to the original value). Depends on T006.
      **Findings + resolution (paused mid-task for user input)**: live-verified via
      `claude-in-chrome` — after a real content change (Price Change: +$3,711.32 at 1 month),
      switching Duration to 1 year alone produced **$0.00**, not a ~12x-scaled amount. Traced
      this to a structural property, not a bug: the stored baseline's `selections` always
      advance to match current content on every non-"unchanged" calculate, so by the time
      `"duration_only"` can fire at all, `prior.selections` is *already* identical to
      `currentSelections` — repricing identical content at a new duration is mathematically
      guaranteed to equal the actual new total, i.e. Price Change = $0, always, for every
      possible duration-only transition under this baseline model. The spec's original
      "-100 → -1200" framing is not achievable without a larger baseline-tracking redesign.
      Presented this to the user with the tradeoff; **decision: ship $0.00 as the correct,
      honest answer** (still a real fix over today's bug — the old behavior left Price Change
      frozen at a stale, disconnected number). Updated spec.md (US2 narrative, Independent
      Test, AC1/AC2, FR-002, FR-004) and quickstart.md's US2 section to match this confirmed
      behavior.

**Checkpoint**: A duration-only change updates Price Change correctly in both directions,
test-first covered.

---

## Phase 5: User Story 3 - The architecture diagram stays visible during normal editing (Priority: P1)

**Goal**: The diagram never goes blank while the architecture still has content.

**Independent Test**: `quickstart.md` US3 scenario.

- [X] T008 [US3] Live-reproduce via `claude-in-chrome` with the console open: (1) the user's
      scripted sequence — add an Application Component, add a Service to it, delete the
      Service, delete the Application Component; (2) repeated clicking through diagram elements
      (select, deselect, resize) in varied sequences. This is a continuation of 008's own
      documented, still-open bug (research.md §3) — 008 could not reproduce it in 5 attempts
      without this specific scripted sequence. Instrument/breakpoint around
      `reportHeight`/`initialNodes`/the `setNodes`-reapplying `useEffect` in
      `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` and
      `frontend/src/pages/WorkspacePage.tsx`'s `ownHeights` state per research.md §3's two new
      candidate mechanisms (stale `manualSizeRef`/`ownHeights` entries after a delete; a
      render→effect→parent-state-update loop during rapid add/delete). Record exact findings.
      Do not start T009 until this is recorded.
      **Findings**: Attempted the user's exact scripted sequence four ways: (a) as a single
      Application Component (the only content) — resulted in a correct, empty-but-rendered
      canvas (grid + controls intact), matching the documented non-bug Edge Case, not the
      reported bug; (b) with a second, untouched Application Component present so the
      architecture isn't fully emptied — the second component rendered correctly after the
      full add-service→delete-service→delete-component sequence; (c) the same sequence nested
      inside a VPC (a more complex parent/child state transition) — the VPC rendered correctly,
      empty, after the nested component was deleted; (d) ~10 rapid alternating select/deselect
      clicks across multiple nodes, plus a resize-handle drag and a drag-to-nest operation, in
      varied sequences. Zero console errors/exceptions across all four; zero blank-outs. This
      extends 008's own 5-attempt non-reproduction with 4 more targeted variants (9 total
      across both features) using the newly-available specific repro steps — still
      unreproducible via `claude-in-chrome`.
- [X] T009 [US3] Based on T008's findings, implement the fix — likely pruning
      `manualSizeRef`/`ownHeights` entries for deleted Collection ids and/or guarding the
      `initialNodes`-recompute effect against firing mid-delete, in
      `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` and
      `frontend/src/pages/WorkspacePage.tsx` as T008's findings indicate. If not reproducible
      after a good-faith attempt, document that explicitly (matching 008's own precedent for
      this exact bug) rather than shipping a guess. Depends on T008.
      **No fix applied** — matching 008's own precedent for this exact bug: shipping a
      speculative code change against an unreproduced failure risks a no-op "fix" (008's own
      documented mistake) and violates Constitution Principle VI (no unjustified complexity).
      The two candidate mechanisms from research.md §3 remain plausible but unconfirmed;
      flagged for the user to verify against their own exact repro (browser, extensions,
      timing, or a data shape this tool's `claude-in-chrome` session couldn't reproduce),
      per 008's own conclusion for this identical bug.
- [X] T010 [US3] Live-verify via `quickstart.md` US3 scenario, repeating both the scripted
      sequence and the repeated-click sequence several times to confirm no blank-out. Depends
      on T009.
      **Already covered by T008** — its four-variant investigation *is* this verification (no
      blank-out across any attempt); no additional pass needed since no code changed.

**Checkpoint**: The diagram survives the user's scripted repro and repeated interaction without
going blank (or the investigation's findings are explicitly documented if unreproducible).

---

## Phase 6: User Story 4 - Connectors carry exactly one Service each, and collections can have multiple connectors between them (Priority: P2)

**Goal**: A second Service on an already-occupied Connector is refused, not silently replaced;
multiple Connectors between the same Collections render as distinct edges.

**Independent Test**: `quickstart.md` US4 scenario.

### Backend (test-first, Constitution Principle V)

- [X] T011 [P] [US4] Test-first: extend `backend/tests/integration/test_us2_connectors.py`
      with a case asserting `POST /connectors/{connector_id}/sku-selection` returns `409` with
      a clear `detail` message when the Connector already has a `SKUSelection`, and that the
      existing selection is unchanged afterward (contracts/api.md §1). Confirm it fails against
      the current replace-on-conflict behavior before proceeding.
- [X] T012 [US4] Implement the `409`-on-conflict behavior in
      `backend/src/api/connectors.py::attach_connector_sku`, replacing the existing
      delete-then-insert logic. Depends on T011.
      **Done**: also updated `backend/tests/contract/test_connector_sku_selection.py`'s
      `test_reattaching_sku_replaces_the_previous_one` (renamed to
      `test_reattaching_sku_is_refused_not_replaced`), which had explicitly asserted the old
      replace behavior and now correctly failed after the fix — a necessary consequence of the
      intentional behavior change, not new test-first work. Full backend suite: 156/156 pass.

### Frontend

- [X] T013 [P] [US4] Test-first: add `frontend/tests/unit/edgeOffset.test.ts` for the new
      `edgeOffsetIndex()` helper (data-model.md) — asserts the first edge in a
      source/target-pair group gets offset `0`, subsequent edges in the same (order-independent)
      pair get increasing offsets, and edges with distinct pairs are unaffected by each other.
      Confirm it fails (module doesn't exist yet) before proceeding.
- [X] T014 [US4] Implement `edgeOffsetIndex()` in `frontend/src/lib/edgeOffset.ts` per
      data-model.md. Depends on T013.
- [X] T015 [US4] Wire `edgeOffsetIndex()` into
      `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`'s `initialEdges`
      construction, applying a perpendicular curve offset per edge's computed index so parallel
      Connectors between the same Collection pair render as visually distinct, independently
      clickable paths (FR-010). Depends on T014.
      **Correction found live**: `pathOptions.curvature` (the originally-planned mechanism,
      per research.md §4) does NOT work for this diagram's common horizontally-aligned layout —
      confirmed by inspecting the rendered SVG `d` attributes of two differently-curved edges,
      which were byte-for-byte identical. For `Position.Left`/`Position.Right` handles,
      curvature only extends bezier control points horizontally, producing no visual
      divergence when source/target share the same Y. Replaced with a custom `OffsetEdge`
      component (`edgeTypes`) that displaces the path perpendicular to the straight
      source→target line by the edge's `offsetIndex` — verified live to produce genuinely
      distinct, visibly separated paths regardless of node orientation.
- [X] T016 [US4] Live-verify via `quickstart.md` US4 scenario: confirm a second-Service attempt
      is refused with the `409`'s message rendered via the existing `ErrorMessage`/
      `skuActionError` path in `frontend/src/components/workspace/ServiceConfigPanel.tsx`
      (research.md §4 — no new frontend error-handling code expected here); confirm two
      Connectors between the same Collections render distinctly. Depends on T012, T015.
      **Verified**: attempting a second Service on an occupied Connector shows "This Connector
      already has a Service. Create a new Connector to add another." via the existing
      `ErrorMessage` component (red, with Dismiss), original selection untouched. Two
      Connectors between the same pair render as visibly distinct curved/straight paths,
      confirmed both visually and via the underlying SVG path data. Full frontend suite:
      70/70 pass; `tsc -b` clean.

**Checkpoint**: Connector/Service conflicts are refused with a clear message; multiple parallel
Connectors are visually distinguishable.

---

## Phase 7: User Story 5 - The service search shows how many results are on screen (Priority: P2)

**Goal**: A correctly worded, positioned, and conditionally-styled "n of m services displayed"
indicator.

**Independent Test**: `quickstart.md` US5 scenario.

- [X] T017 [US5] In `frontend/src/components/CatalogSearchPanel.tsx`: reword the existing
      indicator from `"({n} of {m} results displayed)"` to `"n of m services displayed"`; move
      it out of the scrolling results `<div>` to directly below the three filter inputs
      (matching 008's FR-022 fixed-filter-row precedent one `<div>` up); apply the red/warning
      style only when `n < m`, continuing to render unstyled when `n === m`; keep it hidden
      entirely when the search's total match count is zero (FR-011/012/013).
- [X] T018 [US5] Live-verify via `quickstart.md` US5 scenario (a search with more matches than
      shown, a search where all matches are shown, and a zero-match search).
      **Verified**: broad search → "200 of 120646 services displayed" in red, fixed above the
      results list; narrowed to an exact match → "129 of 129 services displayed" in muted gray
      (not red); zero-match search → indicator hidden entirely, only "No matching services
      found." shown.

**Checkpoint**: The coverage indicator matches FR-011-013 exactly.

---

## Phase 8: User Story 6 - Pricing values are easier to read and reflect the correct data timestamp (Priority: P2)

**Goal**: Thousand separators on every pricing value; the verbose snapshot sentence replaced by
a "Data Timestamp" line.

**Independent Test**: `quickstart.md` US6 scenario.

- [X] T019 [US6] Add thousand-separator grouping to `formatPrice()` in
      `frontend/src/components/workspace/PricingPanel.tsx` (e.g.
      `Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })`),
      reused at all three existing call sites (total, Price Change, per-SKU breakdown) (FR-014).
- [X] T020 [US6] In the same file: remove the
      `"For {duration}, priced from snapshot {date}"` paragraph; add a
      `"Data Timestamp: {date}"` line at the bottom of the column, reading the same
      `calculation.snapshot_date` field (FR-015/016).
- [X] T021 [US6] Live-verify via `quickstart.md` US6 scenario (a total in the thousands or
      more; confirm the old sentence is gone and the new line is present with the correct
      date).
      **Verified**: "Total: 105,433.17 USD" and per-SKU line both show thousand separators;
      the old "For 1 month, priced from snapshot..." sentence is gone; "Data Timestamp:
      2026-09-11" appears at the bottom of the column.

**Checkpoint**: Pricing values are grouped and the column shows the corrected data-timestamp
copy.

---

## Phase 9: User Story 7 - The architecture diagram is easier to read and its layout survives a reload (Priority: P3)

**Goal**: Less visual clutter, clearer boundaries, one well-indicated resize affordance, larger
spacing, smaller diagram text, underlined selection, and size/position that survive a reload.

**Independent Test**: `quickstart.md` US7 scenario.

- [ ] T022 [P] [US7] Test-first: add `frontend/tests/unit/diagramLayout.test.ts` for the new
      `diagramLayout.ts` module (data-model.md) — read/write round-trip for one Architecture's
      layout, the `try/catch`-guarded no-op behavior when `localStorage` throws, and the
      per-Architecture key scoping (`cloud-pricing-diagram-layout-{architectureId}`). Confirm
      it fails (module doesn't exist yet) before proceeding.
- [ ] T023 [US7] Implement `frontend/src/lib/diagramLayout.ts` per data-model.md's
      `DiagramLayout`/`CollectionLayoutOverride` shapes, modeled on `columnWidths.ts`'s existing
      pattern. Depends on T022.
- [ ] T024 [P] [US7] In `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`: drop
      the `` (${c.type})` `` suffix from both node-label call sites (top-level and nested
      children) (FR-017).
- [ ] T025 [P] [US7] In the same file: darken `VpcNode`'s and `ApplicationComponentNode`'s
      border classes (verified live against both light and dark theme); add a border class to
      each `ServiceList` item (FR-018/019).
- [ ] T026 [US7] In the same file: restrict `<NodeResizer>` to only its bottom-right handle
      (dropping the default all-eight-handle set) for both node types, and style its visual
      resize-affordance indicator consistently with the diagram panel's existing whole-panel
      `resize-y` handle (FR-020/021).
- [ ] T027 [US7] In the same file: reduce node/edge label Tailwind text-size utility classes by
      three steps from 008's sizing (FR-022, diagram half). Separately — app-wide, not only in
      files this feature otherwise touches — reduce every remaining text-size utility class by
      one further step from 008's sizing (FR-022, app-wide half: columns 1-5 in full, including
      ProviderArchitecturePanel.tsx, CollectionsPanel.tsx, and ServiceConfigPanel.tsx even
      though no other task in this feature touches them) — following 008's established
      per-class step-down convention (research.md §7/§10 there), never a global CSS
      `font-size` override.
- [ ] T028 [US7] Increase `VPC_CHILD_SPACING` in `frontend/src/pages/nodeLayout.ts` and the
      top-level layout's grid-spacing constants in `ArchitectureDiagramPanel.tsx`'s
      `initialNodes` positioning to a visibly larger fixed value (FR-023).
- [ ] T029 [US7] Wire `diagramLayout.ts` into `ArchitectureDiagramPanel.tsx`: read the stored
      layout on load to seed the manual-override map (extended to carry `x`/`y` alongside the
      existing `width`/`height`); write on `<NodeResizer>`'s `onResizeEnd` and on
      `onNodeDragStop` (FR-024, also fixing the in-session position-loss noted in research.md
      §7a as a byproduct). Depends on T023.
- [ ] T030 [US7] In the same file: apply `underline` to whichever Application Component's,
      Connector's, or Service's name is currently selected, based on the existing
      `selected`/id-comparison props each already receives; no other name may be underlined at
      the same time (FR-025).
- [ ] T031 [US7] Live-verify via `quickstart.md` US7 scenario, including a page reload to
      confirm size/position persistence. Depends on T024, T025, T026, T027, T028, T029, T030.

**Checkpoint**: The diagram reads more clearly, resizes only from its indicated corner, and a
user's manual size/position adjustments survive a reload.

---

## Phase 10: User Story 8 - Adding a Connector doesn't require selecting two Collections first (Priority: P3)

**Goal**: An "Add Connector" button opens a dialog with From/To Collection dropdowns.

**Independent Test**: `quickstart.md` US8 scenario.

- [ ] T032 [US8] Add the shadcn `Dialog` primitive at `frontend/src/components/ui/dialog.tsx`
      (research.md §8 — a copied-in source file per this project's existing shadcn convention,
      alongside `select.tsx`/`button.tsx`; no new npm dependency).
- [ ] T033 [US8] Build the "Add Connector" dialog in
      `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` (or a small sibling
      component it renders): "From Collection"/"To Collection" `<Select>` dropdowns (reusing
      the existing `components/ui/select.tsx`) populated from the `collections` prop already
      available; disable/reject confirming with the same Collection chosen in both (FR-026a),
      and disable confirming whenever fewer than two distinct Collections exist in the
      Architecture (Edge Cases);
      on confirm, call the existing `onCreateConnector(from, to)` prop verbatim (the same
      mutation `WorkspacePage.tsx`'s pre-existing `handleConnect()` already uses). Depends on
      T032.
- [ ] T034 [US8] Add the "Add Connector" button to the diagram panel's UI, opening the new
      dialog with no pre-selection required (FR-026). Depends on T033.
- [ ] T035 [US8] Live-verify via `quickstart.md` US8 scenario, including confirming the
      pre-existing select-two-and-connect flow still works unchanged. Depends on T034.

**Checkpoint**: A Connector can be created via the new dialog, with the same-Collection guard
enforced, without disturbing the existing connect flow.

---

## Phase 11: User Story 9 - AWSDataTransfer services are identifiable by region pair (Priority: P3)

**Goal**: `AWSDataTransfer` services show a derived `{fromRegionCode}=>{toRegionCode}` label
everywhere they appear, with dedicated region filters in search.

**Independent Test**: `quickstart.md` US9 scenario.

### Backend (test-first, Constitution Principle V)

- [ ] T036 [P] [US9] Test-first: extend `backend/tests/unit/test_catalog_search.py` with cases
      for the new `from_region_code`/`to_region_code` filters on `search_catalog()` (contracts/
      api.md §2) — each filters correctly, both AND-combine with existing filters and with each
      other, and either alone satisfies the "at least one filter" requirement. Confirm these
      fail (parameters don't exist yet) before proceeding.
- [ ] T037 [US9] Implement the two new parameters in
      `backend/src/pricing_data/catalog.py::search_catalog` (the
      `json_extract_string(p.attributes_json, '$.fromRegionCode'/'$.toRegionCode')` regex
      clauses per contracts/api.md) and thread them through
      `backend/src/api/catalog.py::search_skus`'s query-parameter signature. Depends on T036.

### Frontend

- [ ] T038 [P] [US9] Test-first: add `frontend/tests/unit/awsDataTransfer.test.ts` for
      `awsDataTransferLabel()` (data-model.md) — derives the label for a well-formed
      `AWSDataTransfer` SKU, returns `null` for a non-`AWSDataTransfer` service code, and
      returns `null` (not a broken partial string) when either region field is absent
      (research.md §9's missing-field edge case). Confirm it fails (module doesn't exist yet)
      before proceeding.
- [ ] T039 [US9] Implement `awsDataTransferLabel()` in
      `frontend/src/lib/awsDataTransfer.ts` per data-model.md. Depends on T038.
- [ ] T040 [US9] Add `from_region_code`/`to_region_code` parameters to
      `frontend/src/api/client.ts`'s `searchCatalog()`, then run
      `cd frontend && npm run check-api-types` to confirm the generated types stay in sync
      (Constitution Principle IV). Depends on T037.
- [ ] T041 [US9] Wire `awsDataTransferLabel()` into `frontend/src/components/CatalogSearchPanel.tsx`'s
      `summaryText()`, `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`'s
      `ServiceList` item text, and `frontend/src/components/workspace/PricingPanel.tsx`'s
      per-SKU breakdown line — each falling back to its existing default label when the helper
      returns `null` (FR-027/028/030). Depends on T039.
- [ ] T042 [US9] Add conditional "From region"/"To region" input fields to
      `frontend/src/components/CatalogSearchPanel.tsx`, shown when the `service_code` filter
      matches `AWSDataTransfer`, wired to the new search parameters (FR-029). Depends on T040.
- [ ] T043 [US9] Live-verify via `quickstart.md` US9 scenario, including a transfer with a
      missing region code (internet/CloudFront destination) falling back correctly, and a
      non-`AWSDataTransfer` service being entirely unaffected. Depends on T041, T042.

**Checkpoint**: AWSDataTransfer services are identifiable by region pair everywhere they
appear, with working region filters.

---

## Phase 12: Polish & Cross-Cutting Concerns

- [ ] T044 [P] Run the full backend suite (`cd backend && pytest`) and fix any regressions
      surfaced by this feature's changes.
- [ ] T045 [P] Run the full frontend suite (`cd frontend && npm test`) and fix any regressions.
- [ ] T046 Run `cd frontend && npm run check-api-types` end-to-end and confirm it's clean
      (Constitution Principle IV) — a final check after both backend contract changes (T012's
      sibling schema stays unchanged; T037's new query params).
- [ ] T047 Walk `quickstart.md`'s full "Regression check" section end-to-end.
- [ ] T048 [P] Review every file touched during the live-repro tasks (T001, T008) for stray
      `console.log`/debug instrumentation added while investigating, and remove it.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No tasks — no dependency.
- **Foundational (Phase 2)**: No tasks — no dependency.
- **User Stories (Phase 3-11)**: Each depends only on tasks within its own phase (research.md
  confirms no cross-story file overlap) — all nine may proceed in parallel if staffed, or
  sequentially in spec.md's priority order (US1, US2, US3 → US4, US5, US6 → US7, US8, US9).
- **Polish (Phase 12)**: Depends on all desired user stories being complete.

### Within Each User Story

- US1/US3: live reproduction MUST come before any fix; a regression test (US1) or live
  re-verification (US3) comes after.
- US2/US4/US7/US9: test-first tasks (marked accordingly) MUST fail before their implementation
  task, per Constitution Principle V.
- Every story's final task is a live-verification pass against its `quickstart.md` scenario.

### Parallel Opportunities

- T003 (US1's regression test) can be drafted in parallel with T001/T002's investigation, but
  should assert against whatever T002 actually fixes — sequenced here for correctness, not a
  hard file conflict.
- T004 (US2), T011/T013 (US4), T022 (US7), T036/T038 (US9) — every test-first task marked `[P]`
  can be written in parallel with other stories' test-first tasks (different files).
- T024/T025 (US7) are marked `[P]` — different concerns in the same file but non-overlapping
  edits (label text vs. border classes); safe to parallelize by two contributors coordinating on
  that one file, or do sequentially solo.
- Different user story phases (US1 through US9) can be worked on fully in parallel by different
  contributors once each story's own first task is unblocked — there is no Foundational gate.
- T044/T045/T048 (Polish) can run in parallel with each other.

---

## Parallel Example: User Stories 4 and 9 (both have independent backend + frontend halves)

```bash
# US4 backend and US9 backend can proceed in parallel (different files):
Task: "T011 [US4] extend test_us2_connectors.py with the 409-conflict case"
Task: "T036 [US9] extend test_catalog_search.py with from/to region-code cases"

# US4 frontend and US9 frontend can proceed in parallel with each other, and with either
# backend half above:
Task: "T013 [US4] edgeOffset.test.ts"
Task: "T038 [US9] awsDataTransfer.test.ts"
```

---

## Implementation Strategy

### MVP First (Through User Story 3)

1. Complete Phase 3 (US1), Phase 4 (US2), Phase 5 (US3) — the three P1 correctness/stability
   fixes.
2. **STOP and VALIDATE**: run `quickstart.md`'s US1-US3 scenarios independently.
3. Deploy/demo if ready — the three most user-visible correctness bugs are fixed even before
   any P2/P3 polish lands.

### Incremental Delivery

1. US1 → US2 → US3 (P1): ship the correctness fixes first.
2. US4 → US5 → US6 (P2): Connector/Service correction, search coverage indicator, pricing
   formatting.
3. US7 → US8 → US9 (P3): diagram polish/persistence, Add Connector dialog, AWSDataTransfer
   handling.
4. Each story adds value without breaking any previous story — research.md confirms zero
   cross-story file overlap.

### Parallel Team Strategy

With multiple developers, since there is no Foundational gate: assign each user story to a
different developer immediately. Backend-touching stories (US1's investigation, US4, US9) pair
naturally with a developer comfortable in `backend/src/`; the rest are frontend-only.

---

## Notes

- [P] tasks = different files, no dependency on an incomplete task.
- [Story] label maps task to specific user story for traceability.
- US1 and US3 are investigative-first (live repro before fix) per research.md §1/§3 — do not
  skip the repro task or write a fix against a guess.
- Verify test-first tasks fail before implementing (US2, US4's two halves, US7's
  `diagramLayout.ts`, US9's two halves).
- Commit after each task or logical group.
- Stop at any checkpoint to validate a story independently.
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence.

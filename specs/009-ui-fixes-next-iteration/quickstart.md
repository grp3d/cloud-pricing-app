# Quickstart: UI Fixes and Enhancements — Next Iteration

Validation guide for the nine user stories in spec.md. Backend logic changes (US1's
investigation, US2, US4's conflict rule, US9's region filters) get automated tests per
Constitution Principle V; everything else is presentational and is live-verified per Principle
V's UI carve-out (matching 007/008's precedent), using `claude-in-chrome` against the running
dev app.

## Prerequisites

- Backend running (`cd backend && uvicorn src.main:app --reload`) with `DATABASE_URL` pointing
  at a working Postgres instance and `aws_pricing_parquet_dir` (see `backend/src/config.py`)
  resolving to a real Parquet dataset with at least one recent `snapshot_date` partition.
- Frontend running (`cd frontend && npm run dev`), pointed at that backend.
- At least one Architecture with a couple of Collections (one VPC, one Application Component)
  and a Connector between them, to exercise US3/US4/US7/US8 live.
- Backend tests: `cd backend && pytest`. Frontend unit tests: `cd frontend && npm test`.
  Type-contract gate: `cd frontend && npm run check-api-types` (must be run after any backend
  schema/query-param change per contracts/api.md, Constitution Principle IV).

## US1 — SKU `2AB37QDFJZBGQ5YP` prices successfully

1. In column 2's "Add a Service" search, find and add SKU `2AB37QDFJZBGQ5YP` (search
   `m5.16xlarge` or `AmazonEC2` + text `2AB37QDFJZBGQ5YP`) to a Collection.
2. Configure it (any pricing term/purchase option) and run a calculation (column 5).
3. **Expected**: the calculation succeeds; this SKU contributes a real price to the total, or —
   only if genuinely unpriceable — appears as an explicit unpriceable line, never a
   calculation-wide failure (FR-001, SC-001).
4. If a failure *is* reproduced, capture the exact step and any console error before fixing —
   research.md §1 found the calculation engine itself does not fail for this SKU in isolation,
   so the failure point is elsewhere in this live flow.

## US2 — Price Change reflects a duration-only adjustment

1. Open an Architecture with an established Prior Calculation baseline at 1 month (calculate
   once to establish one if needed).
2. Note the displayed Price Change value.
3. Switch Duration to 1 year, making no other change.
4. **Expected**: Price Change updates to the duration-adjusted comparison (not left at the old
   value) — cross-check it matches what a content-and-duration change would have produced for
   an equivalent scenario (FR-002/003, SC-002).
5. Switch Duration back to 1 month. **Expected**: Price Change returns to its original value
   (FR-004).
6. Automated coverage: `frontend/tests/unit/priceChange.test.ts` — add a `"duration_only"` case
   (data-model.md) before implementing the branch (test-first, Constitution Principle V).

## US3 — The architecture diagram stays visible during normal editing

1. **Scripted repro (do this first, before any fix)**: add an Application Component, add a
   Service to it, delete the Service, delete the Application Component.
   **Expected today (bug)**: the diagram may go blank. **Expected after fix**: the diagram
   continues showing the architecture's remaining content (FR-005).
2. Click through a variety of diagram elements in sequence (select, deselect, select another,
   resize) several times. **Expected**: the diagram never renders as blank space while the
   architecture still has content (FR-006).
3. If either reproduces, use `read_console_messages` to capture any thrown error before
   changing code — research.md §3 has two candidate mechanisms to check first.

## US4 — Connectors carry one Service; multiple Connectors are distinguishable

1. Attach a Service to a Connector that has none. **Expected**: succeeds as today.
2. Attempt to attach a second Service to that same Connector. **Expected**: refused with a
   clear inline message (via the existing `ErrorMessage` pattern); the Connector still shows
   its original Service (FR-008, SC-004).
3. Create a second Connector between the same two Collections, each with its own Service.
   **Expected**: both render as distinguishable, independently clickable edges — neither fully
   overlaps the other (FR-009/010).
4. Automated coverage: a new backend integration test (`tests/integration/`, alongside
   `test_us2_connectors.py`) asserting the `409` on conflict, test-first; a frontend unit test
   for the new `edgeOffsetIndex()` helper (data-model.md), test-first.

## US5 — Service search shows "n of m services displayed"

1. Search for something with more than the currently-displayed number of matches (e.g. a broad
   `service_code` like `AmazonEC2`).
2. **Expected**: text reading "n of m services displayed" appears directly below the three
   search fields, above the results list, styled in red (FR-011/012).
3. Narrow the search until every match is displayed (n equals m). **Expected**: same text
   shown, no longer styled as a warning (FR-012).
4. Search something with zero matches. **Expected**: no "n of m" text at all (FR-013).

## US6 — Pricing values are easier to read

1. Calculate a price whose total is in the thousands or more.
2. **Expected**: the total, Price Change, and every per-SKU breakdown line show comma thousand
   separators (FR-014, SC-006).
3. **Expected**: the "For {duration}, priced from snapshot {date}" sentence is gone; a
   "Data Timestamp: {date}" line appears at the bottom of column 5 with the same date
   (FR-015/016).

## US7 — The architecture diagram is easier to read and its layout survives a reload

1. Open a diagram with a Collection. **Expected**: no collection-type text shown; darker
   Collection border; each Service has its own border (FR-017/018/019).
2. Select an Application Component, Connector, and Service in turn. **Expected**: only the
   currently-selected one's name is underlined at any time (FR-025).
3. Try dragging a Collection box from its bottom-right corner (resizes, with a visible
   indicator there) and from another edge/corner (does not resize) (FR-020/021).
4. Resize a box, then move it. Reload the page. **Expected**: the same size and position
   persist (FR-024, SC-007) — check `localStorage` for the new
   `cloud-pricing-diagram-layout-{architectureId}` key (data-model.md).
5. **Expected**: diagram text is visibly smaller than the rest of the UI (three steps down);
   non-diagram text is visibly smaller than 008's sizing (one step down); spacing between
   diagram components is visibly larger than before (FR-022/023).

## US8 — "Add Connector" button

1. With at least two Collections and nothing pre-selected, click "Add Connector".
2. **Expected**: a dialog opens with "From Collection"/"To Collection" dropdowns listing every
   Application Component and VPC (FR-026).
3. Pick the same Collection in both dropdowns. **Expected**: cannot confirm (FR-026a).
4. Pick two different Collections and confirm. **Expected**: a new Connector is created between
   them, dialog closes.
5. Confirm the pre-existing select-two-and-connect flow still works unchanged.

## US9 — AWSDataTransfer services show a region-pair label

1. Search with `service_code` `AWSDataTransfer`. **Expected**: two additional "From region"/"To
   region" fields appear (FR-029); narrowing by either filters results.
2. Add an `AWSDataTransfer` result. **Expected**: it displays as `{fromRegionCode}=>{toRegionCode}`
   in the search results, the diagram, and (after calculating) the per-SKU price breakdown —
   not the raw SKU (FR-027/028).
3. Find (or search for) a transfer with an external/CloudFront destination (no `toRegionCode`).
   **Expected**: falls back to the existing default label rather than showing a broken
   `"...=>"` string (research.md §9).
4. Add a non-`AWSDataTransfer` service. **Expected**: entirely unaffected, displays as today
   (FR-030).

## Regression check

- `cd backend && pytest` — full suite green, including any new test-first tests above.
- `cd frontend && npm test` — full suite green, including `priceChange.test.ts`'s new case and
  the new `edgeOffsetIndex`/`awsDataTransferLabel`/`diagramLayout` unit tests.
- `cd frontend && npm run check-api-types` — clean (no diff) after the two backend contract
  changes in contracts/api.md.

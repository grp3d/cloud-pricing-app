# Quickstart: UI Updates and Corrections

Validates: FR-001–FR-025 (incl. FR-016a/016b), SC-001–SC-010. Unlike 007, this feature
touches **both** `backend/` and `frontend/` — both dev servers must be running, and
`check-api-types` must be re-run after the backend changes land, before/alongside frontend
work that depends on the new `CatalogSearchResult.total` field and the new
`calculate-snapshot` endpoint's generated types.

## Prerequisites

- Backend and frontend dev servers both running per this repo's existing setup.
- At least one AWS Architecture with: a VPC containing a nested Application Component, at
  least two services added across its boxes, a Data Connector between two Collections, and
  at least one Reserved-term SKU Selection (for FR-016a's duration-adjustment scenario,
  since Reserved pricing doesn't scale linearly with duration — 006).
- `screenshot-samples/gcp_icon.png` and `azure_icon.png` present (already true as of this
  writing); `aws_icon.png` supplied before Scenario 4's AWS-icon check can pass (Assumptions
  — otherwise skip only that one assertion).

## Scenario 1 — Diagram reliability and sizing (US1, FR-001–FR-004)

**Diagnosis-first**: before implementing a fix, reproduce 1b and 1c below with the browser
DevTools console open in a real, focused browser tab (not `claude-in-chrome` — research.md
§1b/1c explain why that tool can't observe this reliably) and record what actually happens
(a thrown error with a stack trace? no error, but nodes render off-screen? something else?)
before writing the fix those two need.

1. **(FR-001)** Select a box, drag its resize handle to a new size. Click elsewhere to
   deselect, then reselect the same box.
   - **Expected**: the box is still the size the user set — not reverted to its
     auto-computed size.
2. **(FR-002)** Add enough services to a box that its content would need more than one
   line beyond its current size.
   - **Expected**: the box grows to show every line of its own label and service list, with
     no clipped text and no scrollbar appearing where the box could simply be taller
     instead.
3. **(FR-003)** Click an empty area inside a VPC box (not on a nested child, not on the
   VPC's own label).
   - **Expected**: the diagram remains fully visible and interactive; nothing disappears;
     no reload is needed to recover. (See Diagnosis-first above if this still fails.)
4. **(FR-004)** Drag the diagram panel's own resize handle (bottom-right).
   - **Expected**: the panel grows to at least double its current default height ceiling
     (SC-003).

## Scenario 2 — Column 3 always present; columns 1-3 collapsible (US2, FR-005/006)

1. With an Architecture open, select a service (column 3 populates), then click empty
   diagram space to deselect.
   - **Expected**: column 3 stays at its normal width, showing a blank/placeholder state —
     it does not collapse to zero width (unlike 007's prior behavior).
2. Click column 2's collapse icon (top-right), then column 3's.
   - **Expected**: each collapses to an icon-only rail independently, matching column 1's
     existing collapsed behavior (icons, hover tooltips, every action still reachable).
3. Expand each again.
   - **Expected**: each returns to its normal width and content.

## Scenario 3 — Column/section labels (US3, FR-007–FR-011)

1. Expand column 1. Confirm AWS, GCP, and Azure are each on their own line, and neither GCP
   nor Azure show "(soon)" text (their buttons stay disabled/non-functional — Edge Cases).
2. Collapse column 1. Confirm each provider shows its own icon (not a generic placeholder) —
   skip the AWS assertion if `aws_icon.png` hasn't been supplied yet (Assumptions).
3. With an Architecture open, confirm column 2's header reads "Architecture Editor" and its
   three sections read "Collections", "Selected Collection", "Add a Service", with a visible
   separator between each pair — including when the section between two separators (e.g.
   "Selected Collection" with nothing selected) is empty.
4. Confirm column 3's header reads "Service Editor", with or without a service selected.

## Scenario 4 — Adjustable, persisted column widths (US4, FR-012/013, SC-005)

1. Drag the boundary between columns 2 and 3 to a new position.
   - **Expected**: both columns' widths update live, clamped so neither shrinks below its
     own usable minimum (its collapsed-rail width — research.md §9).
2. Reload the page in the same browser.
   - **Expected**: the resized widths are exactly as left — not reset to defaults.
3. Open the same URL in a different browser (or a private window).
   - **Expected**: default widths — per-browser persistence (Clarifications) intentionally
     does not follow across browsers/devices.

## Scenario 5 — Pricing display: rounding, Price Change, Price per Sku (US5,
FR-014–FR-017/016a/016b, SC-006–SC-008)

1. Calculate a price. Confirm the total, and every other displayed price, shows exactly 2
   decimal places (no long floating-point remainders).
2. **(First-ever calculate for this Architecture, or after clearing browser storage)**
   Confirm no Price Change value is shown yet.
3. Add a service (an architecture content change), Calculate again.
   - **Expected**: a Price Change value appears equal to (new total − prior total), with a
     red upward arrow if it increased, green downward if decreased, no arrow if unchanged.
4. Calculate again with **no** change (or only a Duration change) since the last
   calculation.
   - **Expected**: the Price Change value and arrow are unchanged from step 3 — the
     baseline did not silently reset (FR-016).
5. Change the architecture (e.g. remove a service) **and** the Duration selection together,
   then Calculate.
   - **Expected**: Price Change reflects only the architecture edit's effect — verify by
     independently computing what the *prior* architecture would have cost at the *new*
     Duration (e.g. via a second, separate Calculate against a duplicate/rollback of that
     prior state) and confirming the displayed Price Change matches (new total − that
     duration-adjusted prior total), not (new total − the original, un-adjusted prior
     total) (FR-016a — this is the scenario the Reserved-term SKU in Prerequisites is for,
     since a naive linear scaling would visibly disagree with the real recalculation here).
6. Reload the page, then Calculate again with no change.
   - **Expected**: Price Change is still correct, not reset to "first ever calculate" —
     confirms FR-016b's per-browser persistence survived the reload.
7. Confirm a "Price per Sku" section appears below the main result, separated by a visible
   divider, listing every priced SKU with its own total price, sorted highest-price-first
   (SC-008: the most expensive SKU should be immediately identifiable, at the top).

## Scenario 6 — Service search: regex, sticky filters, 200 cap, count, sort (US7,
FR-020–FR-025, SC-009/010)

1. In "Add a Service", type a regex pattern into the service-code field (e.g. `Amazon(EC2|
   S3)`), confirming matches from both services are returned.
2. Type a regex pattern into the product-family and free-text fields independently,
   confirming each is pattern-matched on its own.
3. Type a syntactically invalid pattern (e.g. an unterminated `[`) into any field.
   - **Expected**: a clear, in-place message next to that field — no crash, no silently
     empty results.
4. Run a broad search returning many results. Scroll the results list.
   - **Expected**: the three filter fields stay fixed in view; only the results below them
     scroll.
5. Confirm up to 200 results are returned (raised from 50) — matches the backend's existing
   ceiling (research.md §4), so no backend change should have been needed for this part
   specifically.
6. Run a search with more matches than are displayed.
   - **Expected**: a "(n of m results displayed)" note appears, with `m` the true total
     (confirm against `CatalogSearchResult.total` in the network response — not an
     estimate).
7. Run a search where every match is already displayed (e.g. a narrow filter).
   - **Expected**: no "(n of m)" note is shown.
8. Confirm results are sorted alphabetically by the same summary text shown for each
   result, not by an unrelated internal order.

## Scenario 7 — Visual style (US6, FR-018/019)

1. Compare any panel's text against its pre-008 size.
   - **Expected**: one Tailwind text-size step smaller, consistently.
2. Compare themed elements (buttons, active states, panel accents) against pre-008.
   - **Expected**: Radix "sky" color scale throughout, except the diagram's own node/edge
     rendering (007's documented exception, unchanged).

## Notes

- Re-run `npm run check-api-types` after backend changes land (`CatalogSearchResult.total`,
  the new `calculate-snapshot` endpoint) — this feature is the first since 006 to touch the
  API surface, so a clean type-check here is a real regression check, not a formality.
- Per Constitution Principle V, the backend query changes (regex matching, total count,
  `calculate-snapshot`) and the frontend's baseline-update decision logic
  (`frontend/src/lib/priceChange.ts`) are test-first; everything else in this quickstart is
  the primary validation method for presentational work, per the same precedent 005/007
  established.
- Run the existing backend and frontend test suites once at the end as a regression check.

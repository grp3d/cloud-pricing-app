# Quickstart: Resizable Canvas & Reliable Box Sizing

Validates: FR-001–FR-005, SC-001–SC-003. See `spec.md` for full acceptance scenarios and
`research.md` for the chosen approach (native CSS canvas resize; real DOM-measured box
height instead of an estimate).

## Prerequisites

- Backend and frontend dev servers running per this repo's existing setup (unchanged by
  this feature — no new dependency, no schema/migration to apply).
- An Architecture with at least one VPC containing a nested Application Component, and at
  least one SKU selection whose identifying-detail text is long enough to wrap to more than
  one line at the default box width (needed to exercise US2 — see `spec.md`'s Independent
  Test).

## Scenario 1 — Resize the canvas (US1, FR-001, FR-002, SC-001)

1. Open an Architecture's assembly canvas page.
2. Drag the resize grip at the bottom-right corner of the canvas viewport.
   - **Expected**: the visible canvas area grows/shrinks in a single drag gesture (SC-001);
     it cannot be dragged below a usable minimum (Edge Case).
3. At the resized size, pan, zoom, select a box, select a connector, and drag a box.
   - **Expected**: every interaction still works exactly as before (FR-002).
4. Reload the page.
   - **Expected**: the canvas returns to its default size (Assumption — not persisted).

## Scenario 2 — A long detail line never clips (US2, FR-003, SC-002)

1. On a box (Application Component or VPC), add a SKU whose identifying-detail text is long
   enough to wrap to 2+ lines at the box's current width.
2. Observe the box.
   - **Expected**: the box is tall enough to show that service's full text — no clipping,
     no truncation, no overlap with a neighboring or nested box (SC-002).
3. Remove that SKU (or replace it with a short one).
   - **Expected**: the box's height shrinks back down to fit its new (shorter) content
     (FR-004) — it doesn't stay artificially tall.

## Scenario 3 — Cascading growth through nesting (US2, FR-005)

1. In a VPC that already contains a nested Application Component, add enough long-detail
   SKUs to the *nested* component that its own box grows taller.
2. Observe the containing VPC box.
   - **Expected**: the VPC box also grows to keep fully containing the taller nested box —
     no overlap between the nested box and the VPC's own content/border (FR-005, carried
     forward from `004`).

## Scenario 4 — Manual width resize still works (Assumptions — width unaffected)

1. Drag a box's own resize handle (from `004`) to make it narrower.
   - **Expected**: the box narrows, and — since less width means the same text wraps to
     more lines — the box's height grows if needed to keep showing that content in full
     (still no clipping; height reliability isn't defeated by a width change).
2. Add a new SKU to that same box (a content change).
   - **Expected**: consistent with the unchanged Edge Case rule from `004`, the box's size
     is now driven by its content fit again — a previous manual size no longer overrides it.

## Notes

- Scenarios 1–4 are validated live in-browser (`claude-in-chrome`), not purely via unit
  tests — see `research.md` §3 for why (real text-wrap/clipping can only be proven by an
  actual browser layout, not a mocked `ResizeObserver`).
- The pure Y-offset/parent-height stacking math (given a map of measured child heights) is
  covered by unit tests in `frontend/tests/unit/nodeLayout.test.ts`.

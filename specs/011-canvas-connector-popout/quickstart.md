# Quickstart: Canvas Connector & Pop-Out Improvements

Validation guide for the three user stories in spec.md. This feature is entirely
presentation-layer (frontend only, no backend/API changes — spec Assumptions), so all
validation is live, per Constitution Principle V's presentational-code carve-out (matching
`005`'s/`007`'s precedent), using `claude-in-chrome` against the running dev app. Any pure
logic extracted per research.md §5 (connect pre-population ordering, resize math) gets
test-first Vitest coverage before this live pass.

## Prerequisites

- Backend running (`cd backend && uvicorn src.main:app --reload`) with `DATABASE_URL` pointing
  at a working Postgres instance and a real Parquet dataset (unchanged by this feature — needed
  only so the workspace has real Collections/Services to exercise).
- Frontend running (`cd frontend && npm run dev`), pointed at that backend.
- An Architecture with at least two Collections (e.g. one VPC, one Application) to exercise
  US1/US2 live.
- Frontend unit tests: `cd frontend && npm test`.

## US3 — More legible canvas text

1. Open any Architecture with at least one Collection and view column 4's canvas at its default
   zoom level.
2. **Expected**: Collection names, Connector labels, and region labels are visibly larger than
   before (`text-2xs`/11px vs. the prior `text-3xs`/10px — research.md §1), the diagram's zoom
   level is unchanged, and no label text overflows or clips its box (FR-001, precedent: 004/008's
   narrow-column overflow issue).

## US2 — One consolidated way to create a Connector

1. Confirm column 4's canvas no longer shows its own "Add Connector" button/panel (FR-002).
2. With **zero** Collections selected on the canvas, click "Connect" in column 2.
   **Expected**: a dialog opens with empty "From Collection"/"To Collection" dropdowns (FR-005).
3. Close it. Select **exactly one** Collection on the canvas, then click "Connect".
   **Expected**: "From Collection" is pre-populated with that Collection; "To Collection" is
   empty (FR-005).
4. Close it. Select **two** Collections on the canvas in a specific order, then click "Connect".
   **Expected**: "From Collection"/"To Collection" are pre-populated with the first/second
   selected Collections respectively (FR-005), and no Connector exists yet — it's only created
   after clicking "Add Connector" inside the dialog (FR-006).
5. Click "Add Connector" inside the dialog. **Expected**: the Connector is created exactly as
   it would have been under the old immediate-connect behavior — same arrow/direction on the
   diagram.
6. **Expected** throughout: the "Connect" button in column 2 is always clickable, regardless of
   how many Collections are currently selected (FR-004 — previously disabled unless exactly two).

## US1 — Pop out the architecture canvas

1. Click the pop-out ([↗]) icon in column 4's canvas's top-right corner (FR-007).
   **Expected**: an enlarged, resizable overlay opens within the same browser tab (not a new
   browser window — Clarifications), showing the same architecture.
2. Drag the overlay's resize grip. **Expected**: the canvas inside it adjusts to the new size
   (FR-008).
3. While the overlay is open, in columns 2/3: add a Service to a Collection, add a Connector,
   and rename or move a Collection. **Expected**: each change appears in the pop-out's canvas
   without manually refreshing or reopening it (FR-009), typically within a couple seconds
   (SC-004).
4. While the overlay is open, select and pan/zoom within **column 4's own canvas** (behind/below
   the overlay, or after temporarily closing it). **Expected**: column 4's canvas remains fully
   interactive on its own — selecting, connecting, etc. — independent of the pop-out (FR-011).
5. Close the overlay via its close button, then reopen it and close it via Escape instead.
   **Expected** both times: column 4's canvas becomes the active view again, showing the
   architecture's current state, with no page reload (FR-010, SC-005). Also confirm clicking on
   column 4's own canvas while the pop-out is open does *not* close the pop-out (Edge Cases) —
   it's a live interaction with column 4, not a dismiss gesture.
6. Repeat step 1 while the overlay is already open (e.g. via a second trigger if reachable).
   **Expected**: the existing overlay is brought into focus, not duplicated (Edge Cases).

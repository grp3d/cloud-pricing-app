---

description: "Task list for Canvas Connector & Pop-Out Improvements"
---

# Tasks: Canvas Connector & Pop-Out Improvements

**Input**: Design documents from `/specs/011-canvas-connector-popout/`

**Prerequisites**: plan.md, spec.md, research.md, quickstart.md (all present). No
`data-model.md`/`contracts/` — no data-model or API-contract changes. `backend/` is
untouched throughout.

**Tests**: Minimal, by design (Constitution Principle V's presentational-code carve-out,
research.md §5) — this is layout/interaction work, not pricing or data-relationship logic.
No new pure logic is extracted for this feature (resize/selection-ordering logic follows the
same in-component pattern `DiagramResizeHandle`/`ColumnResizeHandle`/`connectorSelection.ts`
already use), so every user story is validated live against `quickstart.md`
(`claude-in-chrome`), matching `005`'s/`007`'s precedent.

**Organization**: No Setup or Foundational phase — no new tooling/dependencies (plan.md) and
no shared infrastructure needs building before any story starts; `ArchitectureDiagramPanel`
is already a reusable, prop-driven component. Stories are sequenced in spec.md's priority
order (US1 → US2 → US3). US1 and US2 both edit `ArchitectureDiagramPanel.tsx` (US1 adds the
pop-out trigger; US2 removes the old `AddConnectorDialog`) — doing US1 first means US2's
removal happens after the pop-out trigger already replaces that button's screen position, so
this order avoids rework. US3 (font size) touches the broadest set of lines in the same file
and is sequenced last to minimize merge friction with US1/US2's structural edits.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1`-`US3`, matching `spec.md`
- File paths are relative to the repository root and follow `plan.md`'s Project Structure

## Phase 1: User Story 1 - Pop out the architecture canvas into its own view (Priority: P1) 🎯 MVP

**Goal**: A pop-out control on column 4's canvas opens an enlarged, resizable, in-tab overlay
containing a second, independent, live-synced canvas.

**Independent Test**: Open the pop-out from column 4, add a Service/Connector via columns 2/3,
confirm the change appears in the pop-out without a manual refresh, then close the pop-out and
confirm column 4's own canvas is still fully usable.

### Implementation for User Story 1

- [X] T001 [US1] Add an `onOpenPopout: () => void` prop and a `[↗]`-style icon `Button` in a
      `<Panel position="top-right">` (the same position the removed `AddConnectorDialog`
      currently occupies) to `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`
      (FR-007)
- [X] T002 [US1] Add `popoutOpen`/`setPopoutOpen` boolean state to
      `frontend/src/pages/WorkspacePage.tsx`; wire `onOpenPopout={() => setPopoutOpen(true)}`
      into the existing column-4 `<ArchitectureDiagramPanel>` instance (FR-007)
- [X] T003 [US1] Create `frontend/src/components/workspace/PopoutCanvasDialog.tsx`: accepts
      `open`, `onOpenChange`, and the same `architectureId`/`collections`/`connectors`/
      `onCreateConnector`/`onUpdateCollectionParent`/`onRejectedNesting`/`onRefresh` props
      `WorkspacePage.tsx` already threads to column 4's `ArchitectureDiagramPanel`; wraps its
      own `<ReactFlowProvider>` and owns its own local `diagramSelection`/`selectedNodeIds`/
      `ownHeights` state (mirroring the shape `WorkspacePage.tsx` owns for column 4), rendering
      a second, independent `<ArchitectureDiagramPanel>` instance inside a `Dialog`/
      `DialogContent` from `frontend/src/components/ui/dialog.tsx` (FR-008, FR-011,
      research.md §3)
- [X] T004 [US1] In `PopoutCanvasDialog.tsx`, pass `modal={false}` to the `Dialog` root and
      remove (or render `pointer-events-none`, confined to the dialog's own bounds) the default
      `DialogOverlay`, so column 4's own canvas stays clickable/interactive while the pop-out is
      open (FR-011 — `/speckit-analyze` finding F1: a default *modal* Dialog's focus trap and
      full-viewport overlay would otherwise block column 4 entirely, contradicting FR-011).
      Give `DialogContent` a large default size (e.g. `max-w-[90vw] max-h-[85vh]` in place of
      the default `sm:max-w-lg`) plus inline `style={{ width, height }}` backed by component
      state, and add a corner resize grip using the same
      `onPointerDown`/`setPointerCapture`/`pointermove` pattern as `DiagramResizeHandle`
      (`ArchitectureDiagramPanel.tsx`) / `ColumnResizeHandle` (`WorkspacePage.tsx`), extended to
      both width and height (FR-008, research.md §4) — depends on T003
- [X] T005 [US1] Render `<PopoutCanvasDialog open={popoutOpen} onOpenChange={setPopoutOpen} ...>`
      from `frontend/src/pages/WorkspacePage.tsx` alongside the existing column-4
      `ArchitectureDiagramPanel`, passing through the same `collections`/`connectors`/mutation
      props (FR-009, FR-010) — depends on T001-T004
- [X] T006 [US1] Live-verify via `claude-in-chrome` against `quickstart.md`'s US1 section:
      open/resize the pop-out, confirm columns 2/3 edits propagate into it live, **explicitly
      click/select something on column 4's own canvas while the pop-out is open and confirm it
      responds** (not just that it's still rendering/updating — FR-011, finding F1), and confirm
      closing it (button, Escape, or outside-click) returns column 4 to being active with no
      page reload (FR-007–FR-011, SC-004, SC-005) — depends on T001-T005

**Checkpoint**: The pop-out is fully functional and independently testable; column 4's own
canvas behavior is unchanged when the pop-out is closed.

---

## Phase 2: User Story 2 - One consistent way to create a Connector (Priority: P2)

**Goal**: Column 2's "Connect" button becomes the sole connector-creation entry point, opening
the same dialog the old canvas button used, pre-populated from the current canvas selection.

**Independent Test**: With zero, one, and two Collections selected on the canvas in turn, click
"Connect" in column 2 each time and confirm the dialog's From/To dropdowns are pre-populated
accordingly and that no Connector is created until the user explicitly confirms.

### Implementation for User Story 2

- [X] T007 [US2] Remove the `AddConnectorDialog` function and its
      `<Panel position="top-right"><AddConnectorDialog .../></Panel>` usage from
      `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` (FR-002) — do this after
      T001 so the pop-out trigger already occupies that screen position before this is removed
- [X] T008 [US2] Add `collections: Collection[]`, `selectedNodeIds: string[]`, and
      `onCreateConnector: (from: string, to: string) => void` props to
      `CollectionsPanelProps` in `frontend/src/components/workspace/CollectionsPanel.tsx`,
      replacing `canConnect`/`onConnect`
- [X] T009 [US2] In `CollectionsPanel.tsx`, move the dialog markup (From/To `Select` dropdowns,
      the same-Collection guard, the confirm button) from the removed `AddConnectorDialog`
      (T007) into a local dialog rendered from the "Connect" button, which is now always
      enabled (no `disabled` prop) and opens the dialog instead of connecting immediately
      (FR-003, FR-004, FR-006) — depends on T007, T008
- [X] T010 [US2] Seed the dialog's local `from`/`to` state from `selectedNodeIds` when it opens:
      `selectedNodeIds[0]` → `from`, `selectedNodeIds[1]` → `to` if present, both left empty if
      `selectedNodeIds` has zero or more than two entries (FR-005) — depends on T009
- [X] T011 [US2] In `frontend/src/pages/WorkspacePage.tsx`, remove `handleConnect` and pass
      `collections={collections}`, `selectedNodeIds={selectedNodeIds}`, and
      `onCreateConnector={(from, to) => createConnector.mutate({ from, to })}` into
      `<CollectionsPanel>` in place of the removed `canConnect`/`onConnect` props — depends on
      T008
- [X] T012 [US2] Delete the now-dead `canConnect` function from
      `frontend/src/pages/connectorSelection.ts` and its `describe("canConnect", ...)` test
      block from `frontend/tests/unit/connectorSelection.test.ts` (`updateOrderedSelection` and
      its own tests stay — still used by `ArchitectureDiagramPanel.tsx`'s selection handler,
      unrelated to this feature) — its only callers were the `canConnect`/`onConnect` props T008
      removed and the `handleConnect` T011 removed, confirmed via grep to have no other
      references (`/speckit-analyze` finding M1) — depends on T008, T011
- [X] T013 [US2] Live-verify via `claude-in-chrome` against `quickstart.md`'s US2 section: zero/
      one/two-selection pre-population, no-connector-until-confirm, and that the "Connect"
      button is always clickable (FR-002–FR-006, SC-002, SC-003) — depends on T007-T012

**Checkpoint**: Connector creation works only through column 2's "Connect" button; the canvas no
longer has its own connector-creation control.

---

## Phase 3: User Story 3 - More legible canvas text (Priority: P3)

**Goal**: Canvas text (Collection/Connector/region labels) is one step larger, without changing
the diagram's default zoom.

**Independent Test**: Open any architecture with Collections/Connectors and confirm the canvas
text is larger than the current default while the zoom level is unchanged.

### Implementation for User Story 3

- [X] T014 [P] [US3] In `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`,
      replace every `text-3xs` usage with `text-2xs` for: `ServiceList`'s "No services yet."
      text and its `<ul>`, both node types' `<strong>{label}</strong>`, both region-label
      `<span>`s, and the connector `labelStyle.fontSize` (`var(--text-3xs)` →
      `var(--text-2xs)`) — leave the bottom-left zoom-% `<Panel>` at `text-4xs` (UI chrome, not
      diagram content) (FR-001, research.md §1)
- [X] T015 [US3] Live-verify via `claude-in-chrome` against `quickstart.md`'s US3 section:
      confirm larger, non-overflowing/non-clipped text at the diagram's default zoom (FR-001,
      SC-001) — depends on T014

**Checkpoint**: All three user stories are independently functional.

---

## Dependencies & Execution Order

### Phase Dependencies

- **User Story 1 (P1)**: No dependency on US2/US3 — can start immediately.
- **User Story 2 (P2)**: No functional dependency on US1, but T007 (removing the old canvas
  button) is sequenced after T001 (adding the pop-out trigger to the same screen position) to
  avoid one task's diff fighting the other's in the same file/region.
- **User Story 3 (P3)**: No functional dependency on US1/US2; sequenced last only to reduce
  merge friction, since it touches the broadest set of lines in a file US1/US2 also edit.

### Within Each User Story

- Implementation tasks before the story's live-verification task.
- Story complete (including live verification) before moving to the next priority, per this
  feature's sequencing rationale above — though a team could work US1/US2/US3 in parallel on
  separate branches if preferred, since none is a hard prerequisite for another.

### Parallel Opportunities

- T014 (US3, `ArchitectureDiagramPanel.tsx` text sizes) is marked `[P]` only in the sense that
  it doesn't depend on any *incomplete* task within its own story (there's only one
  implementation task). In practice, doing it after US1/US2 have already landed in the same
  file (per the sequencing rationale above) avoids merge conflicts, even though nothing
  functionally requires that order.
- US1 and US2's implementation tasks (T001-T006 vs. T007-T013) touch almost entirely different
  files (`PopoutCanvasDialog.tsx` is new; `CollectionsPanel.tsx` is untouched by US1) except for
  `ArchitectureDiagramPanel.tsx` (T001 adds to it, T007 removes from it) and
  `WorkspacePage.tsx` (T002/T005 vs. T011) — two developers could work both stories in parallel
  if T001 lands (or is at least agreed on) before T007 starts.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (US1: T001-T006).
2. **STOP and VALIDATE**: Run `quickstart.md`'s US1 section independently.
3. Deploy/demo if ready — the pop-out is useful on its own even before US2/US3 land.

### Incremental Delivery

1. Add User Story 1 → validate independently → demo (MVP).
2. Add User Story 2 → validate independently → demo.
3. Add User Story 3 → validate independently → demo.
4. Each story adds value without breaking the previous ones.

## Notes

- No `[P]` markers across different stories are used here beyond T014, since US1's and US2's
  own task lists are each mostly sequential within themselves (later tasks build on props/
  components earlier tasks introduce in the same story).
- Commit after each story's checkpoint, not after every individual task, per this repository's
  established Spec Kit convention (conventional-commit style, one commit summarizing the
  changes since the last commit).
- Verify `npm run check-api-types` is unaffected (it should be — no backend/API changes in this
  feature) as a final regression check once all three stories are done.

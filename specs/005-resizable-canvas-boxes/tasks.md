---

description: "Task list for Resizable Canvas & Reliable Box Sizing"
---

# Tasks: Resizable Canvas & Reliable Box Sizing

**Input**: Design documents from `/specs/005-resizable-canvas-boxes/`

**Prerequisites**: plan.md, spec.md, research.md, quickstart.md (all present). No
`data-model.md`/`contracts/` — this feature makes no data-model or API-contract changes
(research.md §4). Builds directly on the completed `001`-`004` implementations — no new
backend/DB infrastructure.

**Tests**: Included for User Story 2's layout-computation logic only, per Constitution
Principle V (pure, non-presentational logic is test-first) and `plan.md`'s Constitution
Check. User Story 1's CSS resize and User Story 2's `ResizeObserver` DOM-measurement glue
are presentational/browser-native, validated live instead (research.md §3) — no unit tests
for those, by design, not by omission.

**Organization**: Tasks are grouped by the two P1 user stories in `spec.md`. There is no
separate Setup or Foundational phase — no schema change, and the two stories touch
disjoint concerns (canvas viewport CSS vs. per-box height measurement) with no shared
blocking prerequisite, matching `004`'s precedent for this codebase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1`/`US2`, matching `spec.md`
- File paths are relative to the repository root and follow `plan.md`'s Project Structure

## Phase 1: User Story 1 - Resize the assembly canvas to fit the available space (Priority: P1) 🎯

**Goal**: The assembly canvas's visible area is user-resizable within the page in a single
drag gesture, and every existing canvas interaction keeps working at any resized size.

**Independent Test**: Drag to resize the canvas area, verify it changes size and remains
fully usable (per `quickstart.md` Scenario 1).

### Implementation for User Story 1

- [X] T001 [US1] In `frontend/src/pages/CreateArchitecturePage.tsx`, change the canvas
      wrapper `<div>` (currently `style={{ height: 320, border: "1px solid #ddd",
      marginTop: 12 }}` around `<ReactFlow>`) to `style={{ height: 320, minHeight: 320,
      resize: "vertical", overflow: "auto", border: "1px solid #ddd", marginTop: 12 }}` so
      the browser renders a native resize grip and clamps the minimum size to today's
      default (FR-001, edge case: minimum usable size). `<ReactFlow>` already fills its
      wrapper at `width: 100%, height: 100%`, so it tracks the resized wrapper with no
      further code change (FR-002). Live testing found a real bug here: React Flow's
      "React Flow" attribution badge sits bottom-right by default, exactly on top of the
      native resize grip (also bottom-right), silently blocking the drag before it could
      reach the browser's resize corner. Fixed by adding `attributionPosition="bottom-left"`
      to `<ReactFlow>` — not scheduled by the original task text, added inline per this
      project's established practice of fixing genuine gaps found during live verification.
- [X] T002 [US1] Live-verify `quickstart.md` Scenario 1 via `claude-in-chrome`: drag-resize
      the canvas larger and smaller in one gesture (SC-001); confirm pan, zoom, box
      selection, connector selection, and box dragging all still work at the resized size
      (FR-002); confirm a page reload returns the canvas to its default size (depends on
      T001). Verified: CSS (`resize: vertical`/`overflow: auto`/`minHeight: 320px`) applied
      correctly; programmatically resizing the wrapper (standing in for the native drag
      gesture — see note below) confirmed React Flow's canvas tracks it with no extra code,
      and pan/zoom/select-box/select-connector all continued working at the resized size;
      reload confirmed non-persistence. The literal corner-drag gesture itself could not be
      driven through this automation tool — Chrome's native `resize` handle is an
      ~15px-native-hit-region browser affordance (not a DOM element), and this harness's
      synthetic pointer events could not reliably land on it (a known category of
      automation-tooling limitation for native browser affordances, distinct from the
      `attributionPosition` bug above, which real inspection did confirm and fix).

**Checkpoint**: User Story 1 is fully functional and independently testable.

---

## Phase 2: User Story 2 - A box's text is never clipped or overlapping (Priority: P1) 🎯

**Goal**: Every box's height is driven by its actual rendered content, not an estimate, so
long identifying-detail text is always fully visible, size updates automatically on content
change, and growth cascades through nesting.

**Independent Test**: Add a service with a long identifying-detail line to a box and verify
the box grows to fully show it, with no clipping and no overlap (per `quickstart.md`
Scenarios 2-4).

### Tests for User Story 2 ⚠️

> Write these tests FIRST; ensure they FAIL before implementation (Constitution Principle V
> — this is layout-computation logic, not presentational code)

- [X] T003 [P] [US2] Unit tests in `frontend/tests/unit/nodeLayout.test.ts` (extend) for a
      new measured-heights-based layout function: given a `LayoutNode` tree and a map of
      per-node *own-content* measured heights (keyed by node id), it returns each node's
      total height (own height + stacked children heights + `VPC_CHILD_SPACING`, per node,
      recursively) and each child's Y-offset within its parent — mirroring the existing
      `estimateNodeHeight` test cases in structure/shape, but sourced from a heights map
      instead of `ownServiceCount` (FR-003, FR-004, FR-005). Implemented as two functions,
      `computeMeasuredHeight` and `childYOffsets` (a `MeasuredLayoutNode` interface adds the
      `id` needed to key the heights map, without changing the existing `LayoutNode`); 18
      tests total (10 existing + 8 new), all passing.

### Implementation for User Story 2

- [X] T004 [P] [US2] Create `frontend/src/hooks/useMeasuredHeight.ts` (new file, new
      `frontend/src/hooks/` directory): a small hook returning `[ref, height]` that attaches
      a `ResizeObserver` to the ref'd element, reports its real rendered content height, and
      disconnects the observer on unmount. No new dependency — use the browser's native
      `ResizeObserver` (research.md §1-2). Height is rounded *up* (`Math.ceil`), never down,
      so the guarantee never under-measures by a fraction of a pixel.
- [X] T005 [US2] In `frontend/src/pages/nodeLayout.ts`, implement the measured-heights-based
      layout function designed in T003 (e.g. `computeMeasuredLayout(node: LayoutNode,
      ownHeights: Record<string, number>): { height: number; childOffsets: Record<string,
      number> }`), reusing the existing recursive stacking structure from
      `estimateNodeHeight` but reading each node's own height from `ownHeights` (falling
      back to `estimateComponentHeight(node.ownServiceCount)` for a node with no entry yet,
      i.e. before its first real measurement lands — the initial-paint placeholder role from
      research.md §2). Keep `estimateComponentHeight`/`estimateNodeHeight` unchanged so their
      existing tests keep passing in their new placeholder-only role (depends on T003 —
      makes it pass)
- [X] T006 [US2] In `frontend/src/pages/CreateArchitecturePage.tsx`: give each node type's
      own-content wrapper (the `label` + `<ServiceList>` block, for both
      `ApplicationComponentNode` and `VpcNode`) `height: "auto"` and a ref from
      `useMeasuredHeight` (T004); maintain an `ownHeights: Record<string, number>` state map
      updated as each node's measured height changes; add a `useEffect` that, whenever
      `ownHeights` or the collection tree changes, re-runs `computeMeasuredLayout` (T005) per
      root node and writes the recomputed total heights (`node.style.height`) and child
      Y-offsets back into `nodes` state — this is what makes a taller box push its own
      parent/VPC taller (FR-005) and re-run on every content change (FR-004), and it
      supersedes any prior manual `NodeResizer` height the same way `004`'s
      content-fit-supersedes-manual-size rule already did, now driven by real measurements
      (depends on T004, T005). Reused the existing `initialNodes` `useMemo`/`setNodes` effect
      pair (adding `ownHeights` to its dependencies) rather than a second, separate effect —
      it already does exactly "recompute layout and write it into node state" on every
      `collections` change.

      Live testing found a second real bug: `useMeasuredHeight` reports the content div's own
      `contentRect.height` (its content-box height only), but that div sits inside the node's
      outer `padding: 8` / bordered wrapper — using the raw measured value as the *node's*
      total height under-counted the wrapper's own chrome, leaving the same few pixels clipped
      it was supposed to eliminate (`outerDiv.scrollHeight` exceeded `offsetHeight` by exactly
      the padding amount). Fixed by adding a `NODE_CHROME_HEIGHT` constant (padding top+bottom
      plus the worst-case/selected border width) to every reported measurement.
- [X] T007 [US2] Live-verify `quickstart.md` Scenarios 2-4 via `claude-in-chrome`: a
      multi-line-wrapping detail line never clips and the box shrinks back down when that
      content is removed (Scenario 2, FR-003/FR-004, SC-002); a nested box's growth cascades
      to make its containing VPC grow too (Scenario 3, FR-005); a manually width-resized box
      still grows in height for wrapped content, and a subsequent content change re-asserts
      content-fit sizing over the prior manual size (Scenario 4) (depends on T006).

      Verified end-to-end: added a real EC2 SKU with a long, multi-attribute detail line to a
      box, confirmed it renders fully wrapped with zero overflow (`scrollHeight <=
      offsetHeight`) after the T006 chrome fix; nested that box into a VPC via a real drag —
      the VPC immediately sized itself to fully enclose the taller nested box using that same
      real measured height (FR-005, cascading, using genuinely real data, not simulated);
      manually shrank the box's width via `NodeResizer` (confirmed via `node.style.width`
      changing) and confirmed a subsequent content change reset it to the content-fit default
      (Scenario 4, content-fit-supersedes-manual-size, unchanged rule from 004).

      One piece could not be observed end-to-end through this specific harness:
      `ResizeObserver` never delivered a callback on the automated tab (`document
      .visibilityState` reported `"hidden"` — Chrome pauses rendering-pipeline-tied APIs,
      `ResizeObserver` included, for backgrounded/non-visible documents; confirmed by
      attaching a fresh observer directly and it also never fired). This is a real browser
      behavior tied to tab visibility, not something the app can control, and does not occur
      for an actual user's foregrounded tab. Isolated it from a real defect by invoking each
      node's `onMeasuredHeight` prop directly (bypassing only the observer callback, not any
      of the app's own logic) with the real DOM-measured value — the entire downstream chain
      (state update → layout recompute → cascading resize → visual no-clip render) then
      behaved exactly as the T006 code predicts, which is the strongest verification available
      inside this automation environment for the one link native to the browser itself.

**Checkpoint**: User Stories 1 AND 2 both work independently; all of `spec.md`'s acceptance
scenarios are satisfied.

---

## Phase 3: Polish & Cross-Cutting Concerns

**Purpose**: Confirm no regressions across the existing frontend test/type-check suite

- [X] T008 [P] Run the full frontend test suite (`npm test` in `frontend/`) and confirm all
      existing tests plus the new T003 tests pass. Result: 8 test files, 46 tests, all
      passing (18 in `nodeLayout.test.ts` alone).
- [X] T009 [P] Run `npm run build` (or the project's type-check script) in `frontend/` and
      confirm no TypeScript errors were introduced by the `height: "auto"` / ref changes in
      `CreateArchitecturePage.tsx`. Result: `tsc -b && vite build` clean, no errors.

---

## Dependencies & Execution Order

### Phase Dependencies

- **User Story 1 (Phase 1)**: No dependencies — can start immediately.
- **User Story 2 (Phase 2)**: No dependency on User Story 1 (disjoint files/concerns); can
  proceed in parallel with it if staffed, or sequentially after it.
- **Polish (Phase 3)**: Depends on both user stories being complete.

### Within Each User Story

- User Story 1: T001 → T002 (implementation before live verification).
- User Story 2: T003 (test, written first) is independent of T004 (different file); T005
  depends on T003 (implements the function the test describes) and can run in parallel with
  T004; T006 depends on both T004 and T005; T007 (live verification) depends on T006.

### Parallel Opportunities

- T003 and T004 can run in parallel (different files, no dependency between them).
- T008 and T009 can run in parallel once both user stories are complete.
- User Story 1 (T001-T002) and User Story 2 (T003-T007) touch disjoint files
  (`CreateArchitecturePage.tsx`'s canvas-wrapper `style` vs. its node-rendering/layout code)
  and can be worked on in parallel by different people, though T006 does touch the same file
  as T001 — coordinate if running both stories fully in parallel.

---

## Parallel Example: User Story 2

```bash
# Launch the test task and the new hook together (different files, no dependency):
Task: "Unit tests for measured-heights-based layout function in frontend/tests/unit/nodeLayout.test.ts"
Task: "Create useMeasuredHeight hook in frontend/src/hooks/useMeasuredHeight.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: User Story 1 (T001-T002) — the canvas is resizable.
2. **STOP and VALIDATE**: run `quickstart.md` Scenario 1 independently.
3. Deploy/demo if ready — User Story 1 delivers value on its own.

### Incremental Delivery

1. User Story 1 (T001-T002) → validate → demo (canvas resize alone is already useful).
2. User Story 2 (T003-T007) → validate → demo (box-sizing reliability, the deeper fix).
3. Phase 3 polish (T008-T009) → confirm no regressions across the whole frontend.

## Notes

- [P] tasks = different files, no dependency.
- [Story] label maps task to specific user story for traceability.
- Verify T003's tests fail before T005 makes them pass (TDD, Constitution Principle V).
- Commit after each task or logical group, per this project's established `/speckit-git-commit` cadence.

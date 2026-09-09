# Research: Resizable Canvas & Reliable Box Sizing

## 1. Canvas viewport resize (FR-001, FR-002, SC-001)

**Decision**: Use the browser's native CSS `resize: vertical` on the assembly canvas's
wrapper `<div>` (the element that currently has a fixed `height: 320`), with
`overflow: auto` so the resize grip renders. The inner `<ReactFlow>` element already fills
its wrapper (`width: 100%`, `height: 100%`), so it tracks the wrapper's size automatically —
React Flow's own internal `ResizeObserver` (used for `fitView`/viewport handling) already
reacts to container size changes, no extra code needed for FR-002.

**Rationale**: The page layout is a single-column, full-width flow (confirmed by reading
`CreateArchitecturePage.tsx` — the canvas `<div>` and every section around it are `100%`
width, stacked vertically, not a side-by-side split view). That means "resize the canvas"
only meaningfully means *height* — there is no width to gain. A native resize handle gives
a single-drag-gesture resize (SC-001) for free, with the browser handling the drag
interaction, cursor, and clamping — and it inherently does **not** persist across reload
(it's just the element's computed style, reset on next page load), matching the spec's
Assumption. This is the simplest option that satisfies every acceptance scenario
(Principle VI, Simplicity & YAGNI).

**Alternatives considered**:
- A custom draggable resize-handle component (mouse-down/mouse-move JS): rejected — more
  code, more test surface, and the same UX outcome as the native browser feature. Would
  only be justified if the app needed multi-directional or persisted resize, which the spec
  explicitly does not call for.
- A resizable split-pane layout library: rejected — the page has no second pane to trade
  space with (nothing sits beside the canvas), so a split-pane abstraction has no second
  party to negotiate size against; it would be solving a problem this layout doesn't have.

**Minimum size (Edge Case)**: set a `min-height` on the wrapper (matching today's default,
320px) so the browser's native resize can't be dragged below a usable size; React Flow's
`<Controls>` stay visible and operable at any size at or above that floor.

## 2. Reliable, non-clipping box height (FR-003, FR-004, FR-005, SC-002)

**Decision**: Replace the character/line-count height *estimate* (`estimateComponentHeight`
in `nodeLayout.ts`, added in 003/004) with the browser's own *measured* rendered height of
each box's own content block, obtained via a small `ResizeObserver`-backed hook
(`useMeasuredHeight`, new). Each node type's "own content" wrapper (label + `ServiceList`)
gets `height: auto` (no fixed pixel height) and a ref; the hook reports its real rendered
height, including however many lines any given detail line actually wraps to. A
`useEffect` in `CreateArchitecturePage` re-runs the existing recursive stacking algorithm
(child Y-offsets, parent/VPC total height) whenever any node's measured own-content height
changes, and writes the recomputed sizes back into node state — this is what makes growth
cascade through nesting (FR-005) and re-run automatically on any content change (FR-004).

**Rationale**: This directly closes the gap the spec calls out — `004`'s research.md #4
chose an estimate specifically because "measuring actual rendered height adds complexity
proportional to a problem long detail text doesn't yet cause." That tradeoff is exactly
what this feature revisits: FR-003's "always... without any of it being clipped" is an
absolute guarantee that counting characters/services can approximate but never guarantee
(a long unbroken identifier, unusual font metrics, or a wider zoom level are all cases the
old estimate could under-count). Measuring the actual DOM is the only way to guarantee it.

**Why a scoped hook on each node's own-content block, not React Flow's built-in
`node.measured` dimension events**: `@xyflow/react` already runs a `ResizeObserver` per
node and reports `node.measured.{width,height}` (confirmed in `@xyflow/system`'s source).
But in this app's tree, a nested box's children are separate sibling *nodes* positioned by
absolute `x`/`y` (via `parentId`), not DOM descendants of their parent's own box — so a
VPC's aggregate `node.measured.height` would already include its stacked children, which is
the *output* of the stacking algorithm, not an input to it. What the stacking algorithm
needs is each node's *own* content height in isolation (title + its own `ServiceList`,
before any children are stacked beneath it) — exactly what a ref scoped to just that inner
div measures. Using React Flow's own aggregate measurement would create a circular
dependency (parent height depends on stacked children, which is itself computed from parent
height).

**Initial-paint placeholder**: the existing `estimateComponentHeight`/`estimateNodeHeight`
functions are kept, but their role changes — they're no longer the authority on
clipping-avoidance, only a same-frame placeholder used for a node's very first render,
before its first real `ResizeObserver` measurement has landed (avoiding a 0-height flash).
Every node is immediately superseded by its real measured height once the observer fires.
This also means the ~30 existing passing unit tests for those pure functions stay valid —
they're testing a placeholder-estimate role now, not the clipping guarantee.

**Manual width resize (`NodeResizer`, from 004) unaffected**: the spec's Assumptions
explicitly keep box *width* user-resizable and not auto-grown; only height reliability is
in scope. The existing Edge Case rule (unchanged from 004: content-fit sizing supersedes a
prior manual size on the next content change) continues to apply — it's now driven by
measured heights instead of estimated ones, but the rule itself doesn't change.

**Alternatives considered**:
- Constrain `NodeResizer` to width-only handles (removing the ability to manually drag
  height): rejected as unnecessary — the existing "content-fit supersedes manual size on
  next content change" rule already prevents a stale manual height from causing clipping;
  restricting the resize handles is extra UI code the spec doesn't call for.
- A CSS-only fix (e.g., `white-space: normal` / `overflow-wrap` tuning without any
  measurement): rejected — this app's boxes need their *height* to grow with wrapped
  content and to push sibling/parent layout, which CSS alone cannot do across React Flow's
  absolutely-positioned sibling nodes; JS-driven re-layout from a real measurement is
  required.

## 3. Testing approach

**Decision**: Keep the recursive stacking/cascading math (Y-offsets, parent/VPC total
height from a map of child heights) as pure, unit-testable functions in `nodeLayout.ts`
(extending the existing `estimateNodeHeight`/`LayoutNode` test pattern in
`nodeLayout.test.ts`), now parameterized by a measured-heights map rather than a service
count. The `useMeasuredHeight` `ResizeObserver` hook itself, and the actual no-clipping
behavior for real wrapped text, are validated live in-browser (`claude-in-chrome`), not via
a jsdom `ResizeObserver` polyfill/mock — a mocked observer can assert the hook *wires up*
correctly but can't prove real text never clips, which is the entire point of this feature;
a real browser is the only environment that can prove that.

**Rationale**: Consistent with Constitution Principle V, which explicitly allows
tests-after for presentational code where a test-first cycle adds no verification value —
the DOM-measurement glue and the CSS `resize` handle both fall in that category. The
layout-computation logic (which *isn't* presentational) keeps the test-first pure-function
discipline already established in this codebase.

## 4. No backend, data-model, or API-contract changes

**Decision**: This feature is entirely frontend/client-side (canvas layout only). No
Postgres schema, DuckDB query, or FastAPI route/schema is touched, so no `data-model.md` or
`contracts/` are produced for this feature — there is nothing for them to document. The
`check-api-types` drift gate (Principle IV) is unaffected since the OpenAPI contract itself
doesn't change.

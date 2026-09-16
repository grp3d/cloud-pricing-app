# Research: Canvas Connector & Pop-Out Improvements

## §1. Canvas text size (US3/FR-001)

**Decision**: Bump the architecture canvas's text one more step up the app's existing custom
scale: `--text-3xs` (10px, the size currently in place after this session's earlier live edit)
→ `--text-2xs` (11px), applied everywhere `ArchitectureDiagramPanel.tsx` currently uses
`text-3xs` (node labels, region labels, the empty-service-list message, the connector edge
label's `fontSize`).

**Rationale**: `frontend/src/index.css` already defines a four-step scale below `text-xs`
(12px): `text-2xs` (11px) → `text-3xs` (10px) → `text-4xs` (9px). The canvas is currently one
step below `text-xs` at `text-3xs`; "one more increase" (spec Assumptions) is the next step up,
`text-2xs`, with no new CSS variable needed. The bottom-left zoom-% `Panel` stays at `text-4xs`
(UI chrome, not diagram content, per this session's prior decision) — unaffected.

**Alternatives considered**: Introducing a new intermediate size between `text-3xs` and
`text-xs` — rejected as unnecessary; the existing scale already has a well-defined next step.

## §2. Consolidated Connect entry point (US2/FR-002–FR-006)

**Decision**: Delete the `AddConnectorDialog` component and its `<Panel position="top-right">`
usage from `ArchitectureDiagramPanel.tsx` (FR-002). Move its dialog markup (From/To `Select`
dropdowns, the same-Collection guard, the confirm button) to `CollectionsPanel.tsx` (column 2),
opened by the existing "Connect" button instead of `WorkspacePage.tsx`'s `handleConnect`
directly creating a Connector. The dialog's own local `from`/`to` state is now *seeded* from
`selectedNodeIds` (already threaded into `CollectionsPanel` as `canConnect`'s basis) when it
opens: `selectedNodeIds[0]` → `from`, `selectedNodeIds[1]` → `to` (if present), matching
FR-005's selection-order pre-population and the ordering `connectorSelection.ts`'s
`updateOrderedSelection` already guarantees. The "Connect" button's `disabled={!canConnect}`
gate (which required exactly two selected Collections) is removed per FR-004 — the button is
always enabled, exactly like the removed canvas button was.

**Rationale**: `onCreateConnector` (`(from: string, to: string) => void`, wired to
`createConnector.mutate`) is already the single shared entry point both the old canvas button
and the old direct-connect path used — no backend or mutation change, only which UI triggers it
and how its inputs are gathered (spec Assumptions: presentation-layer only). Reusing the
dialog's existing markup/validation verbatim (rather than writing a new one) keeps this
Principle VI-simple: one dialog implementation, relocated, not two.

**Alternatives considered**: Keeping both the canvas button and column 2's immediate-connect
button and only changing one — rejected, contradicts FR-002/SC-003 (exactly one entry point).
Pre-populating from `diagramSelection` (the single-item "what's shown in column 2/3" selection)
instead of `selectedNodeIds` (the multi-select array) — rejected, `diagramSelection` cannot
represent two simultaneously-selected Collections the way `selectedNodeIds` already does.

## §3. Live-synced, independently-interactive pop-out (US1/FR-007–FR-011)

**Decision**: The pop-out renders a **second, independent instance** of
`ArchitectureDiagramPanel`, each wrapped in its own `<ReactFlowProvider>`. A new small
component (`PopoutCanvasDialog`, rendered from `WorkspacePage.tsx` next to the existing column 4
panel) owns:
- its own `<ReactFlowProvider>` (required — see Rationale),
- its own local selection state (`diagramSelection`, `selectedNodeIds`, and the
  `onSelectCollection`/`onSelectConnector`/`onSelectService`/`onDeselectAll`/
  `onSelectedNodeIdsChange` callbacks that update it), separate from `WorkspacePage`'s own,
- its own local `ownHeights`/`reportHeight` box-height map (each instance measures its own
  layout independently),
- open/closed state and pixel width/height for the resize handle (§4).

`collections`/`connectors` (the actual architecture data) and the mutation callbacks
(`onCreateConnector`, `onUpdateCollectionParent`, `onRejectedNesting`, `onRefresh`,
`architectureId`) are passed straight through from `WorkspacePage`'s existing state/mutations —
the same TanStack Query cache both instances read from, so any edit from columns 2/3 (which
already calls `invalidateArchitecture()`) re-renders both instances automatically. This is
FR-009 with no new sync mechanism: it already works today for column 4 and needs no new code
for a second instance subscribed to the same query.

**Rationale**: `ArchitectureDiagramPanel` calls `useReactFlow()`/`useOnSelectionChange()`
(`@xyflow/react`), which require a `ReactFlowProvider` ancestor and share **one** internal
store per provider — two `<ReactFlow>` instances under the *same* provider would fight over one
shared internal state, not behave independently. A second, separate provider is therefore not
an implementation nicety but the only way to satisfy FR-011 ("remains... independently usable")
while both canvases are mounted at once. Because `diagramSelection`/selection callbacks are
already props `WorkspacePage` threads in (not internal to `ArchitectureDiagramPanel`), giving
the pop-out its own local copies of exactly those props is a small, additive change — no
existing column 4 behavior changes.

Per the resolved clarification, selecting/connecting inside the pop-out does not drive columns
2/3 (only column 4's own selection does, unchanged from today) — the pop-out is an additional,
independently-usable view, not a replacement selection source. A user who wants the
Connect-dialog pre-population (§2) from a pop-out-made selection still makes that selection on
column 4's own canvas, as today.

**Alternatives considered**: Sharing one `ReactFlowProvider`/selection state between column 4
and the pop-out — rejected, technically fights React Flow's one-store-per-provider model and
contradicts the resolved "independently interactive" requirement. Making the pop-out
read-only (no `ReactFlowProvider`, no interaction) — rejected by the resolved clarification.

## §4. Pop-out presentation & resize (US1/FR-008, Clarifications)

**Decision**: Build the pop-out on the existing shadcn/ui `Dialog`/`DialogContent` primitives
(`components/ui/dialog.tsx`), the same base `AddConnectorDialog` already used, but with
`modal={false}` passed to the `Dialog` root and **no full-viewport dimming `DialogOverlay`**
(either omit it entirely or render it `pointer-events-none` and confined to the dialog's own
bounds) — see Amendment below for why. Otherwise as originally planned: a large-by-default
`className` override (e.g. `max-w-[90vw] max-h-[85vh]` in place of the default `sm:max-w-lg`)
and inline `style={{ width, height }}` driven by component state. Resizing reuses this
codebase's own proven pointer-based drag-handle pattern — `onPointerDown` +
`setPointerCapture` + a `pointermove` listener updating that width/height state — the same
approach `DiagramResizeHandle` (`ArchitectureDiagramPanel.tsx`) and `ColumnResizeHandle`
(`WorkspacePage.tsx`) already use for the diagram's height and the column widths, extended to
both dimensions for the pop-out's own corner grip.

**Amendment (`/speckit-analyze` finding F1)**: The original version of this decision reused
Radix `Dialog`'s *default* modal behavior — focus trapping plus a full-viewport, pointer-blocking
overlay. That directly contradicts FR-011 (confirmed via the resolved clarification): column 4's
own canvas must stay "fully usable on its own... rather than becoming a disabled or placeholder
view" while the pop-out is open. A modal dialog's backdrop, by construction, blocks pointer
interaction with whatever's behind it — no amount of local state design makes column 4
"independently interactive" if a full-screen overlay is intercepting every click aimed at it.
`modal={false}` disables Radix's focus trap and its `aria-hidden`/body-scroll-lock side effects
on the rest of the page; removing (or de-blocking) `DialogOverlay` is the separate, necessary
second half of the fix, since the overlay's pointer-blocking comes from it being a real,
full-viewport DOM element sitting on top in stacking order, unrelated to the `modal` prop. With
both changes, the pop-out becomes a large floating panel over the canvas area rather than a
classic modal dialog — visually and functionally consistent with "two independent, live views"
(the framing already used when this pop-out mechanism was decided) rather than one view blocking
the other.

Escape-to-close and outside-click-to-close (Edge Cases) still work with `modal={false}` — Radix's
dismiss-on-`Escape`/`onPointerDownOutside` behavior is handled by its `DismissableLayer`
independent of the `modal` prop, so no custom handling is needed for those.

**Rationale**: Per the resolved Clarification, the pop-out is an in-tab overlay, not a separate
browser window, but "in-tab" was never meant to imply "blocks the rest of the tab" — the
resolved FR-011 already says the opposite. Native CSS `resize` was already tried and rejected
earlier in this codebase for the diagram panel's own resize grip (documented in
`ArchitectureDiagramPanel.tsx`'s `DiagramResizeHandle` comment: an imprecise hit-region let
drags fall through to the canvas's own pan handling, and the browser's own DOM mutation wasn't
kept across re-renders) — the pointer-based, state-backed approach is the already-proven fix for
exactly this failure mode, so this reuses it rather than re-discovering the same bug.

**Alternatives considered**: A dedicated resizable-dialog library — rejected per Constitution
Principle VI (no new dependency for something this codebase has already solved once). Keeping
the default modal `Dialog` (the original version of this decision) — rejected per finding F1:
directly contradicts FR-011.

## §5. Testing approach

**Decision**: `connectorSelection.ts`'s pre-population-ordering logic (§2) gets a unit test
(Vitest) if any new pure helper is extracted for it, following this codebase's existing
precedent for that file; the resize-handle math (if extracted as a pure function) likewise. All
three user stories are otherwise UI/interaction work validated live via `claude-in-chrome`
against `quickstart.md`, per Constitution Principle V's explicit presentational-code carve-out
(matching `005`'s and `007`'s precedent) — no pricing calculation, DuckDB, or Postgres logic is
touched.

**Alternatives considered**: Full component/integration test coverage for the pop-out's
dual-instance rendering — deferred; Principle V doesn't require it for presentational code, and
this codebase's established pattern for canvas/diagram work is live verification, not
component-test scaffolding (`ArchitectureDiagramPanel.tsx` itself has none).

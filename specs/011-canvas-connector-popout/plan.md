# Implementation Plan: Canvas Connector & Pop-Out Improvements

**Branch**: `011-canvas-connector-popout` | **Date**: 2026-09-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-canvas-connector-popout/spec.md`

## Summary

Three independent, presentation-layer-only changes to the architecture workspace: (1) bump
column 4's canvas text one more step up the existing size scale; (2) remove the canvas's own
"Add Connector" button and relocate its dialog to column 2's "Connect" button, which now always
opens it (pre-populated from whatever's currently selected on the canvas) instead of connecting
immediately; (3) add a pop-out control that opens an enlarged, resizable, in-tab overlay
containing a second, fully independent, live-synced instance of the same canvas — both
instances read the same architecture data, so edits from columns 2/3 appear in both
automatically, and each stays separately interactive. See `research.md` for the full technical
approach and rationale for each.

## Technical Context

**Language/Version**: TypeScript ~5.6, React 18.3, Vite 5.4 (unchanged) — this feature touches
`frontend/` only; `backend/` is untouched (spec Assumptions).

**Primary Dependencies**: No new dependencies. Reuses `@xyflow/react` (React Flow, a second
`ReactFlowProvider`/`ArchitectureDiagramPanel` instance — research.md §3), the existing
shadcn/ui `Dialog` primitives (research.md §4), and this codebase's own pointer-based
drag-resize pattern (`DiagramResizeHandle`/`ColumnResizeHandle` — research.md §4).

**Storage**: N/A — no Postgres/DuckDB/API change; reuses the existing Collections/Connectors
data and `createConnector` mutation as-is.

**Testing**: Vitest + Testing Library for any newly-extracted pure logic (connect-dialog
pre-population ordering, resize-handle math, if extracted — research.md §5); `claude-in-chrome`
live verification against `quickstart.md` as the primary validation method, per Constitution
Principle V's presentational-code allowance (matching `005`'s and `007`'s precedent). Existing
unit-tested domain components (`connectorSelection.ts`, etc.) keep their current tests passing
unchanged.

**Target Platform**: Existing web SPA, desktop-width browsers (matching `007`'s established
scope — no dedicated narrow-screen layout).

**Project Type**: Web application (existing `backend/` + `frontend/` split) — this feature is
scoped to `frontend/` only.

**Performance Goals**: No new numeric target; the pop-out's second canvas instance renders
client-side from data already in the TanStack Query cache — no new network calls.

**Constraints**: No backend/API changes (`check-api-types` must stay clean); every existing
canvas interaction (pan, zoom, select, drag, nesting, per-box resize) must keep working
unchanged in both the column 4 canvas and the pop-out's canvas.

**Scale/Scope**: Unchanged — same Architectures/Collections/Connectors/services scale as today;
this is a presentation-layer restructure plus one new UI surface (the pop-out), not a data-scale
change.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applicability | Assessment |
|---|---|---|
| I. Pricing Data Integrity | N/A | No pricing values are read, computed, or displayed differently. |
| II. Clear Data-Layer Separation | N/A | No Postgres/DuckDB access changes. |
| III. Provider-Extensibility by Design | N/A | No provider-specific assumptions introduced or touched. |
| IV. Type-Safe Frontend/Backend Contract | N/A | No API request/response shape changes — nothing for `check-api-types` to drift on. |
| V. Test-First Development | Applies, with its own explicit carve-out used | This is layout/presentational/interaction work, not pricing or data-relationship logic — Principle V permits tests-after here, validated live per research.md §5 (matching `005`'s/`007`'s precedent). Any pure logic that does get extracted (connect pre-population ordering, resize math) still gets test-first unit tests. |
| VI. Simplicity & YAGNI | Central | Drives research.md's decisions throughout: reusing the existing dialog/resize/selection patterns verbatim rather than inventing new ones, no new dependency for the resizable overlay, and the pop-out's data-sync relying entirely on the TanStack Query cache already shared today rather than any new sync mechanism. |

**Gate result**: PASS. No violations; Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/011-canvas-connector-popout/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

No `data-model.md` or `contracts/` — no data-model or API-contract changes (spec Assumptions;
matching `007`'s precedent for a purely presentation-layer feature).

### Source Code (repository root)

```text
backend/                                     # UNCHANGED by this feature

frontend/
├── src/
│   ├── pages/
│   │   ├── WorkspacePage.tsx                  # MODIFIED — handleConnect removed (connector
│   │   │                                         creation moves into CollectionsPanel's dialog);
│   │   │                                         renders PopoutCanvasDialog alongside column 4
│   │   └── connectorSelection.ts              # UNCHANGED — pre-population reuses its existing
│   │                                             selection-order guarantee
│   ├── components/
│   │   ├── workspace/
│   │   │   ├── ArchitectureDiagramPanel.tsx   # MODIFIED — AddConnectorDialog/its Panel removed;
│   │   │   │                                    text-3xs → text-2xs (US3); still the component
│   │   │   │                                    both column 4 and the pop-out instantiate
│   │   │   ├── CollectionsPanel.tsx           # MODIFIED — "Connect" button now opens the
│   │   │   │                                    relocated Add-Connector dialog instead of
│   │   │   │                                    connecting immediately; always enabled
│   │   │   └── PopoutCanvasDialog.tsx         # NEW — owns its own ReactFlowProvider, local
│   │   │                                        selection state, and resize state; renders a
│   │   │                                        second ArchitectureDiagramPanel instance inside
│   │   │                                        an enlarged Dialog (research.md §3-4)
│   │   └── ui/                                # UNCHANGED — Dialog primitives reused as-is
│   └── index.css                               # UNCHANGED — --text-2xs already exists
└── tests/
    └── unit/                                  # existing suites unchanged; new suite(s) only for
                                                  any extracted pure logic (research.md §5)
```

**Structure Decision**: Web application structure (established `001`-`010`) is unchanged. This
feature is scoped entirely to `frontend/src/components/workspace/` and `WorkspacePage.tsx`. It
introduces one new component (`PopoutCanvasDialog.tsx`) and moves the connector-creation dialog
from `ArchitectureDiagramPanel.tsx` into `CollectionsPanel.tsx`; every other existing component
keeps its current props/behavior contract.

## Complexity Tracking

*No violations — table not needed.*

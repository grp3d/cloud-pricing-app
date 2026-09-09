# Implementation Plan: Resizable Canvas & Reliable Box Sizing

**Branch**: `005-resizable-canvas-boxes` | **Date**: 2026-09-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-resizable-canvas-boxes/spec.md`

## Summary

Two client-side canvas fixes reported together: (1) the assembly canvas viewport has a
fixed height and gets cramped as an Architecture grows — fixed via the browser's native
`resize: vertical` on the canvas wrapper, a single-drag-gesture, non-persisted resize that
needs no new code beyond the CSS itself. (2) A box's height is currently only an *estimate*
based on counting services/characters (from `003`/`004`), which can under-count how many
lines long identifying-detail text actually wraps to and clip it — fixed by measuring each
box's own-content block's real rendered height via a small `ResizeObserver` hook, and
re-running the existing recursive stacking/cascading algorithm from those real measurements
instead of the estimate (the estimate is kept only as a same-frame initial-paint
placeholder). See `research.md` for the full rationale and rejected alternatives.

## Technical Context

**Language/Version**: TypeScript ~5.6 (React 18.3), Vite 5.4 — frontend only; this feature
makes no backend changes.

**Primary Dependencies**: React, `@xyflow/react` ^12.3.5 (both already in use); the
browser's native `ResizeObserver` API and native CSS `resize` property — no new dependency
is added (Principle VI, Simplicity & YAGNI).

**Storage**: N/A — no Postgres schema, DuckDB query, or data-model change; this feature is
pure client-side canvas layout.

**Testing**: Vitest for the pure layout-computation functions in `nodeLayout.ts` (extending
the existing `nodeLayout.test.ts` pattern); live browser verification via `claude-in-chrome`
for the actual DOM-measurement/no-clipping behavior and the native canvas resize, per
`research.md` §3.

**Target Platform**: Web browser (existing React SPA).

**Project Type**: Web application (existing `backend/` + `frontend/` split) — this feature
touches `frontend/` only.

**Performance Goals**: Re-layout on a content or resize change must feel instant on a
typical Architecture (tens of boxes) — no numeric throughput target; this is a UI
responsiveness expectation, not a domain-specific performance requirement.

**Constraints**: No new frontend dependency; must not touch the API surface (the
OpenAPI-generated `schema.d.ts` and `check-api-types` gate are unaffected); the canvas's
resized size and each box's *width* remain non-persisted/user-driven exactly as before —
only box *height* reliability is in scope (spec Assumptions).

**Scale/Scope**: Unchanged — same expected number of Collections/boxes per Architecture as
today.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applicability | Assessment |
|---|---|---|
| I. Pricing Data Integrity | N/A | No pricing values are read, computed, or displayed differently by this feature. |
| II. Clear Data-Layer Separation | N/A | No Postgres or DuckDB access changes. |
| III. Provider-Extensibility by Design | N/A | No provider-specific (AWS) logic touched — pure canvas layout. |
| IV. Type-Safe Frontend/Backend Contract | N/A | No API route/schema change; nothing for `check-api-types` to drift on. |
| V. Test-First Development | Partial | The pure stacking/cascading layout math is logic (not presentational) and gets test-first unit tests, extending `nodeLayout.test.ts`. The `ResizeObserver` DOM-measurement glue and the native CSS resize are presentational/browser-native — Principle V explicitly allows tests-after here, validated live instead (research.md §3), consistent with how 003/004 treated similar layout code. |
| VI. Simplicity & YAGNI | Applies | Both fixes deliberately favor the simplest option: native CSS `resize` over a custom drag-handle component; a scoped `ResizeObserver` hook over a new layout library; no new dependency added. See research.md §1–2 for rejected, more-complex alternatives. |

**Gate result**: PASS. No violations; Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/005-resizable-canvas-boxes/
├── plan.md              # This file (/speckit-plan command output)
├── research.md           # Phase 0 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

No `data-model.md` or `contracts/` are produced for this feature — it makes no data-model
or API-contract changes (see research.md §4).

### Source Code (repository root)

```text
backend/            # UNCHANGED by this feature

frontend/
├── src/
│   ├── pages/
│   │   ├── CreateArchitecturePage.tsx   # canvas wrapper gets CSS resize; node own-content
│   │   │                                  divs get measurement refs; recompute effect
│   │   └── nodeLayout.ts                # pure stacking/cascading math reworked to consume
│   │                                       a measured-heights map instead of a service count
│   └── hooks/
│       └── useMeasuredHeight.ts         # NEW — small ResizeObserver-backed hook
└── tests/
    └── unit/
        └── nodeLayout.test.ts           # extended for the measured-heights-based layout fn
```

**Structure Decision**: Web application structure (already established in `001`-`004`) is
unchanged. This feature is scoped entirely to `frontend/src/pages/` (the assembly canvas
page and its layout helper) plus one new small hook under `frontend/src/hooks/` (a new
directory — this codebase didn't previously need a dedicated custom-hook module). No other
directory is touched.

## Complexity Tracking

*No violations — table not needed.*

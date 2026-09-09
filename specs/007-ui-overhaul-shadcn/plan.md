# Implementation Plan: Five-Column Workspace UI Overhaul

**Branch**: `007-ui-overhaul-shadcn` | **Date**: 2026-09-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-ui-overhaul-shadcn/spec.md`

## Summary

Replace today's two-page flow (a landing page with provider/Architecture selection, and a
separate Architecture-editing page) with one persistent, five-panel workspace screen, per the
user's annotated screenshot: provider/Architecture selection (collapsible to an icon rail);
Collection/Connector management + AWS-service search; a selected service's attributes and
pricing inputs (shown only while something is selected, collapsing otherwise); the assembled
architecture diagram; and duration/Calculate/results. Rebuilt on Tailwind CSS + shadcn/ui +
Lucide icons wherever they cleanly fit, with code simplicity prioritized over forcing them in
where they don't (the diagram's own React Flow node/edge rendering being the clear example).
Adds one genuinely new interaction: individual services listed inside a Collection's/VPC's box
become independently clickable (today only the whole box is). See `research.md` for full
rationale.

## Technical Context

**Language/Version**: TypeScript ~5.6, React 18.3, Vite 5.4 (unchanged) — this feature
touches `frontend/` only; `backend/` is untouched.

**Primary Dependencies**: New — Tailwind CSS v4 (`@tailwindcss/vite`), shadcn/ui
(CLI-scaffolded component source, not a runtime package, built on Radix UI primitives),
`lucide-react`. Unchanged — React Query, `@xyflow/react` (React Flow), `react-router-dom`.

**Storage**: N/A — no Postgres/DuckDB/API change; this is a frontend layout and visual
rebuild over the existing 001-006 data and endpoints.

**Testing**: Vitest + Testing Library for any newly-extracted pure logic (research.md §10);
`claude-in-chrome` live verification against `quickstart.md` as the primary validation method
for layout/visual/interaction behavior, per Constitution Principle V's presentational-code
allowance (matching `005`'s precedent). Existing unit-tested domain components keep their
current tests passing unchanged.

**Target Platform**: Existing web SPA, desktop-width browsers (spec Assumptions — no
dedicated narrow-screen layout in scope).

**Project Type**: Web application (existing `backend/` + `frontend/` split) — this feature is
scoped to `frontend/` only.

**Performance Goals**: No new numeric target; panel collapse/expand and service selection are
client-side state changes and must feel instant (no new network calls beyond what already
exists for Collections/Connectors/catalog search/calculation).

**Constraints**: No backend/API changes (`check-api-types` must stay clean); every existing
canvas interaction from 002-005 (pan, zoom, select, drag, individual-box resize, canvas
resize) must keep working unchanged; existing backend test suite is unaffected and stays
green as a regression check only.

**Scale/Scope**: Unchanged — same Architectures/Collections/Connectors/services scale as
today; this is a presentation-layer restructure, not a data-scale change.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applicability | Assessment |
|---|---|---|
| I. Pricing Data Integrity | N/A | No pricing values are read, computed, or displayed differently — the Calculate/results panel shows the exact same data, just relocated. |
| II. Clear Data-Layer Separation | N/A | No Postgres/DuckDB access changes. |
| III. Provider-Extensibility by Design | N/A | Provider selection (col 1) remains a modeled dimension exactly as today (AWS active, GCP/Azure disabled) — no new provider-specific assumptions introduced. |
| IV. Type-Safe Frontend/Backend Contract | N/A | No API request/response shape changes — nothing for `check-api-types` to drift on. |
| V. Test-First Development | Applies, with its own explicit carve-out used | This is layout/presentational/visual-system work, not pricing or data-relationship logic — Principle V itself permits tests-after here, validated live per research.md §10 (matching `005`'s precedent). Any pure logic that does get extracted (e.g. `ServiceConfigSelection` transitions) still gets test-first unit tests. |
| VI. Simplicity & YAGNI | Central | Drives nearly every decision in research.md: Tailwind v4's simpler setup, shadcn/ui's own "own the source" model, reusing existing hardened query/mutation logic verbatim rather than rewriting it, no new state-management library, no persistence for collapse state, and the explicit spec-level instruction that simplicity beats forced package usage. |

**Gate result**: PASS. No violations; Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/007-ui-overhaul-shadcn/
├── plan.md              # This file (/speckit-plan command output)
├── research.md           # Phase 0 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

No `data-model.md` or `contracts/` — no data-model or API-contract changes (research.md §11).

### Source Code (repository root)

```text
backend/                                     # UNCHANGED by this feature

frontend/
├── components.json                          # NEW — shadcn/ui config
├── vite.config.ts                            # MODIFIED — @tailwindcss/vite plugin, @/* alias
├── tsconfig.json                              # MODIFIED — @/* → src/* path alias
├── src/
│   ├── index.css (or app.css)                 # NEW/MODIFIED — Tailwind entry (`@import "tailwindcss";`)
│   ├── App.tsx                                # MODIFIED — both routes render WorkspacePage
│   ├── pages/
│   │   ├── WorkspacePage.tsx                  # NEW — owns shared state/mutations; assembles the 5 panels
│   │   ├── nodeLayout.ts                      # UNCHANGED (reused by ArchitectureDiagramPanel)
│   │   ├── dropTargetDetection.ts             # UNCHANGED
│   │   ├── connectorSelection.ts              # UNCHANGED
│   │   ├── LandingPage.tsx                    # REMOVED — superseded by ProviderArchitecturePanel
│   │   └── CreateArchitecturePage.tsx         # REMOVED — split across the panel components below
│   ├── components/
│   │   ├── ui/                                # NEW — shadcn/ui-generated primitives (button, input,
│   │   │                                        select, card, tooltip, scroll-area, separator, …)
│   │   ├── workspace/                         # NEW
│   │   │   ├── ProviderArchitecturePanel.tsx  # column 1
│   │   │   ├── CollectionsPanel.tsx           # column 2
│   │   │   ├── ServiceConfigPanel.tsx         # column 3
│   │   │   ├── ArchitectureDiagramPanel.tsx   # column 4 (the existing React Flow canvas, relocated)
│   │   │   └── PricingPanel.tsx               # column 5
│   │   ├── CatalogSearchPanel.tsx             # UNCHANGED contract; restyled internally, rendered by CollectionsPanel
│   │   ├── PricingInputsForm.tsx              # UNCHANGED contract; restyled internally, rendered by ServiceConfigPanel
│   │   ├── SkuDetail.tsx                      # UNCHANGED contract; restyled internally, rendered by ServiceConfigPanel
│   │   ├── DataConnectorPanel.tsx             # UNCHANGED contract; restyled internally, rendered by CollectionsPanel/ServiceConfigPanel
│   │   ├── ConfirmDeleteDialog.tsx            # UNCHANGED contract; restyled internally
│   │   └── ErrorMessage.tsx / ErrorBoundary.tsx  # UNCHANGED
│   └── lib/
│       ├── skuDetail.ts, usageQuantityHint.ts # UNCHANGED
│       └── serviceConfigSelection.ts          # NEW (if extracted per research.md §6) — pure
│                                                 ServiceConfigSelection type/transition helpers
└── tests/
    └── unit/                                  # existing suites unchanged; new suite(s) only for any
                                                  extracted pure logic (research.md §10)
```

**Structure Decision**: Web application structure (established `001`-`006`) is unchanged.
This feature is scoped entirely to `frontend/`. It introduces one new component grouping
(`components/workspace/`, the five panels) and one new generated-code grouping
(`components/ui/`, shadcn/ui primitives), while every existing domain component
(`CatalogSearchPanel`, `PricingInputsForm`, `SkuDetail`, `DataConnectorPanel`,
`ConfirmDeleteDialog`) keeps its current props/behavior contract and existing tests — only
its internal markup/styling and which parent renders it change. `LandingPage.tsx` and
`CreateArchitecturePage.tsx` are removed as page-level components; their logic is
redistributed into `WorkspacePage.tsx` and the five panel components rather than deleted.

## Complexity Tracking

*No violations — table not needed.*

# Implementation Plan: Architecture Panel Narrow-Width Layout

**Branch**: `013-column-resize-narrow-behavior` | **Date**: 2026-09-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-column-resize-narrow-behavior/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Fix the layout of column 1's expanded architecture panel (`ProviderArchitecturePanel`) so that
narrowing it via drag-resize never hides the Create button or any action button (import,
share, delete), and so that overlong architecture names wrap onto multiple lines instead of
truncating with an ellipsis. This is a presentation-layer-only CSS/layout change to one
existing component — no new data, no API changes, no new dependencies.

## Technical Context

**Language/Version**: TypeScript 5.6, React 18.3 (existing frontend stack; no version change)

**Primary Dependencies**: Tailwind CSS v4 (utility classes drive all layout), Radix UI
`ScrollArea` primitive (wraps the architecture list), existing `Button` component
(`frontend/src/components/ui/button.tsx`, already applies `shrink-0 whitespace-nowrap` to
every button)

**Storage**: N/A — no data persistence changes; this feature only changes layout/styling

**Testing**: Vitest + React Testing Library (`frontend/src/**/*.test.tsx`), consistent with
existing frontend test conventions; per Constitution Principle V, this is UI-only
presentational code so tests-after is acceptable (no pricing/DuckDB/Postgres logic involved)

**Target Platform**: Web browser (existing React SPA), same as the rest of the app

**Project Type**: Web application (frontend + backend already exists) — this feature is
frontend-only; no backend changes

**Performance Goals**: Layout must stay visually smooth during interactive drag-resize
(no jank/reflow thrashing beyond what the existing resize handle already produces)

**Constraints**: Must not change the panel's existing minimum resizable width (56px,
matching the collapsed-rail width) or its collapse/expand behavior; must not regress the
existing name truncation-on-select interaction model beyond replacing truncation with wrap

**Scale/Scope**: Single component file (`ProviderArchitecturePanel.tsx`) and its
Tailwind class usage; no new files, no new props, no new components

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (Pricing Data Integrity)**: N/A — no pricing values are read, computed, or
  displayed by this change.
- **Principle II (Clear Data-Layer Separation)**: N/A — no Postgres/DuckDB access; the
  component already receives architecture data via existing props.
- **Principle III (Provider-Extensibility)**: PASS — the panel already renders
  `selectedProvider` generically (`{selectedProvider.toUpperCase()} Architectures`); this
  change doesn't add or remove provider-specific logic.
- **Principle IV (Type-Safe Frontend/Backend Contract)**: N/A — no API/schema changes; the
  component's existing prop types are unchanged.
- **Principle V (Test-First Development)**: SATISFIED under the UI-only exception — this is
  presentational layout code with no pricing/query/persistence logic, so tests-after (a
  layout/behavior test added alongside or immediately after the fix) is permitted.
- **Principle VI (Simplicity & YAGNI)**: PASS — the fix is scoped to adjusting existing
  Tailwind utility classes on existing elements; no new abstraction, component, or
  configuration system is introduced.

No violations. Complexity Tracking table below is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/013-column-resize-narrow-behavior/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command) — no entities; noted as N/A
├── quickstart.md        # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

No `contracts/` directory: this feature makes no API/interface changes, so there is no new
contract to document (existing `ProviderArchitecturePanelProps` is unchanged).

### Source Code (repository root)

This is an existing web application (frontend + backend). This feature touches only the
frontend, and only one existing file within it:

```text
frontend/
├── src/
│   ├── components/
│   │   └── workspace/
│   │       └── ProviderArchitecturePanel.tsx   # the only file changed by this feature
│   ├── pages/
│   │   └── WorkspacePage.tsx                   # renders the panel + resize handle; unchanged
│   └── lib/
│       └── columnWidths.ts                     # MIN_WIDTH clamp; unchanged
└── tests/unit/
    └── ProviderArchitecturePanel.test.tsx       # new test file for this feature (matches
                                                  # existing convention, e.g. ServiceConfigPanel.test.tsx)

backend/                                        # untouched by this feature
```

**Structure Decision**: Single frontend component fix within the existing
frontend/backend web application structure. No new files beyond one test file; no backend
involvement.

## Complexity Tracking

*No Constitution Check violations — this section is not applicable.*

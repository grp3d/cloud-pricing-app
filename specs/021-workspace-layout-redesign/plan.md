# Implementation Plan: Workspace Layout Redesign

**Branch**: `021-workspace-layout-redesign` | **Date**: 2026-11-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/021-workspace-layout-redesign/spec.md`

## Summary

The five-column workspace becomes a header architecture menu plus three zones: an
Architecture Editor sidebar, a full-width canvas, and a two-tab inspector (Pricing and
Service) that can be split top and bottom. The app also moves to zinc greys with one blue
accent. Technically:

- **Header menu:** Column 1's list and mutations move into a header Popover (`TopTabs` →
  `ArchitectureMenu` + `useArchitectureLibrary`). The menu has one group per provider and
  uses the existing react-query keys.
- **Workspace:** `WorkspacePage` renders three zones sized by the existing `col2` and `col4`
  preferences. A pure `fitZones` function handles narrow windows.
- **Inspector:** a new `InspectorPanel` holds `PricingPanel` and the `ServiceConfigPanel`
  content as tabs. Its arrangement comes from a pure `nextArrangement` model and is saved as
  a new typed `workspace.inspector` preference.
- **Dragging tabs:** pointer events with two drop zones, plus a keyboard options menu. No
  drag-and-drop library.
- **Theme:** new zinc and blue token values in `index.css` (light and dark), shared
  `focus-ring` and `interactive` utilities, 1px canvas boxes, and a global reduced-motion
  rule.
- **Backend:** two additive changes. The `inspector` preference field, and an optional
  `provider` filter on `GET /architectures/importable`.
- **New UI components:** three shadcn components (popover, tabs, dropdown-menu), built on the
  already-installed `radix-ui`. No new npm packages.

## Technical Context

**Language/Version**:
- Frontend: TypeScript 5.6, React 18.3, Vite 5.4.
- Backend: Python 3.12, FastAPI.

**Primary Dependencies**:
- Already installed: Tailwind CSS 4.3 (`@tailwindcss/vite`), shadcn 4 (`radix-nova` style)
  on `radix-ui` 1.6, `lucide-react`, `tw-animate-css`, `@xyflow/react` 12, TanStack Query 5,
  React Router 6.
- Backend: Pydantic 2, SQLAlchemy (async).
- New: three shadcn component files only (research R1).

**Storage**: PostgreSQL `user_preferences.data` (JSON, typed by `Preferences`). One optional
field is added; there's no migration (data-model §1).

**Testing**:
- Backend: pytest.
- Frontend: Vitest with Testing Library (jsdom).
- E2E: Playwright 1.64.1 in headless Chromium, which also runs in CI's `e2e` job.

**Target Platform**: desktop browsers 1280px wide and wider (Chromium is tested), in light and
dark theme.

**Project Type**: web application (`backend/` and `frontend/`).

**Performance Goals**:
- Menu and tab changes feel instant: under 100ms to respond, and animations of 150–200ms.
- Dragging the split divider and the zone edges keeps 60fps: a width or height change only,
  with no data refetch.

**Constraints**:
- No new npm packages.
- No change to pricing logic or pricing APIs.
- Existing accessible names are kept unless replaced (contracts/ui.md).
- `ArchitectureDiagramPanel.tsx` (about 2,100 lines) gets targeted edits only: box border and
  selection classes, focus states, and connector stroke tokens. Its existing prettier
  warnings are left as they are.
- WCAG 2.1 AA contrast in both themes.

**Scale/Scope**:
- Rewritten: one page (`WorkspacePage`, about 1,100 lines) and the header.
- New: two components (`ArchitectureMenu`, `InspectorPanel`), two pure modules
  (`inspectorLayout`, `fitZones`) and one hook (`useArchitectureLibrary`).
- Removed: `ProviderArchitecturePanel`.
- Restyled: about 10 components.
- One theme file.
- Two backend endpoints touched.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Pricing Data Integrity | No price is computed, shown differently or approximated. Calculation and Price Change code is untouched; only where the Price Summary is placed changes. | ✅ Pass |
| II. Data-Layer Separation | The only write is to `user_preferences` (user-defined data). No pricing data is involved. | ✅ Pass |
| III. Multi-Provider by Design | The menu groups by the provider dimension (`GET /providers`, active only), with no provider hard-coded beyond display order. Import filtering uses the existing `ProviderCode`. | ✅ Pass |
| IV. Type-Safe Contract | `inspector` is a typed Pydantic model (`extra="forbid"`). The `provider` query parameter is typed. The generated TS types are refreshed, and CI's drift check gates them. | ✅ Pass |
| V. Test-First | Backend preference and importable tests are written before the code (contracts/api.md). `nextArrangement` and `fitZones` hold the layout logic and are unit-tested first. Presentational restyling is tests-after, which the constitution allows for UI-only code. | ✅ Pass |
| VI. Simplicity & YAGNI | Two fixed tabs, not a docking system (FR-025). No DnD or docking library. Existing preference keys are reused. The theme changes token values, not components. | ✅ Pass |

**Post-design re-check (after Phase 1)**: still passing.
- The design adds one optional preference field and one optional query parameter, both
  typed and tested first.
- No new store, service or framework.
- No pricing path is touched.
- No complexity is left to justify.

## Project Structure

### Documentation (this feature)

```text
specs/021-workspace-layout-redesign/
├── spec.md              # Feature spec (with clarifications)
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R14
├── data-model.md        # Phase 1: inspector arrangement, zone sizes, theme tokens
├── contracts/
│   ├── api.md           # Preferences `inspector`; importable `?provider=`
│   └── ui.md            # Roles and accessible names the tests rely on
├── quickstart.md        # Phase 1: validation scenarios A–E
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── models/schemas.py              # + InspectorArrangement; WorkspacePreferences.inspector
│   └── api/architectures.py           # list_importable_architectures(provider: ProviderCode | None)
└── tests/
    ├── contract/test_preferences.py   # + inspector round trip and validation (first)
    └── contract/test_architecture_sharing.py  # + importable provider filter (first)

frontend/
├── src/
│   ├── index.css                      # zinc + blue tokens (light/dark), @utility focus-ring/interactive,
│   │                                  #   reduced-motion rule
│   ├── api/
│   │   ├── client.ts                  # listImportableArchitectures(provider?)
│   │   └── generated/schema.d.ts      # regenerated
│   ├── components/
│   │   ├── ui/                        # + popover.tsx, tabs.tsx, dropdown-menu.tsx (shadcn add)
│   │   ├── layout/
│   │   │   ├── TopTabs.tsx            # split Cloud Pricing control, current-architecture label
│   │   │   └── ArchitectureMenu.tsx   # NEW: provider groups, rows, new/import per group
│   │   └── workspace/
│   │       ├── InspectorPanel.tsx     # NEW: tabs, split, drag zones, options menu, rail
│   │       ├── PricingPanel.tsx       # becomes the Pricing tab body (no own column chrome)
│   │       ├── ServiceConfigPanel.tsx # becomes the Service tab body (no own column chrome)
│   │       ├── CollectionsPanel.tsx   # left sidebar styling (bg-sidebar, padding)
│   │       ├── ArchitectureDiagramPanel.tsx  # 1px boxes, selection ring, focus, stroke tokens
│   │       ├── ImportArchitectureDialog.tsx  # + provider prop (title); fed a provider-filtered list
│   │       └── ProviderArchitecturePanel.tsx # REMOVED
│   ├── hooks/
│   │   └── useArchitectureLibrary.ts  # NEW: lists per provider + create/delete/public/import
│   ├── lib/
│   │   ├── inspectorLayout.ts         # NEW: arrangement type, defaults, nextArrangement, read/write
│   │   ├── fitZones.ts                # NEW: rendered widths for narrow windows
│   │   ├── columnWidths.ts            # ColumnId → "collections" | "inspector" (col2, col4; 320/360)
│   │   └── columnCollapse.ts          # same ids; col4 now collapsible
│   └── pages/WorkspacePage.tsx        # three zones; dispatches service-selected / calculation-finished
├── tests/unit/
│   ├── inspectorLayout.test.ts        # NEW (first)
│   ├── fitZones.test.ts               # NEW (first)
│   ├── theme.contrast.test.ts         # NEW: FR-031 pairs from index.css
│   ├── ArchitectureMenu.test.tsx      # NEW (takes over ProviderArchitecturePanel.test.tsx)
│   ├── InspectorPanel.test.tsx        # NEW
│   ├── columnWidths/columnCollapse tests  # updated ids
│   └── WorkspacePage.*.test.tsx       # updated for three zones
└── e2e/
    ├── helpers.ts                     # calculate() brings Pricing forward first
    └── layout.spec.ts                 # NEW: quickstart A–D in the browser, 1280/1600, light/dark
```

**Structure Decision**: the existing web-application layout (`backend/`, `frontend/`) is
kept. New frontend code goes next to its peers: components under `components/layout` and
`components/workspace`, logic under `lib/`, and the shared mutation hook under `hooks/`. No
new top-level folders.

## Implementation phases (for /speckit-tasks)

1. **Foundations**:
   - Backend tests first, then code: `inspector` preference and the importable `provider`
     filter. Then regenerate the API types.
   - Run `shadcn add popover tabs dropdown-menu` and confirm `package.json` is unchanged.
   - The `inspectorLayout` and `fitZones` modules, tests first.
   - The `columnWidths` and `columnCollapse` id changes.
2. **US1, header menu**:
   - `useArchitectureLibrary`, `ArchitectureMenu` and the split `TopTabs` control.
   - Remove Column 1 from `WorkspacePage`.
   - Move the Column 1 unit tests to `ArchitectureMenu.test.tsx`.
3. **US2, three zones and merged inspector**:
   - `InspectorPanel` (merged), with `PricingPanel` and `ServiceConfigPanel` as tab bodies.
   - The auto-front events and collapsed rail with its marker.
   - `fitZones` wired in, and the sidebar styling.
   - Update `e2e/helpers.ts`; the 020 specs must pass.
4. **US3, split**:
   - Drag zones and the divider.
   - Tab options menus.
   - Saving and restoring the arrangement.
5. **US4, look**:
   - The theme tokens and the contrast test.
   - The `focus-ring` and `interactive` utilities applied across the components.
   - Canvas box, selection and connector tokens.
   - Icon and number consistency.
   - Reduced motion.
6. **Polish**:
   - `e2e/layout.spec.ts`, including screenshots and the 1280 and 1600 checks.
   - Docs: the quickstart results and `docs/` screenshots if updated.
   - Full lint, build, unit and e2e runs.

## Complexity Tracking

There are no constitution violations, so no complexity needs justifying.

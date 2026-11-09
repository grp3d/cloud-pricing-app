---

description: "Task list for 021 Workspace Layout Redesign"
---

# Tasks: Workspace Layout Redesign

**Input**: Design documents from `specs/021-workspace-layout-redesign/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md,
contracts/ui.md, quickstart.md

**Tests**: Included. The constitution (Principle V) requires tests first for the backend
preference and importable changes, and the plan makes the two pure layout modules
(`inspectorLayout`, `fitZones`) test-first. Component tests may follow the code (UI-only).

**Organization**: Tasks are grouped by user story so each story can be built and checked on
its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task).
- **[Story]**: US1–US4, from spec.md.
- Paths are from the repository root (`backend/`, `frontend/`).

**Standing rules for every task**:
- `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` gets minimal hand edits
  only. Never run prettier on it or on whole folders; format only the files you touched.
- Existing accessible names are kept unless contracts/ui.md lists them as replaced or
  removed (FR-033).
- No new npm packages (plan Constraints). No change to pricing logic or pricing APIs.

---

## Phase 1: Setup

**Purpose**: add the UI building blocks and record a clean baseline.

- [ ] T001 Run `cd frontend && npx shadcn add popover tabs dropdown-menu`. This should create `frontend/src/components/ui/popover.tsx`, `frontend/src/components/ui/tabs.tsx` and `frontend/src/components/ui/dropdown-menu.tsx`, importing from the existing `radix-ui` package. Then confirm `git diff --exit-code -- frontend/package.json frontend/package-lock.json` reports no change (research R1). If shadcn tries to add a package, stop and report it to the user before going on.
- [ ] T002 Record the baseline before any change: `cd backend && uv run pytest -q`, then `cd frontend && npm run lint && npm run build && npm test && npm run test:e2e`. Note any failure that exists before 021 work starts, so it is not blamed on 021 later.

---

## Phase 2: Foundational (blocks every story)

**Purpose**: the backend contract changes, the regenerated types, and the pure layout logic
that the stories build on.

**⚠️ CRITICAL**: no user-story work starts until this phase is done.

### Tests first (they must fail before the matching code exists)

- [ ] T003 [P] Add the five `workspace.inspector` cases from contracts/api.md §1 to `backend/tests/contract/test_preferences.py`:
  1. a valid arrangement round-trips through PATCH then GET;
  2. `split: 0.1` returns 422 and the previous value is still stored;
  3. `mode: "tabs"`, or an extra key inside `inspector`, returns 422;
  4. a PATCH of `workspace` without `inspector` removes the stored one;
  5. a row stored before 021, with no `inspector`, still reads back.

  Follow the file's existing fixtures and helpers.
- [ ] T004 [P] Add the three `?provider=` cases from contracts/api.md §2 to `backend/tests/contract/test_architecture_sharing.py`:
  1. another user's public AWS and GCP architectures exist, and `?provider=gcp` returns only the GCP ones;
  2. no parameter returns both (today's behaviour);
  3. `?provider=gcp` with no GCP public architectures returns `{"groups": []}`.

  Also check that an unknown provider returns 422.
- [ ] T005 [P] Create `frontend/tests/unit/inspectorLayout.test.ts`. Write one test per row of the state-transition table in data-model §1, for both merged and split. Also cover:
  - `DEFAULT_ARRANGEMENT` equals `{mode:"merged", upper:"pricing", front:"pricing", split:0.5}`;
  - `set-split` clamps to [0.2, 0.8];
  - a split → merge → split round trip restores `upper`;
  - `readInspector(undefined)` returns the default;
  - `readInspector` of an invalid object returns the default;
  - `writeInspector(arrangement)` calls `preferencesStore.patchSection("workspace", …)` (mocked) with `inspector` set and the existing `column_widths`, `collapsed` and `last_provider` kept unchanged, because PATCH replaces the whole section (constitution V: preference write logic is tested first).
- [ ] T006 [P] Create `frontend/tests/unit/fitZones.test.ts` for `fitZones(available, sidebar, inspector)` (research R4):
  - 1280 with 320 and 360 gives a 600px canvas;
  - 1600 gives 920px;
  - when the canvas would drop below 400px, the sidebar shrinks first, then the inspector, each to no less than 56px;
  - a collapsed zone counts as 56px;
  - when even rails can't keep 400px, the canvas takes what is left (never negative);
  - the inputs are never mutated.

### Implementation

- [ ] T007 In `backend/src/models/schemas.py`, add `InspectorArrangement(_Strict)` with fields `mode: Literal["merged","split"]`, `upper: Literal["pricing","service"]`, `front: Literal["pricing","service"]` and `split: float = Field(ge=0.2, le=0.8)`, all required. Then add `inspector: InspectorArrangement | None = None` to `WorkspacePreferences`. `SCHEMA_VERSION` stays 1. T003 must pass.
- [ ] T008 In `backend/src/api/architectures.py`, add an optional `provider: ProviderCode | None = None` query parameter to `list_importable_architectures` and filter the public architectures by it before grouping. Keep the ordering: Admin first, then owners alphabetically, then names. Leave out owners with no matching architectures. T004 must pass, and so must the whole backend suite (`uv run pytest -q`).
- [ ] T009 Regenerate the frontend API types with the backend running (`cd frontend && npm run generate-api-types`), which writes `frontend/src/api/generated/schema.d.ts`. Then in `frontend/src/api/client.ts`, change `listImportableArchitectures(provider?: ProviderCode)` to append `?provider=` when one is given. `npm run check-api-types` must be clean.
- [ ] T010 [P] Create `frontend/src/lib/inspectorLayout.ts` (research R5, data-model §1). It contains:
  - the types `InspectorTab`, `InspectorMode`, `InspectorArrangement` and `InspectorAction` (`select-tab`, `drop-on-lower`, `drop-on-upper-bar`, `swap`, `merge`, `set-split`, `service-selected`, `calculation-finished`);
  - `DEFAULT_ARRANGEMENT`;
  - `other(tab)`;
  - a pure `nextArrangement(current, action)` that returns the same object when nothing changes;
  - `readInspector(workspacePrefs)`, which falls back to the default;
  - `writeInspector(arrangement)`, which calls `preferencesStore.patchSection("workspace", { ...current workspace section, inspector })` so the other workspace fields are kept, as `columnWidths.ts` does.

  T005 must pass.
- [ ] T011 [P] Create `frontend/src/lib/fitZones.ts`, exporting `fitZones(available, { sidebar, sidebarCollapsed, inspector, inspectorCollapsed })`. It returns `{ sidebar, canvas, inspector }` rendered widths, using `MIN_WIDTH` (56) from `frontend/src/lib/columnWidths.ts` and a canvas minimum of 400. T006 must pass.
- [ ] T012 In `frontend/src/lib/columnWidths.ts` and `frontend/src/lib/columnCollapse.ts`, add a new `"inspector"` id mapped to `col4`, with a default width of 360 and collapsible through `collapsed.col4`. Keep the `"provider"`, `"service"` and `"pricing"` ids for now, because `WorkspacePage` still uses them; US1 and US2 remove them. Extend `frontend/tests/unit/columnWidths.test.ts` and `frontend/tests/unit/columnCollapse.test.ts`:
  - `inspector` reads a saved `col4` (the Price Summary width carries over);
  - `inspector` defaults to 360 when nothing is saved;
  - `collapsed.col4` round-trips.

**Checkpoint**: backend suite green, types clean, the new unit tests green, and the app
unchanged on screen.

---

## Phase 3: User Story 1 - Pick and manage architectures from the header (Priority: P1) 🎯 MVP

**Goal**: Column 1 moves into a header popover, grouped AWS/GCP/Azure, with every Column 1
action available there and on every page.

**Independent Test**: with architectures in all three providers, use the header menu to open
a GCP architecture, create an Azure one and delete an AWS one. Each takes effect, no
architecture column appears, and the same works from Trends and with the keyboard only
(quickstart A).

### Tests for User Story 1

- [ ] T013 [P] [US1] Create `frontend/tests/unit/ArchitectureMenu.test.tsx`. Port every case from `frontend/tests/unit/ProviderArchitecturePanel.test.tsx` (select, create, public toggle, delete with confirmation, guest restrictions, Import), switching to the new names in contracts/ui.md. Add cases for:
  - three groups named `AWS architectures`, `GCP architectures` and `Azure architectures`, in that order, with inactive providers left out;
  - an empty group still shows `New … architecture…` and `Import …`;
  - `aria-current="page"` on the open architecture's row;
  - Enter in the name field creates the architecture, and Escape clears the field without closing the menu;
  - each group's Import requests `listImportableArchitectures(<that provider>)`;
  - a group with 50 architectures scrolls inside its own list, and the other groups' headings stay reachable (spec Edge Cases, "Long lists");
  - rendered inside `TopTabs`: Escape or an outside click closes the menu and focus returns to the `Open architecture menu` chevron (US1 scenario 7).

### Implementation for User Story 1

- [ ] T014 [US1] Create `frontend/src/hooks/useArchitectureLibrary.ts` (research R2), moving the logic out of `frontend/src/pages/WorkspacePage.tsx` with its behaviour unchanged. The hook provides:
  - the active providers (`GET /providers`), in the order AWS, GCP, Azure;
  - one architectures query per active provider, with key `["architectures", provider]` (`useQueries`);
  - the `createArchitecture`, `deleteArchitecture`, `toggleArchitecturePublic` and `importArchitecture` mutations;
  - the delete confirmation state used by `ConfirmDeleteDialog`;
  - a per-provider `importableArchitectures(provider)` query with key `["importableArchitectures", provider]` and `queryFn: () => api.listImportableArchitectures(provider)`. Don't pass the function itself as `queryFn` (as `WorkspacePage.tsx` does today): React Query would call it with its context object as the first argument, which would arrive as `provider`.

  Delete keeps today's side effects: `removePricingResult(id)`, invalidating `["architectures"]`, and `navigate("/")` when the deleted architecture is the open one. Create and select navigate to `/architectures/:id`.
- [ ] T015 [US1] Create `frontend/src/components/layout/ArchitectureMenu.tsx`, using the hook from T014 and the names and roles in contracts/ui.md "Architecture menu". It has:
  - a `group` per provider, with a heading and a scroll-capped list whose heading is sticky;
  - rows with a select button plus the `Make X public/private` and `Delete X` buttons (non-guests only, as today);
  - `New <P> architecture…`, which reveals the textbox `New <P> architecture name` and a `Create` button; Enter submits, and Escape clears the field and calls `stopPropagation`;
  - an Import button named exactly `Import an AWS architecture`, `Import a GCP architecture` or `Import an Azure architecture` (contracts/ui.md), which opens `ImportArchitectureDialog` with that provider's list. Keep the names in one provider → article/label map, not built by string rules.

  Selecting a row or creating one calls `onDone()` so the popover closes.
- [ ] T016 [US1] Update `frontend/src/components/workspace/ImportArchitectureDialog.tsx` so it takes a `provider` prop, shows it in the title (e.g. "Import a GCP architecture"), and is fed the provider-filtered list. Its import behaviour and accessible names are otherwise unchanged.
- [ ] T017 [US1] Update `frontend/src/components/layout/TopTabs.tsx` to make "Cloud Pricing" a split control (FR-001, FR-005, FR-007a):
  - the existing `Cloud Pricing` `NavLink` is unchanged;
  - beside it, a chevron button `Open architecture menu` opens a shadcn `Popover` (dialog named `Architectures`) holding `ArchitectureMenu`;
  - focus returns to the chevron on close;
  - a `<Provider> · <name>` label shows the open architecture. Find it with `useMatch("/architectures/:id")` and look it up in the `["architectures", p]` caches, falling back to the existing single-architecture query. Truncate it, and show the full name in a tooltip and the accessible name.

  This works on Trends and Admin too.
- [ ] T018 [US1] Update `frontend/src/pages/WorkspacePage.tsx`:
  - remove Column 1 (`ProviderArchitecturePanel`, its `ColumnResizeHandle` "Resize provider/Architecture panel", its collapse state) and the provider-picker state;
  - remove the mutations now in `useArchitectureLibrary`;
  - derive the workspace provider as in research R3: the open architecture's provider, else `last_provider` if still active, else `aws`;
  - save `last_provider` when an architecture is opened or created;
  - with no architectures, show a prompt pointing to the "Cloud Pricing" menu to create or import one (US1 scenario 9);
  - keep the in-memory result maps.
- [ ] T019 [US1] Delete `frontend/src/components/workspace/ProviderArchitecturePanel.tsx` and `frontend/tests/unit/ProviderArchitecturePanel.test.tsx`. Remove the `"provider"` id from `frontend/src/lib/columnWidths.ts` and `frontend/src/lib/columnCollapse.ts` and their tests. A saved `col1` must still be ignored without error: add a test for it.
- [ ] T020 [US1] Update `frontend/tests/unit/WorkspacePage.pricing.test.tsx` and `frontend/tests/unit/WorkspacePage.errors.test.tsx` wherever they reach Column 1 (`Cloud providers`, `New Architecture`, `Import an architecture`). Use the header menu, or render the page at `/architectures/:id`. Change only how each control is reached, never the asserted behaviour (SC-009). Add one case: opening a GCP architecture makes the service search query the GCP catalogue (US1 scenario 2, FR-004).

**Checkpoint**: `npm run lint && npm run build && npm test` green, the 020 e2e specs still
pass (they open architectures by URL), and quickstart A passes by hand.

---

## Phase 4: User Story 2 - Edit a service and see the price beside it (Priority: P1)

**Goal**: three zones (sidebar, full-width canvas, inspector), with Pricing and Service as
tabs of one inspector and the auto-front rules.

**Independent Test**: at 1600×1000 the canvas is at least 900px wide. Selecting a service
brings Service forward, saving keeps Service in front, and Calculate brings Pricing forward
with the new total (quickstart B).

### Tests for User Story 2

- [ ] T021 [P] [US2] Create `frontend/tests/unit/InspectorPanel.test.tsx` for merged mode:
  - the `complementary` landmark `Inspector`, with tabs `Pricing` and `Service` in the tablist `Inspector tabs`;
  - clicking and arrow keys switch tabs;
  - the `arrangement.front` prop picks the visible tab;
  - the Service body stays in the DOM (hidden) while Pricing is in front, so a typed value survives a switch;
  - `Collapse inspector` / `Expand inspector`;
  - the collapsed rail shows `Pricing` and `Service` buttons, each expanding to its tab;
  - with the new-result flag set, the rail button's name is `Pricing — new result`.
- [ ] T022 [P] [US2] Extend `frontend/tests/unit/ServiceConfigPanel.test.tsx`: with nothing selected and no SKU chosen, the panel shows `Select a service on the canvas`. Existing cases keep passing.

### Implementation for User Story 2

- [ ] T023 [P] [US2] Update `frontend/src/components/workspace/PricingPanel.tsx` so it renders as a tab body: remove its own column chrome (outer width, column header, collapse) but keep `Duration`, `Calculate`, the `Calculation result` region, Price Change, the out-of-date notice and the "Price per Sku" word-wrap toggle (off by default, for the session) with their names unchanged. The body sits in its own scroll area. `frontend/tests/unit/PricingPanel.test.tsx` stays green, with only chrome-related queries changed.
- [ ] T024 [P] [US2] Update `frontend/src/components/workspace/ServiceConfigPanel.tsx` the same way: no column chrome, its own scroll area, every field name kept (`Save`, `Remove this service`, `vCPUs`, …), plus the empty prompt `Select a service on the canvas` (FR-018).
- [ ] T025 [US2] Create `frontend/src/components/workspace/InspectorPanel.tsx`, in merged mode only for now:
  - props: `arrangement`, `onAction(InspectorAction)`, `collapsed`, `onCollapsedChange`, `newResult`, `pricing: ReactNode` and `service: ReactNode`;
  - shadcn `Tabs` with the tablist `Inspector tabs`;
  - the Service `TabsContent` uses `forceMount` plus `hidden` when not active (data-model §4);
  - a header holding the `Collapse inspector` button;
  - a collapsed 56px rail with `Pricing` and `Service` icon buttons and the new-result dot (research R7).

  T021 must pass.
- [ ] T026 [US2] Rebuild the workspace row in `frontend/src/pages/WorkspacePage.tsx` as three zones (research R4, contracts/ui.md "Workspace zones"):
  - the `complementary` sidebar `Architecture Editor` holding `CollectionsPanel` (width `collections` / `col2`), with the `Resize Architecture Editor panel` handle and `Collapse panel` / `Expand panel`;
  - the canvas `ArchitectureDiagramPanel` as `flex-1 min-w-0`;
  - the `InspectorPanel` (width `inspector` / `col4`) with the `Resize inspector` handle, in place of the pricing column's handle;
  - the Service Editor column and its `Resize Service Editor panel` handle removed;
  - widths from `fitZones`, fed by `useMeasuredWidth` on the row. Fitting never writes preferences; only drags do.
- [ ] T027 [US2] Wire the auto-front events in `frontend/src/pages/WorkspacePage.tsx`:
  - hold the arrangement from `readInspector(prefs.workspace)`, and send every change through `nextArrangement` then `writeInspector`;
  - dispatch `service-selected` from every existing selection path (canvas selection, Architecture Editor row, catalogue SKU pick) and also set `collapsed.col4 = false` there (FR-018a);
  - dispatch `calculation-finished` when a calculation for the open architecture settles, with a result or an error, including the automatic one on open;
  - while collapsed, set a session `newResult` flag instead of expanding, and clear it when the inspector is expanded;
  - a service save dispatches nothing (FR-017);
  - deselection dispatches nothing, so Service stays in front with its empty prompt.
- [ ] T028 [P] [US2] Update `frontend/src/components/workspace/CollectionsPanel.tsx` to sidebar styling (FR-012): `bg-sidebar text-sidebar-foreground`, consistent padding, and its own scroll area so long lists never push the layout.
- [ ] T029 [US2] Remove the `"service"` and `"pricing"` ids from `frontend/src/lib/columnWidths.ts` and `frontend/src/lib/columnCollapse.ts`, so `ColumnId` is `"collections" | "inspector"`. Update their tests: `col1` and `col3` are ignored without error, and a saved `col4` becomes the inspector width.
- [ ] T030 [US2] Update `frontend/tests/unit/WorkspacePage.pricing.test.tsx` and `frontend/tests/unit/WorkspacePage.errors.test.tsx` for the three zones. Wherever a test reaches `Calculate` or the result while Service is in front, click the `Pricing` tab first. Add cases:
  - selecting a service brings Service forward;
  - a finished calculation brings Pricing forward;
  - a calculation that ends in an error also brings Pricing forward (FR-016);
  - picking a SKU in the service search brings Service forward (US2 scenario 3);
  - a save keeps Service in front.
- [ ] T031 [US2] Update `frontend/e2e/helpers.ts` only (SC-009):
  - `calculate()` clicks the `Pricing` tab when it isn't selected, then clicks `Calculate`;
  - `settled()` MUST NOT change the front tab, because it runs after every save and switching tabs there would hide a break of FR-017 (a save keeps Service in front). Make it wait without needing `Calculate` to be visible: for example `expect(page.getByRole("button", { name: "Calculate", includeHidden: true })).toBeEnabled()`, or wait for the in-flight calculation's response;
  - `editService()` relies on selecting the service to bring Service forward.

  Then run `cd frontend && npm run test:e2e`. `price-change.spec.ts`, `icons.spec.ts` and `regression.spec.ts` must pass without edits.

**Checkpoint**: US1 and US2 together are the redesigned workspace. Lint, build, unit and e2e
are all green, and quickstart B passes.

---

## Phase 5: User Story 3 - Split the inspector to see both tabs at once (Priority: P2)

**Goal**: drag a tab to the lower half to split, drag back to merge, swap, resize the
divider, use the keyboard equivalents, and have the arrangement saved to the account.

**Independent Test**: drag Service to the lower half (split), reload (kept), drag it back
(merged), then do the same with the keyboard only (quickstart C).

### Tests for User Story 3

- [ ] T032 [P] [US3] Extend `frontend/tests/unit/InspectorPanel.test.tsx` for split mode:
  - two tablists, `Upper inspector pane` and `Lower inspector pane`, each with one tab;
  - `Pricing tab options` and `Service tab options` menus offer `Move to lower half` when merged and `Merge` and `Swap` when split, and each item calls `onAction` with the matching action;
  - the `Resize inspector panes` separator exposes `aria-valuenow` (20–80) and arrow keys change it in 5% steps;
  - a pointer drag past 4px over the lower half then released dispatches `drop-on-lower`;
  - a drag released outside both zones, or ended with Escape, dispatches nothing;
  - a click without movement only selects the tab.

### Implementation for User Story 3

- [ ] T033 [US3] Add split rendering to `frontend/src/components/workspace/InspectorPanel.tsx`:
  - upper and lower panes with their own tab bars, sized by `arrangement.split`;
  - each pane keeps at least its tab bar plus 120px of content; if the inspector is too short for both, it scrolls instead of overlapping (data-model §1);
  - the separator `Resize inspector panes` drags by pointer and dispatches `set-split` on pointer-up only, with arrow-key support;
  - pane height changes animate at about 150–200ms.
- [ ] T034 [US3] Add tab dragging to `frontend/src/components/workspace/InspectorPanel.tsx` (research R6):
  - pointer events with a 4px start threshold;
  - while dragging, two drop zones (the upper pane's tab bar, and the lower half) with a preview outline on the hovered zone;
  - releasing over a zone dispatches `drop-on-upper-bar(t)` or `drop-on-lower(t)`;
  - Escape or a release elsewhere cancels with no change (FR-023);
  - release the pointer capture on cancel.
- [ ] T035 [US3] Add the tab options button and shadcn `DropdownMenu` next to each tab in `frontend/src/components/workspace/InspectorPanel.tsx`. It offers `Move to lower half` when merged and `Merge` and `Swap` when split, dispatching the same actions as the drags (FR-022). Each button is named `<Tab> tab options`.
- [ ] T036 [US3] In `frontend/src/pages/WorkspacePage.tsx`, confirm the split arrangement persists through `writeInspector` and is restored from `readInspector` on load. Cover it in `frontend/tests/unit/WorkspacePage.pricing.test.tsx` with a mocked `preferencesStore`: an arrangement in the preferences renders split, and a split action calls `patchSection("workspace", …)` with `inspector` and the existing `column_widths` / `collapsed` / `last_provider` kept.

**Checkpoint**: quickstart C passes by mouse and keyboard, the arrangement survives a reload,
and unit tests are green.

---

## Phase 6: User Story 4 - A calmer, consistent look (Priority: P2)

**Goal**: zinc neutrals with one blue accent in light and dark, visible
hover/focus/pressed states everywhere, 1px canvas boxes, aligned numbers and reduced motion.

**Independent Test**: walk the workspace, Trends, Admin and every dialog in light and dark.
Only blue appears as an accent, every control shows a focus ring when tabbed to, and
`npm test -- theme` passes (quickstart D).

### Tests for User Story 4

- [ ] T037 [P] [US4] Create `frontend/tests/unit/theme.contrast.test.ts` (research R8). It reads `frontend/src/index.css` with `fs`, extracts the `:root` and `.dark` `oklch(...)` token values, converts OKLCH to linear sRGB to relative luminance (inline maths, no dependency), and asserts in both themes the pairs in data-model §3:
  - at least 4.5:1 for `foreground` on `background`, `card` and `muted`; `muted-foreground` on `background` and `card`; `primary-foreground` on `primary`; and `sidebar-foreground` on `sidebar`;
  - at least 3:1 for `ring` and `input` on `background` and `card`.

  Also assert that `--primary` is blue (hue between 250 and 270) and that `--background` has chroma under 0.01.

### Implementation for User Story 4

- [ ] T038 [US4] Replace the token values in `frontend/src/index.css` (`:root` and `.dark`) with the zinc and blue values in data-model §3, including the `--sidebar-*` tokens. Leave `--destructive` and `--chart-*` as they are. T037 must pass.
- [ ] T039 [US4] In `frontend/src/index.css`, add `@utility focus-ring` (a 2px `--ring` outline with a 2px offset on `:focus-visible`) and `@utility interactive` (hover raises the background to `--accent` or the border to `--ring`; active darkens one step) (research R9). Add one global `@media (prefers-reduced-motion: reduce)` rule setting animation and transition durations to 0.01ms (research R10).
- [ ] T040 [US4] Make targeted edits to `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`, by hand only, with no prettier (FR-028):
  - box borders `border-gray-400 dark:border-gray-600` and `border-2 border-gray-600` become a 1px `border-border` with `bg-background/50` (`dark:bg-background/40`);
  - selection is a 1px `border-primary` plus `ring-1 ring-primary`, with no size change;
  - the dot grid colour comes from `var(--border)`;
  - the connector default stroke is `var(--muted-foreground)` and the selected stroke `var(--primary)`, with arrow styles unchanged;
  - add `focus-ring` and `interactive` to icon buttons, fallback tiles, collection and box headers and connector edges.

  Run `npm test` (connector and diagram tests) after the edit.
- [ ] T041 [P] [US4] Update `frontend/src/components/workspace/PopoutCanvasDialog.tsx` so the enlarged canvas matches the main canvas: same box, selection and connector tokens, and the same `focus-ring` on its controls (spec Edge Cases, "Pop-out canvas").
- [ ] T042 [P] [US4] Apply `focus-ring` and `interactive` to the custom interactive elements that aren't from `components/ui/`:
  - `frontend/src/components/workspace/CollectionsPanel.tsx`, `frontend/src/components/CatalogSearchPanel.tsx` and `frontend/src/components/DataConnectorPanel.tsx` (rows and result items);
  - `frontend/src/components/layout/ArchitectureMenu.tsx` (rows and actions);
  - `frontend/src/components/workspace/InspectorPanel.tsx` (tabs, options buttons, divider, rail buttons);
  - `ColumnResizeHandle` in `frontend/src/pages/WorkspacePage.tsx`;
  - `frontend/src/components/layout/TopTabs.tsx` (the split control and current-architecture label). It is here rather than in T043 because T017 rewrites it, so it must wait for US1;
  - the form controls (FR-029: flat, small corner rounding, crisp focus ring, `--input` border): `frontend/src/components/providers/fieldStyles.ts`, `frontend/src/components/providers/AwsFields.tsx`, `GcpFields.tsx` and `AzureFields.tsx`, and `frontend/src/components/PricingInputsForm.tsx`. Keep every label and accessible name unchanged, since the e2e helpers use them (`vCPUs`, `Memory (GiB)`, `Operating system`, …).

  Before starting, list every element with `onClick` or `role="button"` and no focus-visible style (`grep -rn "onClick\|role=\"button\"" frontend/src`), and check each one off.
- [ ] T043 [P] [US4] Audit Trends, Admin, the header and the dialogs for hard-coded neutral or accent colours and missing states, replacing them with tokens and the two utilities:
  - `frontend/src/components/trends/TrendsChartPanel.tsx`, `MoversPanel.tsx` and `ChartSelectors.tsx`;
  - `frontend/src/components/admin/SystemInformationSection.tsx`;
  - `frontend/src/components/auth/LoginDialog.tsx`;
  - `frontend/src/components/ConfirmDeleteDialog.tsx`, `frontend/src/components/ImportResultsDialog.tsx` and `frontend/src/components/workspace/RegionSelectDialog.tsx`;
  - `frontend/src/components/layout/IdentityMenu.tsx`.

  Keep the status colours (amber, red, green) and `--chart-*` as they are (FR-026).
- [ ] T044 [P] [US4] Make icon sizes and numbers consistent (FR-029): icons beside text use `size-4`, or `size-3.5` in dense rows; prices and quantities in columns use `tabular-nums text-right`. Apply this in `frontend/src/components/workspace/PricingPanel.tsx`, `frontend/src/components/SkuDetail.tsx`, `frontend/src/components/trends/MoversPanel.tsx` and `frontend/src/components/workspace/ServiceConfigPanel.tsx`.
- [ ] T045 [P] [US4] Set the motion on the new components: `popover.tsx`, `dropdown-menu.tsx` and `tabs.tsx` in `frontend/src/components/ui/` use tw-animate-css `data-[state]` enter and exit animations at `duration-150`. Confirm the reduced-motion rule from T039 disables them (FR-032).

**Checkpoint**: quickstart D passes in light and dark, the contrast test is green, and the
canvas tests are green.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T046 Create `frontend/e2e/layout.spec.ts`, automating quickstart A–D with the helpers from `frontend/e2e/helpers.ts`:
  - **A:** the header menu on the workspace and on Trends; open, create and delete from the menu; Import filtered by provider; keyboard only.
  - **B:** auto-front for selection, save and calculation; collapsed inspector with the rail marker.
  - **C:** split, merge and swap by mouse drag and by the options menu; the arrangement restored after a reload.
  - **D:** at 1280×800, `document.documentElement.scrollWidth <= clientWidth` on the workspace, Trends and Admin (SC-008), and the canvas is about 600px or wider; at 1600×1000 the canvas is at least 900px; light and dark screenshots of each zone attached with `testInfo.attach`.
- [ ] T047 Check no removed name lingers. Run `grep -rn "Cloud providers\|Resize provider/Architecture panel\|Resize Service Editor panel\|Resize pricing panel\|ProviderArchitecturePanel" frontend/src frontend/tests frontend/e2e`; it must return nothing.
- [ ] T048 Run the full checks:
  - `cd backend && uv run pytest -q`;
  - `cd frontend && npm run check-api-types && npm run lint && npm run build && npm test && npm run test:e2e`.

  Format only the files 021 touched, never whole folders, and never `ArchitectureDiagramPanel.tsx`. Report any failure with its output.
- [ ] T049 Walk through quickstart A–E by hand (including E, the regressions: pop-out canvas, export and import, connectors and arrow styles, sharing, saved widths) and note the results in `specs/021-workspace-layout-redesign/quickstart.md` under a "Results" heading.
- [ ] T050 [P] Update `docs/functionality.md` to describe the header architecture menu, the three-zone workspace and the inspector tabs and split, in place of the five columns.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup. Blocks every story.
- **US1 (Phase 3)** and **US2 (Phase 4)**: both after Foundational.
  - They touch `WorkspacePage.tsx` and the `WorkspacePage.*` tests, so do them one after the other: US1 then US2.
  - US2 doesn't need US1's menu to be tested, because the e2e specs open architectures by URL.
- **US3 (Phase 5)**: after US2, since it extends `InspectorPanel`.
- **US4 (Phase 6)**:
  - T037–T039 (theme, utilities, motion) can start right after Foundational.
  - T040, T041, T043 and T044 can also start then, as they don't depend on the new components.
  - T042 and T045 need US1–US3's components to exist.
- **Polish (Phase 7)**: after all stories.

### Within each phase

- Tests marked first (T003–T006, T013, T021–T022, T032, T037) are written and seen failing before their code.
- Backend: T007 then T008, then T009 (types need both).
- `InspectorPanel`: T025 then T033 then T034 then T035.

### Parallel opportunities

- Phase 2: T003, T004, T005 and T006 together; then T010 and T011 together, alongside T007/T008.
- US1: T013 runs alongside T014.
- US2: T021, T022, T023, T024 and T028 together.
- US4: T037 first, then T041, T043 and T044 in parallel with T040.
- Polish: T050 alongside T046.

## Parallel Example: Foundational

```bash
# Tests first, four files at once:
Task: "inspector cases in backend/tests/contract/test_preferences.py"            # T003
Task: "?provider cases in backend/tests/contract/test_architecture_sharing.py"   # T004
Task: "frontend/tests/unit/inspectorLayout.test.ts"                              # T005
Task: "frontend/tests/unit/fitZones.test.ts"                                     # T006
# Then the pure modules together:
Task: "frontend/src/lib/inspectorLayout.ts"                                      # T010
Task: "frontend/src/lib/fitZones.ts"                                             # T011
```

## Parallel Example: User Story 2

```bash
Task: "InspectorPanel merged tests in frontend/tests/unit/InspectorPanel.test.tsx"  # T021
Task: "PricingPanel as tab body"                                                    # T023
Task: "ServiceConfigPanel as tab body + empty prompt"                               # T024
Task: "CollectionsPanel sidebar styling"                                            # T028
```

## Implementation Strategy

### MVP first (US1)

1. Phases 1–2 (setup and foundations).
2. Phase 3 (US1): the header menu replaces Column 1, and the workspace gains its width.
3. **Stop and check** quickstart A. This can ship on its own, as four columns under a header
   menu.

### Incremental delivery

1. US1, the header menu (MVP).
2. US2, three zones and the merged inspector. This is the main user-visible goal; ship US1
   and US2 together if one release is wanted.
3. US3, split, merge and swap.
4. US4, the zinc and blue look and the states (theme tokens can land earlier; see
   Dependencies).
5. Polish: the layout e2e spec, full checks and docs.

### Notes

- Commit only when the user runs `/speckit-git-commit`, never
  `specs/018-app-cloud-deployment/acceptance.md`.
- Tick each task `[X]` here as it is completed.

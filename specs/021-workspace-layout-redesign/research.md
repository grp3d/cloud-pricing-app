# Research: Workspace Layout Redesign (021)

Each decision is recorded as Decision, Rationale and Alternatives considered. Facts about the
current code come from reading it on 2026-11-08 (branch `021-workspace-layout-redesign`, from
020 at `8069bcf`).

## R1. UI primitives: shadcn Popover, Tabs and DropdownMenu, with no new npm packages

**Decision**: Add three shadcn components with `npx shadcn add popover tabs dropdown-menu`.
They are written into `frontend/src/components/ui/` and use the `radix-ui` package the app
already depends on, matching the existing components there (button, dialog, select,
tooltip…). Afterwards, confirm that `package.json` and `package-lock.json` are unchanged.

**Rationale**:
- Tailwind v4 (`@tailwindcss/vite`), shadcn (`components.json`, style `radix-nova`),
  `radix-ui`, `lucide-react` and `tw-animate-css` are all installed already.
- The three components bring keyboard handling, focus return and ARIA roles that would
  otherwise be hand-written.

**Alternatives considered**:
- *shadcn Sheet for the Service editor:* rejected. A Sheet is a modal dialog: it dims the
  page and blocks the canvas, which defeats "edit and see the total". The clarified design is
  a tabbed inspector instead.
- *DropdownMenu for the architecture list:* rejected. Rows have their own buttons (public,
  delete), and creating one needs a text box. A menu's single-item rows and typeahead fight
  both (see R2).
- *A docking library (dockview, flexlayout-react):* rejected. It is a new dependency for two
  tabs; spec FR-025 limits scope to exactly these two (constitution VI).

## R2. Header architecture menu

**Decision**:
- **Split control:** `TopTabs` gets a control in two parts. The "Cloud Pricing" `NavLink` is
  unchanged. Beside it is a chevron button (accessible name "Open architecture menu") that
  opens a Popover holding a new `ArchitectureMenu` component.
- **Header label:** it shows "Provider · Architecture name" for the open architecture. The
  name is truncated, with the full name in a tooltip and the accessible name.
- **Groups:** the menu shows one group per *active* provider from `GET /providers`, in the
  order AWS, GCP, Azure. Each group lists that provider's architectures from the existing
  query key `["architectures", provider]`, one query per provider, so every existing
  `invalidateQueries({ queryKey: ["architectures"] })` call still refreshes the menu.
- **Row actions:** each row is a select button plus the existing "Make X public/private" and
  "Delete X" icon buttons, which keep their current accessible names. Each group ends with:
  - "New architecture…", which reveals an inline name field and a Create button;
  - "Import", which opens the existing `ImportArchitectureDialog`, filtered to that provider
    (R12).
- **Shared hook:** the mutations move out of `WorkspacePage` into a hook,
  `useArchitectureLibrary`, used by the menu. The hook covers create, delete, toggle public,
  import, and the delete confirmation dialog.
- **Delete:** it keeps today's side effects:
  - `removePricingResult(id)`;
  - invalidate `["architectures"]`;
  - `navigate("/")` if the deleted architecture is open.

  `WorkspacePage` keeps in-memory result maps keyed by architecture id. An entry for a
  deleted id is never read again, so no cross-component signal is needed.
- **Create:** it navigates to the new architecture, and the Popover closes. Picking a row on
  Trends or Admin navigates to `/architectures/:id`, the same route used today.
- **Keyboard:**
  - Radix Popover moves focus into the panel on open, traps nothing, and returns focus to
    the chevron on Escape or an outside click.
  - Inside, the natural Tab order is row → its actions → next row.
  - In the name field, Enter submits and Escape clears the field and stops the event, so the
    first Escape cancels the name and a second one closes the menu (spec Edge Cases).
- **Long lists:** each group's list is capped in height and scrolls. Group headings stay
  sticky within the Popover's own scroll area.

**Rationale**:
- Keeps one source of truth (the react-query cache) for the lists.
- Reuses the existing dialogs and accessible names, so the Column 1 tests can be moved over
  rather than rewritten.
- Works from any page, since `TopTabs` sits above the routes.

**Alternatives considered**:
- *Keep the state in `WorkspacePage` and pass it up through context:* rejected. The menu
  must work on Trends and Admin, where `WorkspacePage` isn't mounted.
- *One `?provider`-less list call:* rejected. The API filters by provider (a required
  default, `aws`), and three small cached queries are simpler than an API change.

## R3. "Selected provider" after Column 1 is gone

**Decision**:
- The provider-picker state in `WorkspacePage` is removed. The workspace's provider is:
  - the open architecture's provider;
  - otherwise the saved `workspace.last_provider`, if it is still active;
  - otherwise AWS.
- `last_provider` is saved when the user opens or creates an architecture.
- It decides which catalogue the empty workspace's search would use, and which group the
  menu scrolls to first. Its existing clean-up of a stale value stays as it is.

**Rationale**: The provider now follows the architecture (FR-004). Keeping `last_provider`
means the existing account preference stays meaningful, with no schema change.

**Alternatives considered**: dropping `last_provider` (rejected: it would need a preference
clean-up for no gain).

## R4. Three-zone layout and fitting narrow windows

**Decision**:
- **Zones:** `WorkspacePage` renders three zones in a flex row under the header:
  - **Left sidebar:** today's `CollectionsPanel`, on `bg-sidebar`. Width `col2`, default
    320px. Collapsed state is `collapsed.col2`, as today.
  - **Canvas:** `ArchitectureDiagramPanel`, `flex-1 min-w-0`.
  - **Inspector:** new. Width `col4`, default 360px (the saved Price Summary width carries
    over). Collapsed state is `collapsed.col4`.
- **Removed:** `ProviderArchitecturePanel`, Column 1's resize handle, `ServiceConfigPanel` as
  a column, and its resize handle. `ServiceConfigPanel`'s content moves into the inspector's
  Service tab.
- **Fitting:** a pure function, `fitZones(available, sidebar, inspector)`, returns the widths
  to render. The canvas keeps at least 400px. Below that, the sidebar and then the inspector
  give up width, each down to its 56px rail (`MIN_WIDTH`). The saved widths are never
  rewritten by fitting, only by the user dragging.
- **Resizing:** `available` comes from the existing `useMeasuredWidth` hook on the workspace row. The
  existing `ColumnResizeHandle` is reused for the two inner edges.

**Rationale**:
- At 1280px: 1280 − 320 − 360 = 600px of canvas (clarification 2).
- At 1600px: 920px, which meets SC-001's 900px or more. Today it is about 440px.
- Keeping `col2` and `col4` means saved widths carry over with no migration (FR-011).

**Alternatives considered**:
- *CSS-only flex-shrink:* rejected. It can't express "shrink the sidebar first, then the
  inspector, and keep the canvas at 400px" without layout jumps, and it is hard to test.
- *New preference keys for the zones:* rejected. The `col2` and `col4` keys already carry
  the right values.

## R5. Inspector arrangement: a pure state model

**Decision**:
- The arrangement is a small value: `{ mode, upper, front, split }`, as defined in
  data-model §1.
- All changes go through one pure function in a new module, `src/lib/inspectorLayout.ts`:
  `nextArrangement(current, action)`. Its actions are:
  - `select-tab`;
  - `drop-on-lower`;
  - `drop-on-upper-bar`;
  - `swap`;
  - `merge`;
  - `set-split`;
  - `service-selected`;
  - `calculation-finished`.
- The function encodes FR-015 to FR-017 and FR-019 to FR-023. It is unit-tested before the
  component is written.
- `WorkspacePage` dispatches:
  - `service-selected` from its existing select handlers (canvas, Architecture Editor,
    catalogue SKU pick);
  - `calculation-finished` when a calculation for the open architecture settles, with a
    result or an error. That includes the automatic one on open (FR-017 of 015).
- A save does nothing to the arrangement (clarification 1).
- **Saving:** every change is saved through `preferencesStore.patchSection("workspace", …)`,
  like column widths. Divider drags save on pointer-up only.

**Rationale**:
- The rules ("which tab comes forward when") are the riskiest part to get subtly wrong. A
  pure function makes each one a one-line test.
- The front-tab rules are UI state, not price logic, but the constitution's test-first
  approach is still cheap here.

**Alternatives considered**: state spread across components (rejected: the rules would be
scattered and untestable).

## R6. Dragging tabs: pointer events, with no drag-and-drop library

**Decision**:
- Tabs are dragged with pointer events, the same technique as `ColumnResizeHandle`.
  - **Start:** the drag begins after 4px of movement, so a click still selects the tab.
  - **Drop zones:** while dragging, the inspector shows two zones, the upper pane's tab bar
    and the lower half. A preview outline shows which one is under the pointer.
  - **Drop:** releasing over a zone dispatches the matching action.
  - **Cancel:** releasing elsewhere, or pressing Escape, cancels the drag.
- **Keyboard:** each tab has a small options button (accessible name "Pricing tab options" /
  "Service tab options") that opens a DropdownMenu.
  - When merged, it offers "Move to lower half".
  - When split, it offers "Merge" and "Swap".
  - Each item dispatches the same action as the matching drag (FR-022).
- **Tabs themselves:** the shadcn Tabs give arrow-key switching and `role="tab"` /
  `aria-selected`.

**Rationale**:
- There are only two drop zones. Pointer events are already used and tested in this
  codebase, and Playwright's mouse API drives them reliably.
- HTML5 drag-and-drop gives poor drag previews, has no reliable Escape-to-cancel, and is
  awkward in tests.

**Alternatives considered**: `@dnd-kit` (rejected: a new dependency for two zones); HTML5
drag-and-drop (rejected for the reasons above).

## R7. Collapsed inspector

**Decision**:
- `collapsed.col4` collapses the inspector to the 56px rail. The rail shows a Pricing and a
  Service icon button, which expand to that tab.
- `service-selected` also sets `collapsed.col4 = false` (FR-018a).
- `calculation-finished` while collapsed sets an in-session flag. The flag shows a dot on
  the rail's Pricing button, with accessible name "Pricing — new result", and clears when
  the inspector is expanded.

**Rationale**: matches clarification 5. The flag is per session because it is a
notification, not a preference.

## R8. Theme: zinc neutrals with a blue accent

**Decision**:
- Replace the token values in `frontend/src/index.css` (`:root` and `.dark`) with Tailwind
  v4's own zinc and blue palette values, which are already OKLCH, so they match Tailwind's
  documentation exactly.
- Token names stay the same, so components need no colour changes for the theme itself.
- The mapping is in data-model §3. In outline:
  - **Light:** background zinc-50 (cards and popovers white), foreground zinc-900, muted text
    zinc-500, borders zinc-200, sidebar zinc-100, primary blue-600 with white text, ring
    blue-600.
  - **Dark:** background zinc-950, foreground zinc-50, muted text zinc-400, borders zinc-800,
    sidebar zinc-900, primary blue-600 with white text, ring blue-500.
- **Kept as they are:**
  - `--destructive`;
  - the status colours in components (amber for out of date, red and green for Price
    Change, green for "Imported");
  - `--chart-*`;
  - provider logos and service icons.

  They are status or data colours, not accents (FR-026).
- **Hard-coded neutrals:** the hard-coded neutral classes are replaced with tokens. These are
  the canvas box borders in `ArchitectureDiagramPanel.tsx`, today `border-gray-400 /
  dark:border-gray-600` and `border-2 border-gray-600`.
- **Contrast check:** contrast is verified by a unit test that parses the token values from
  `index.css`, converts OKLCH to sRGB, and asserts the FR-031 ratios for each text/background
  and ring/background pair, in both themes. This needs no new dependency.

**Rationale**:
- Theme values in one file change the whole app, including dark mode, with no
  component-by-component edits. This is design.md's palette expressed the way this app does
  colour since 008.
- Blue-600 on white is about 5.2:1, and white on blue-600 about 5.2:1. Blue-500 with white
  text would be about 3.7:1, which fails AA, so dark mode keeps blue-600 for filled buttons
  and uses blue-500 only for the ring (3:1 or more against zinc-950).

**Alternatives considered**: writing `bg-zinc-*` and `bg-blue-600` classes into components,
as design.md literally says (rejected: it bypasses the tokens and breaks dark mode).

## R9. Interaction states, borders, icons and numbers

**Decision**:
- **Shared utilities:** add two in `index.css`:
  - `@utility focus-ring`: a 2px `--ring` outline with a 2px offset, on `:focus-visible`;
  - `@utility interactive`: hover raises the border to `--ring`, or the background to
    `--accent`; active darkens one step.
- **Where they go:** apply them to every custom interactive element that doesn't come from
  `components/ui/` (shadcn's Button, Input and Select already have focus-visible rings):
  - canvas icon buttons and fallback tiles;
  - collection and box headers;
  - connector edges (focus);
  - Architecture Editor rows;
  - catalogue search results;
  - architecture menu rows;
  - tabs and their options buttons;
  - resize handles and the split divider;
  - rail buttons.
- **Audit:** recorded in tasks (8 elements have `focus-visible` today; 22 have hover
  styles).
- **Canvas boxes:**
  - **Resting:** a 1px `border-border` with `bg-background/50` (light) or
    `bg-background/40` (dark).
  - **Selected:** a 1px `border-primary` plus a 1px `ring-primary` outside the box, so
    selection doesn't change the box's size (no layout shift).
  - **Grid:** the dot grid colour comes from `--border`.
  - **Connector lines:** default stroke `--muted-foreground`, selected stroke `--primary`.
    The arrow style is unchanged.
- **Icons:** beside text they use `size-4`; in dense rows, `size-3.5`. Prices and quantities
  are already `tabular-nums` in `PricingPanel`; apply the same, with right alignment,
  everywhere numbers appear in columns.

**Rationale**: design.md's state and density rules applied through two utilities, not
copied class lists, so the rules stay consistent and reviewable.

## R10. Motion

**Decision**:
- Popover, DropdownMenu and Tabs content use tw-animate-css's `data-[state]` animations at
  150ms. The inspector's split and merge animate pane height at 150–200ms.
- One global `@media (prefers-reduced-motion: reduce)` rule in `index.css` sets animation
  and transition durations to 0.01ms.

**Rationale**: FR-032 in one place. A global reduced-motion rule can't be forgotten on a new
component.

## R11. Preferences contract: one new typed field

**Decision**:
- Add `inspector: InspectorArrangement | None` to `WorkspacePreferences`, in
  `backend/src/models/schemas.py`, where unknown keys are rejected (`_Strict`). The field is
  optional and additive, so `SCHEMA_VERSION` stays 1 and stored rows stay valid. The field
  definitions are in data-model §1 and contracts/api.md.
- Inspector width and collapsed state reuse `column_widths.col4` and `collapsed.col4`. `col4`
  is already a valid `ColumnKey`; today the Price Summary has a width but no collapsed state.
- **Frontend:**
  - `columnWidths.ts`: `ColumnId` becomes `"collections" | "inspector"`, with keys `col2`
    and `col4`, and defaults 320 and 360.
  - `columnCollapse.ts`: the same.
  - `col1` and `col3` are no longer read and are left in place (spec Assumptions).
  - The generated API types are refreshed (`npm run generate-api-types`), and CI's drift
    check enforces this.

**Rationale**:
- Principle IV: the new state crosses the boundary typed.
- Principle V: preferences are Postgres read/write logic, so the backend tests in
  `contract/test_preferences.py` are written first.

**Alternatives considered**:
- *Storing the arrangement in browser storage only:* rejected. FR-024 requires it on other
  devices.
- *A new preferences section:* rejected. It belongs with the other workspace layout values.

## R12. Import, filtered by provider

**Decision**:
- `GET /architectures/importable` takes an optional `provider` query parameter. When it is
  given, only that provider's public architectures are returned, with the same grouping and
  ordering as today. Without it the response is unchanged, so the endpoint stays backward
  compatible.
- The response shape doesn't change.
- `api.listImportableArchitectures(provider?)` passes it, and each group's Import uses its own
  provider. The query key becomes `["importableArchitectures", provider]`.

**Rationale**:
- Today the Import list mixes providers. From a provider group, that would let a user
  "import into GCP" an AWS architecture, which would then appear in the AWS group.
- A filter is the smallest typed change (spec FR-003).

**Alternatives considered**:
- *Adding `provider` to each item and filtering in the browser:* workable, but it still
  changes the contract and sends unneeded rows.
- *One shared Import at the bottom of the menu:* rejected. The spec puts Import in each
  group.

## R13. Tests

**Decision**:
- **Backend, test-first:**
  - `contract/test_preferences.py`: an inspector arrangement round-trips; invalid values are rejected
    (unknown mode or tab, split out of range, unknown key); a missing value is accepted.
  - The importable tests: the `provider` filter returns only that provider; no filter
    returns all, as today.
- **Frontend unit, test-first for logic:**
  - `inspectorLayout.test.ts`: every action and event rule.
  - `fitZones.test.ts`.
  - The `columnWidths` and `columnCollapse` mappings, including ignoring `col1` and `col3`.
  - The theme contrast test (R8).
- **Frontend component tests (tests-after allowed):**
  - `ArchitectureMenu`: groups; each action; keyboard; Escape on the name field; the provider
    filter on Import. It takes over `ProviderArchitecturePanel.test.tsx`'s cases.
  - `InspectorPanel`: tabs; options menu; rail; marker.
  - `WorkspacePage` tests updated for three zones.
- **E2E (Playwright):**
  - `helpers.ts`: `calculate()` first brings the Pricing tab forward when it is in the back,
    and `editService` relies on selection bringing Service forward. The existing specs then
    pass unchanged (SC-009).
  - New `e2e/layout.spec.ts`:
    - the header menu, on every page;
    - auto-front rules;
    - split, merge and swap by mouse drag and by keyboard;
    - arrangement restored after a reload;
    - collapsed-inspector behaviour;
    - canvas width at 1280 and 1600;
    - no horizontal page scroll at 1280;
    - light and dark screenshots attached to the report.

**Rationale**: covers every FR with the cheapest test that proves it, and keeps 020's
browser checks as the regression net for calculation, Price Change and icons.

## R14. design.md

**Decision**:
- `.claude/system_prompts/design.md` is applied as the spec states it (FR-026 to FR-033),
  through the theme, not literal colour classes. The file itself is left as the user wrote
  it.
- The rest of the earlier review (wording fixes, sections to add, loading it with an
  `@`-import in `CLAUDE.md`) is the user's choice, outside this feature.

**Rationale**: the user hasn't asked for the file to be edited. The spec already records how
its rules apply here.

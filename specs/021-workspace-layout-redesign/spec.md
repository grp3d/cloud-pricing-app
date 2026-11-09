# Feature Specification: Workspace Layout Redesign

**Feature Branch**: `021-workspace-layout-redesign`

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: "Modernize the Cloud Pricing workspace from its 5-column layout into a 3-zone layout: header navigation, a left sidebar, the center canvas, and a right inspector. Also re-theme to zinc with a blue accent and apply the design rules in .claude/system_prompts/design.md. (1) Move the provider and architecture selector (old Column 1) into a popover under the 'Cloud Pricing' header button, grouped by provider, each group with its architectures, 'New architecture…' and Import; everything Column 1 does still works there. (2) The Architecture Editor (old Column 2) becomes a fixed left sidebar; the canvas (old Column 4) fills the remaining space. (3) The Service Editor (old Column 3) and Price Summary (old Column 5) become a two-tab right inspector: Pricing comes to the front when a pricing update completes, Service when a service is selected; like IDE tab panels, a tab can be dragged to the lower half to split the inspector, and dragged back to merge; a keyboard alternative exists; the layout is saved to the user's account. (4) Zinc neutrals with one blue accent, changed through the theme (light and dark); explicit hover/focus/active states; thin borders; consistent icons; aligned numbers; accessible contrast and keyboard use; restrained motion; desktop-first with a stated minimum width. Everything that works today must keep working."

## Context

Today the Cloud Pricing workspace is five side-by-side columns, each with a default width:

| Column | Contents | Default width |
|---|---|---|
| 1 | Providers and architectures | 256px |
| 2 | Architecture Editor (collections and service search) | 320px |
| 3 | Service Editor | 288px |
| 4 | Canvas | Takes the remaining space |
| 5 | Price Summary (duration, Calculate, results, Price Change) | 288px |

On a 1600px-wide window the canvas, where the architecture is actually drawn, gets less than
a third of the width. The Service Editor and the Price Summary sit apart, with the canvas
between them, so a user who edits a service cannot see the new total beside the edit. This
feature regroups the same functions into three zones under a header:

- **Header:** the architecture picker.
- **Left sidebar:** the Architecture Editor.
- **Center:** the canvas.
- **Right inspector:** the Service Editor and Price Summary together, as tabs.

It also gives the app a calmer, more consistent look. No pricing behaviour changes.

## Clarifications

### Session 2026-11-08

- Q: When a service edit is saved, should the Pricing tab come to the front immediately, or only once a calculation finishes? → A: Only a finished calculation brings Pricing forward. After a save the user stays on the Service tab, and the price is marked out of date as today.
- Q: What is the narrowest window the redesigned workspace must fully support? → A: 1280px (typical laptops and up). All three zones fit at their default widths, with a canvas of about 600px.
- Q: On Trends or Admin, what should clicking "Cloud Pricing" do: open the architecture menu, or go to the workspace? → A: A split control on every page. The "Cloud Pricing" label goes to the workspace, as it does today; a chevron beside it opens the architecture menu. Picking an architecture from another page goes to the workspace with it open.
- Q: How wide should the inspector be by default, now that it holds both the Service Editor and the Price Summary? → A: 360px by default, with a saved Price Summary width carried over where one exists. It stays adjustable by dragging (saved to the account) and collapsible, as today. The "Price per Sku" word-wrap toggle is kept in the Pricing tab, unchanged: off by default, for the current session.
- Q: If the inspector is collapsed to its rail and the user selects a service, should it expand by itself? → A: Selecting a service or choosing a SKU expands it, with Service in front. A finished calculation only shows a marker on the rail. Calculate (with duration) stays in the Pricing tab and does not move onto the canvas.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pick and manage architectures from the header (Priority: P1)

A user opens the architecture menu with the chevron beside "Cloud Pricing" in the header. They see their architectures grouped
under AWS, GCP and Azure, and pick one. The workspace switches to that architecture and its
provider. From the same menu they can do everything the old Column 1 allowed:

- create a new architecture, with a name, in any provider group;
- import an architecture;
- make an architecture public or private;
- delete an architecture.

The list shows the user's own architectures, as Column 1 does today. Other users' public
architectures are reached through Import, which copies one into the user's own list.

The old Column 1 is gone, and the rest of the workspace uses the full width.

**Why this priority**: It frees the most space and is the entry point to every other action.
Without it the redesign has nowhere to put the architecture list.

**Independent Test**: With architectures in all three providers, open the header menu, pick
a GCP architecture, then create an Azure one and delete an AWS one, all from the menu. Each
action takes effect, and no architecture column appears in the workspace.

**Acceptance Scenarios**:

1. **Given** a user with AWS, GCP and Azure architectures, **When** they open the "Cloud
   Pricing" menu, **Then** the architectures are listed under three provider groups. Each
   group has a "New architecture…" action and an Import action.
2. **Given** the menu is open, **When** the user picks an architecture from another provider,
   **Then** the menu closes, the workspace shows that architecture, and the workspace's
   provider switches to match. For example, the service search then searches that
   provider's catalogue.
3. **Given** the menu is open, **When** the user chooses "New architecture…" in the GCP
   group, enters a name and confirms, **Then** a GCP architecture with that name is created
   and opened.
4. **Given** an architecture the user owns, **When** they make it public, make it private, or
   delete it from the menu, **Then** the result is the same as from the old Column 1,
   including the confirmation step before a delete.
5. **Given** the user chooses Import in a provider group, **When** the import list opens,
   **Then** it lists other users' public architectures for that provider only, grouped by
   owner as today. Importing one adds it to that group and opens nothing else.
6. **Given** any architecture is open, **When** the user looks at the header, **Then** it
   shows the current provider and architecture name. A long name is shortened with an
   ellipsis, and the full name is available on hover or focus.
7. **Given** the menu is open, **When** the user presses Escape or clicks outside it, **Then**
   it closes and focus returns to the chevron that opened it.
8. **Given** the user is on the Trends page, **When** they click the "Cloud Pricing" label,
   **Then** they go to the workspace. **When** they instead open the menu with the chevron
   and pick an architecture, **Then** they go to the workspace with that architecture open.
9. **Given** a user with no architectures, **When** they open the workspace, **Then** a clear
   prompt points them to the "Cloud Pricing" menu to create or import one.

---

### User Story 2 - Edit a service and see the price beside it (Priority: P1)

The right side of the workspace is one inspector with two tabs: **Pricing** and **Service**.
The workspace has three zones:

- the Architecture Editor in a left sidebar;
- the canvas filling the middle;
- the inspector on the right.

When the user selects a service on the canvas, or picks a SKU in the service search to add
it, the Service tab comes to the front with that service's editor. When a calculation
finishes, the Pricing tab comes to the front with the new total and Price Change.

**Why this priority**: This is the change the user asked for most directly. Editing a service
and checking the price should happen in one place.

**Independent Test**: Open an architecture and select a service on the canvas: the Service
tab shows its editor. Change a value, save, and Calculate: the Pricing tab comes forward with
the new total.

**Acceptance Scenarios**:

1. **Given** an open architecture, **When** the workspace is shown, **Then** it has a left
   sidebar (the Architecture Editor), a center canvas and a right inspector, and no other
   columns.
2. **Given** the inspector shows the Pricing tab, **When** the user selects a service on the
   canvas, **Then** the Service tab comes to the front with that service's editor.
3. **Given** the user picks a SKU in the service search, **When** it is chosen, **Then** the
   Service tab comes to the front with the form to add it, as Column 3 does today.
4. **Given** the Service tab is in front, **When** a calculation finishes (from Calculate, or
   the automatic one when an architecture is opened), **Then** the Pricing tab comes to the
   front.
5. **Given** no service is selected, **When** the user opens the Service tab, **Then** it
   shows the prompt "Select a service on the canvas".
6. **Given** the user switches tabs by hand, **When** nothing else happens, **Then** the
   chosen tab stays in front. Only the events in scenarios 2–4 bring a tab forward on their
   own.
7. **Given** the window is widened or narrowed, **When** it is resized, **Then** the canvas
   grows or shrinks to fill the space between the sidebar and the inspector.
8. **Given** the left sidebar or the inspector, **When** the user drags its edge, **Then** it
   resizes. The width is saved to the user's account, as column widths are today. Each zone
   can also be collapsed to a narrow rail and expanded again.

---

### User Story 3 - Split the inspector to see both tabs at once (Priority: P2)

Like tab panels in a code editor, the user drags the Service tab (or the Pricing tab) to the
lower half of the inspector. The inspector splits: one tab on top, the other below, with a
divider between them that the user can drag. Dragging the lower tab back up onto the upper
tab bar merges them again into one pane with two tabs. The same moves can be made from the
keyboard. The arrangement is remembered.

**Why this priority**: The merged inspector already delivers the main benefit. Splitting adds
seeing both at once for users who want it.

**Independent Test**: Drag the Service tab to the lower half. Both panes show, Pricing above
and Service below. Reload, and the split is kept. Drag Service back up, and the inspector is
merged again. Repeat the same steps with the keyboard only.

**Acceptance Scenarios**:

1. **Given** a merged inspector, **When** the user starts dragging a tab, **Then** the lower
   half of the inspector shows a drop zone. Dropping the tab there splits the inspector, with
   the dragged tab in the lower pane.
2. **Given** a split inspector, **When** the user drags the lower pane's tab onto the upper
   pane's tab bar, **Then** the inspector merges and the dragged tab is in front.
3. **Given** a split inspector, **When** the user drags the upper tab to the lower half,
   **Then** the two panes swap. Either tab can be on top.
4. **Given** a split inspector, **When** the user drags the divider, **Then** the two panes
   resize. Neither pane can be made smaller than its tab bar plus a readable minimum of
   content.
5. **Given** a split inspector, **When** a calculation finishes or a service is selected,
   **Then** nothing moves, because both tabs are already visible.
6. **Given** a keyboard user with focus on a tab, **When** they open that tab's menu, **Then**
   it offers "Move to lower half" (merged) or "Merge" and "Swap" (split). Each one does
   exactly what the matching drag does.
7. **Given** any arrangement (merged or split, which tab is on top, divider position, front
   tab when merged), **When** the user reloads or signs in on another device, **Then** the
   same arrangement is restored.
8. **Given** a drag is cancelled (Escape, or dropped outside a drop zone), **When** it ends,
   **Then** the arrangement is unchanged.

---

### User Story 4 - A calmer, consistent look (Priority: P2)

The whole app (the workspace, Trends, Admin and every dialog) uses neutral zinc greys with a
single blue accent for actions and selected items. Every interactive element shows a clear
hover state, a keyboard focus ring and a pressed state. Canvas boxes have thin borders and
light, see-through backgrounds. Prices line up in columns. Nothing on any screen is cut off or
pushes the page off-screen.

**Why this priority**: It changes how the app feels, but none of it blocks the workflows in
Stories 1–3.

**Independent Test**: Walk through the workspace, Trends and Admin in light and dark theme.
Only one accent colour (blue) appears. Tab through every control and each one shows a focus
ring. Contrast measures meet the stated levels.

**Acceptance Scenarios**:

1. **Given** any screen, **When** it is shown in light or dark theme, **Then** backgrounds,
   borders and text are zinc greys, and the only accent colour is blue. The exceptions are
   status colours (errors, price increases and decreases) and provider logos and service
   icons, which keep their own colours.
2. **Given** any button, tab, menu item, list row, input or canvas item, **When** it is
   hovered, focused from the keyboard, or pressed, **Then** each of the three states is
   visibly distinct from its resting state.
3. **Given** a selected box, service or connector on the canvas, **When** it is shown,
   **Then** the selection uses the blue accent. Each connector keeps the arrow style the user
   chose for it (019).
4. **Given** a price list, **When** prices are shown, **Then** they are right-aligned and
   their digits line up from row to row. Values that update during a calculation don't make
   the list shift sideways.
5. **Given** the app at the minimum supported width (FR-030), **When** any panel holds more
   content than fits, **Then** that panel scrolls on its own, and the page as a whole never
   scrolls sideways.
6. **Given** a user who has asked their system for reduced motion, **When** menus open or
   panels move, **Then** they appear without animation.

---

### Edge Cases

- **Active architecture deleted from the header menu:** the workspace returns to the empty
  prompt, as it does today.
- **Long lists:** a provider group with many architectures (for example 50) scrolls inside the
  menu, and the other groups' headings stay reachable.
- **Provider group with no architectures:** it still shows its heading with "New
  architecture…" and Import, so a user can start in any provider.
- **Public architectures:** the user's own public architectures are marked as public in
  their group, as in Column 1 today. Other users' public architectures appear only in
  Import.
- **Typing in the menu:** typing a new architecture's name in the menu never triggers another
  menu action and never closes the menu. Enter confirms and Escape cancels the name.
- **Unsaved changes:** a user is mid-way through a Service tab edit and a calculation
  finishes, bringing Pricing to the front. Their unsaved changes in the Service tab are kept
  and are there when they return to it.
- **Collapsed inspector:** with the inspector collapsed, selecting a service expands it
  (Service in front). A finished calculation leaves it collapsed and marks the rail, so the
  user can see a new result is waiting.
- **Deselection:** deselecting a service while the Service tab is in front leaves the tab in
  front, showing the empty prompt.
- **Narrow windows:** the window is too narrow for sidebar, canvas and inspector at their
  saved widths. The canvas keeps a usable minimum, and the sidebar and inspector give up
  width first (down to their rails if needed).
- **Old saved settings:** a user has a saved width or collapsed state for the removed Column
  1. It is ignored without error. The saved widths for the Architecture Editor and Price
  Summary carry over to the left sidebar and the inspector.
- **Pop-out canvas:** the enlarged canvas dialog keeps working, and its icons and selection
  look the same as on the main canvas.
- **Split inspector at small heights:** if the window is too short for both panes at their
  minimum, the panes keep their minimum and the inspector scrolls. They don't overlap.

## Requirements *(mandatory)*

### Functional Requirements

**Header architecture menu**

- **FR-001**: The header's "Cloud Pricing" control MUST be split into two parts, on every
  page:
  - the "Cloud Pricing" label, which goes to the workspace as it does today;
  - a chevron beside it, which opens a menu panel listing the user's architectures, grouped
    by provider in the order AWS, GCP, Azure.
- **FR-002**: Each provider group MUST offer "New architecture…", named per group (for
  example "New GCP architecture…"), with a name field and a confirm action inside the menu,
  and Import.
- **FR-003**: Every action available in the old Column 1 MUST be available from the menu,
  with the same rules and confirmations:
  - select;
  - create;
  - import;
  - make public or private;
  - delete.

  Import in a provider group MUST list only that provider's importable architectures.
- **FR-004**: Selecting an architecture MUST open it and set the workspace's provider to that
  architecture's provider.
- **FR-005**: The header MUST show the current provider and architecture name when one is
  open. A long name MUST be shortened with an ellipsis, and the full name MUST be available
  on hover and keyboard focus.
- **FR-006**: The menu MUST be fully usable from the keyboard: open, move between rows and
  their actions, act, and close with Escape, with focus returning to the control that opened
  it.
- **FR-007**: The old Column 1 MUST no longer appear in the workspace.
- **FR-007a**: The architecture menu MUST be available from every page. Picking an
  architecture on another page (Trends, Admin) MUST go to the workspace with that
  architecture open.

**Three-zone workspace**

- **FR-008**: The workspace MUST consist of exactly three zones below the header:
  - a left sidebar holding the Architecture Editor (collections and service search);
  - a center canvas;
  - a right inspector.
- **FR-009**: The canvas MUST take all horizontal space not used by the sidebar and the
  inspector.
- **FR-010**: The left sidebar and the inspector MUST each be resizable by dragging their
  inner edge, and collapsible to a narrow rail. Their width and collapsed state MUST be saved
  to the user's account.
- **FR-011**: The saved Architecture Editor width MUST carry over to the left sidebar, and
  the saved Price Summary width to the inspector. Saved settings for the removed Column 1
  and Column 3 MUST be ignored without error.
- **FR-012**: The left sidebar MUST have a subtle background distinct from the canvas, and
  consistent padding.

**Inspector tabs**

- **FR-013**: The inspector MUST have two tabs:
  - **Pricing:** everything in today's Price Summary — duration, Calculate, results, Price
    Change, out-of-date notice, and the "Price per Sku" word-wrap toggle (unchanged: off by
    default, for the current session).
  - **Service:** everything in today's Service Editor — edit an existing service, add a new
    SKU, remove a service.
- **FR-014**: When merged (one pane), exactly one tab MUST be visible, and the user MUST be
  able to switch tabs by clicking or with the keyboard.
- **FR-015**: When merged, the Service tab MUST come to the front automatically when:
  - a service is selected on the canvas or in the Architecture Editor; or
  - a SKU is chosen in the service search.
- **FR-016**: When merged, the Pricing tab MUST come to the front automatically when a
  calculation completes. That includes the automatic calculation on opening an architecture,
  and covers both success and error results.
- **FR-017**: Other events MUST NOT change the front tab. In particular, saving a service edit
  MUST leave the Service tab in front; it only marks the price out of date. Unsaved input in
  the Service tab MUST be preserved when the tab is sent to the back.
- **FR-018**: With no service selected and no SKU chosen, the Service tab MUST show "Select a
  service on the canvas".
- **FR-018a**: When the inspector is collapsed to its rail:
  - selecting a service or choosing a SKU in the service search MUST expand it, with the
    Service tab in front;
  - a finished calculation MUST NOT expand it, but MUST show a visible marker on the rail
    (with an accessible label) until the user expands it.
- **FR-018b**: The duration selector and the Calculate button MUST stay in the Pricing tab,
  as part of the Price Summary. They MUST NOT move onto the canvas, the header or the
  sidebar.

**Inspector split**

- **FR-019**: The user MUST be able to drag either tab to the lower half of the inspector to
  split it into an upper and a lower pane, one tab each. A drop zone MUST be shown while
  dragging.
- **FR-020**: In split mode, dragging the lower pane's tab onto the upper pane's tab bar MUST
  merge the panes, with the dragged tab in front. Dragging the upper tab to the lower half
  MUST swap the panes.
- **FR-021**: In split mode, a divider between the panes MUST be draggable. Each pane MUST
  keep at least its tab bar plus a minimum readable content height.
- **FR-022**: Every drag action (split, merge, swap) MUST also be available from each tab's
  menu by keyboard, with the same result.
- **FR-023**: A cancelled drag (Escape, or a drop outside a drop zone) MUST leave the
  arrangement unchanged.
- **FR-024**: The inspector arrangement MUST be saved to the user's account and restored on
  reload and on other devices. It covers merged or split, which tab is on top, the divider
  position, and the front tab when merged.
- **FR-025**: The split MUST support exactly these two tabs. A general system for arranging
  any panel anywhere is out of scope.

**Visual system**

- **FR-026**: The app's colour theme MUST move from the current sky-blue neutrals to zinc
  neutrals with a single blue accent, in both light and dark theme. It applies to every page
  and dialog. Status colours, provider logos and service icons keep their own colours.
- **FR-027**: Every interactive element MUST have distinct hover, keyboard-focus and pressed
  states. Keyboard focus MUST be shown as a clearly visible ring.
- **FR-028**: Canvas boxes MUST use thin (1px) borders and light, partly see-through
  backgrounds. Selected canvas items MUST use the blue accent. Connector lines MUST use the
  theme's colours, and each connector MUST keep its arrow style.
- **FR-029**: The visual rules MUST hold across the app:
  - Icons beside text MUST use one consistent size.
  - Prices and quantities MUST be right-aligned, with digits of equal width.
  - Form controls MUST be flat, with small corner rounding and a crisp focus ring.
- **FR-030**: The app MUST support windows 1280px wide and wider (desktop-first). At that
  width, all three zones MUST be usable at their default widths, with the canvas at least
  about 600px wide. The page MUST never scroll
  sideways at any width; panels scroll inside themselves.
- **FR-031**: Text and essential interface elements MUST meet WCAG 2.1 AA contrast in light
  and dark theme:
  - 4.5:1 for normal text;
  - 3:1 for large text, focus rings, and borders that are the only visible boundary of a
    control (WCAG 1.4.11).
- **FR-032**: Menus, tab changes and panel movements MUST animate in about 150–200ms, and
  MUST appear without animation when the user's system asks for reduced motion.
- **FR-033**: All controls MUST have accessible names. Controls that exist today MUST keep
  their current accessible names unless this spec replaces the control.

**Preserved behaviour**

- **FR-034**: Everything else that works today MUST keep working unchanged:
  - calculation and Price Change (including 020's fixes);
  - connectors and arrows;
  - provider service icons;
  - icon and box positions;
  - the pop-out canvas;
  - export and import;
  - sharing and public architectures;
  - account-saved preferences;
  - the Trends and Admin pages.

### Key Entities

- **Inspector arrangement** (a per-user saved preference, like column widths). It records:
  - mode: merged or split;
  - which tab is in the upper pane;
  - the divider position (split);
  - the front tab (merged).
- **Workspace zone sizes** (per-user saved preferences):
  - left sidebar width and collapsed state;
  - inspector width and collapsed state.

  These replace the four column widths. Two of the old values carry over.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At a 1600px-wide window with default widths, the canvas is at least twice as
  wide as it is today. Today it is about 440px; the target is at least 900px.
- **SC-002**: Switching to any architecture, including one from a different provider, takes
  at most 2 actions from anywhere in the workspace: open the menu, pick.
- **SC-003**: A user can edit a service, save, calculate and read the new total and Price
  Change without moving their eyes or pointer out of the inspector.
- **SC-004**: 100% of the actions available in the old Column 1 can be done from the header
  menu, with mouse and with keyboard only.
- **SC-005**: Split, merge and swap can each be done with mouse and with keyboard only. The
  chosen arrangement is restored on 100% of reloads.
- **SC-006**: All text and essential interface elements meet the FR-031 contrast levels in
  both light and dark theme. Every interactive element shows a visible keyboard focus ring.
- **SC-007**: Only one accent colour (blue) appears in the interface, apart from status
  colours, provider logos and service icons.
- **SC-008**: At 1280px and above, no page scrolls sideways, and no control is cut off or
  hidden.
- **SC-009**: Every existing automated check for calculation, Price Change, icons,
  connectors, import and export, and sharing still passes. Tests are updated only where the
  control they reach has moved, not where the behaviour has changed.

## Assumptions

- **Two inspector tabs:** the inspector holds only Pricing and Service. Other panels
  (Architecture Editor, canvas) are not draggable into it, and it can split into at most two
  panes, stacked top and bottom.
- **Front tab on first use:** the inspector starts merged, with Pricing in front.
- **Default sizes:** the left sidebar starts at its saved or default width (today's 320px),
  and the inspector at the saved Price Summary width, or 360px when there is none (confirmed
  in Clarifications). Both remain adjustable by dragging.
- **What counts as a "pricing update":** a calculation completing, with a result or an
  error. Saving a service edit marks the price out of date but doesn't bring Pricing
  forward, because it doesn't produce a new total (confirmed in Clarifications).
- **Dark theme:** the theme is updated and checked in dark mode, because the app has dark
  colours defined and the tests check them. Adding a visible light/dark switch is out of
  scope.
- **Selection colour:** selected canvas items take the new blue accent. Connectors have no
  user-chosen colour (only an arrow style), so their lines take the theme's colours.
- **Old preferences:** saved preferences for the removed columns stay in the user's account,
  unused. Cleaning them up is not needed.
- **Mobile:** tablets and phones are out of scope. The minimum supported width is 1280px.
- **The only backend change is saving the new preferences:** the per-user preference store
  from 019 holds typed, versioned layout settings. Its layout section knows only the four
  column keys today, so it is extended to hold the inspector arrangement (a typed addition,
  per the constitution's Principle IV). Pricing, data and every other API stay unchanged.
- **Design rules:** the rules in `.claude/system_prompts/design.md` apply as stated in
  FR-026–FR-033, using the app's theme rather than fixed colour values.

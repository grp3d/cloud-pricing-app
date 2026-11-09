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

### Session 2026-11-09

- Q: What colour should the header be? → A: Dark zinc in both themes (zinc-900; in dark mode set off from the zinc-950 page by a border), with its text lightened as needed to meet contrast. The architecture menu that drops from it keeps the normal surface colours.
- Q: Where should the open architecture's name go once it leaves the header? → A: In a title row at the top of the canvas, not in the sidebar, because the sidebar can collapse to its rail.
- Q: Should a light-blue (nothing to save) Save button still be clickable? → A: Yes. Save and Calculate both stay clickable when light blue; the colour only signals whether there is something new to save or price.
- Q: Do these refinements belong in 021? → A: Yes, as User Story 5 in the same release.
- Q: How should the architecture menu show the three providers? → A: Collapsed to a short list (AWS, GCP, Azure). Hovering or clicking a provider shows its architectures, New and Import in a panel to the right of the list (User Story 6).
- Q: How is an architecture renamed? → A: An edit (pencil) button between the share and delete buttons in the menu turns the name into a text field, prefilled and selected, to type over. Enter or leaving the field saves; Escape cancels.
- Q: GCP and Azure services show only codes (e.g. "95FF-2EF5-5EA1 / EE2C-E844-D760") on hover and in the Service tab. Where should readable names appear, and what about the codes? → A: In all three places (canvas hover, Service tab, Price per SKU list), with the codes kept as a muted line. Names drawn on the canvas itself are a follow-up feature (User Story 7).
- Q: Azure descriptions repeat words ("… P10 LRS P10 LRS Disk") and Azure service names can be broad ("Storage"). What should change? → A: Remove the repeated words. The broad service name is fine for now, since the details show on hover and in the Service tab.
- Q: Should the top of the Service and Pricing tabs stay visible while scrolling? → A: Yes. Service: the name and description line with the delete button, then a divider. Pricing: duration, total and Price Change, then the existing divider. Both stay in place; the rest scrolls (User Story 8).
- Q: The canvas hover text grows with the canvas zoom and can get far too large. Should it? → A: No. It stays at its normal (100%) size at every zoom (User Story 9, superseding 015's FR-014).

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

### User Story 5 - Header and editing refinements (Priority: P2)

The header is a dark band that sets the navigation apart from the work area, with larger
menu text. The open architecture's name moves from the header to the top of the canvas.
Adding a service from the search puts it on the diagram in one click. The Save and Calculate
buttons show, by their colour, whether there is something new to save or to price, and saving
a service keeps it open in the Service tab.

**Why this priority**: These remove clicks and guesswork from the most common loop (add a
service, adjust it, price it), but the workflow already works without them.

**Independent Test**: Open an architecture, select an application box, click a search
result's arrow: the service appears in the box and in the Service tab. Change its quantity:
Save turns dark blue; save: it turns light blue and the service stays open. Calculate is dark
blue while the price is out of date and light blue once it is current.

**Acceptance Scenarios**:

1. **Given** any page, **When** it is shown in light or dark theme, **Then** the header is a
   dark zinc band, its text and controls meet contrast, and its navigation text is larger
   than before (about 14px) in a slightly taller bar (about 48px).
2. **Given** an open architecture, **When** the workspace is shown, **Then** its provider and
   name appear in a title row at the top of the canvas and no longer in the header.
3. **Given** an application box or a connector is selected, **When** the user clicks a search
   result's arrow, **Then** the service is added there with default values, it is selected,
   and the Service tab comes to the front showing it.
4. **Given** nothing that can hold a service is selected, **When** the user clicks a search
   result's arrow, **Then** nothing is added and a message asks them to select an application
   or connector on the canvas first.
5. **Given** a service open in the Service tab, **When** the user saves it, **Then** it stays
   selected and open, showing the saved values.
6. **Given** a service open in the Service tab, **When** no field differs from what is saved,
   **Then** Save is light blue; **When** any field differs, **Then** Save is dark blue. Both
   are clickable.
7. **Given** an architecture whose price is out of date (or has never been priced), **When**
   the Pricing tab is shown, **Then** Calculate is dark blue; once the price is current, it is
   light blue and still clickable.

---

### User Story 6 - A compact architecture menu with rename (Priority: P2)

The architecture menu opens as a short list of the three providers. Hovering or clicking one
shows that provider's architectures, "New … architecture…" and Import in a panel to its
right. Each architecture has an edit button, between share and delete, to rename it in place.

**Why this priority**: The full menu grows long with many architectures, and there was no
way to rename an architecture at all.

**Independent Test**: Open the menu: only AWS, GCP and Azure show. Hover GCP: its panel
appears to the right. Click the pencil beside an architecture, type a new name and press
Enter: the menu and the canvas title show the new name.

**Acceptance Scenarios**:

1. **Given** the menu is opened, **When** it appears, **Then** it lists AWS, GCP and Azure,
   each collapsed, with no architectures shown.
2. **Given** the open menu, **When** the user hovers or clicks a provider, **Then** that
   provider's architectures, New and Import appear in a panel to the right, and any other
   provider's panel closes.
3. **Given** a provider focused from the keyboard, **When** the user presses Enter, Space or
   ArrowRight, **Then** its panel opens and focus moves into it; ArrowLeft returns to the
   provider; Escape closes the menu with focus back on the chevron.
4. **Given** an architecture in the panel, **When** the user clicks its edit button, **Then**
   the name becomes a text field holding the current name, selected. Enter or leaving the
   field saves a changed, non-blank name; Escape cancels and keeps the menu open.
5. **Given** a rename was saved, **When** the menu and the canvas title are shown, **Then**
   both show the new name.

---

### User Story 7 - Readable GCP and Azure service names (Priority: P1)

GCP and Azure services are identified by opaque codes. Wherever a service is shown (the canvas
hover text, the Service tab and the Price per SKU list), it is named by its provider service
name and its own description, as the service search shows them, with the codes kept as a
muted line.

**Why this priority**: Without it, a GCP or Azure architecture can't be read: every service
looks like "95FF-2EF5-5EA1 / EE2C-E844-D760". It is also the groundwork for showing names on
the canvas, a follow-up.

**Independent Test**: Add GCP "Cloud Storage" from the search. Hover its icon: "Cloud
Storage", its description, then the codes (muted). Select it: the Service tab heading reads
the same. Calculate: the price line reads "Cloud Storage — <description>".

**Acceptance Scenarios**:

1. **Given** a saved GCP or Azure service, **When** its canvas icon is hovered or focused,
   **Then** the text starts with the service name and description, followed by the codes,
   shown muted; its accessible name starts the same way.
2. **Given** that service selected, **When** the Service tab shows it, **Then** the heading
   is the name and description, with the codes muted beneath; a GCP service also lists its
   category path.
3. **Given** a calculation, **When** the Price per SKU list (and any "could not be priced"
   list) shows that service, **Then** it reads "name — description", the full text on hover,
   with the codes muted beneath.
4. **Given** an AWS service, **When** it is shown, **Then** it reads as before: its service
   code with its identifying details.
5. **Given** an architecture saved before this change, **When** it is opened, **Then** its
   services are named too (nothing is stored; names come from the pricing data).

---

### User Story 8 - The inspector tabs keep their top in view (Priority: P2)

When the Service or Pricing tab holds more than fits, its top stays in place and only the
rest scrolls: the service's name, description and delete button in the Service tab; the
duration, Calculate, total and Price Change in the Pricing tab. A divider separates the
pinned top from what scrolls, in both tabs.

**Why this priority**: A long list of service details or prices pushed the service's name,
its Save and delete, or the total out of view.

**Independent Test**: Select a service with many details and scroll the Service tab: the
heading and delete button stay put. Make the window short and scroll the Pricing tab: the
duration, Calculate and total stay put.

**Acceptance Scenarios**:

1. **Given** a service open in the Service tab, **When** the user scrolls it, **Then** the
   name, description, codes and delete button stay in place above a divider, and the
   details and form scroll beneath.
2. **Given** a calculation shown in the Pricing tab, **When** the user scrolls it, **Then**
   the duration, Calculate, total and Price Change (or its "not available" note) stay in
   place above the divider, and the warnings, Price per SKU list and Data Timestamp scroll
   beneath.
3. **Given** nothing priced yet, **When** the Pricing tab is shown, **Then** the duration and
   Calculate sit above the divider.

---

### User Story 9 - Canvas hover text at a fixed size (Priority: P3)

The hover text of a service on the canvas stays at its normal size whatever the canvas zoom,
instead of growing and shrinking with it.

**Why this priority**: Magnified, the text grew far too large to read comfortably; shrunk,
too small. The icons and boxes still zoom.

**Independent Test**: Zoom the canvas in and out with its controls and hover (or focus) a
service: the text is the same size each time.

**Acceptance Scenarios**:

1. **Given** the canvas at any zoom, **When** a service is hovered or focused, **Then** its
   pop-up text is the tooltip's normal size (as at 100%).
2. **Given** a service being dragged, **When** the canvas is zoomed, **Then** the dragged
   copy still matches the icon's size on screen (unchanged).

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
- **FR-005**: The current provider and architecture name MUST be shown when one is open, in a
  title row at the top of the canvas (moved from the header by FR-036). A long name MUST be
  shortened with an ellipsis, and the full name MUST be available on hover and keyboard
  focus.
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

**Header and editing refinements (User Story 5)**

- **FR-035**: The header MUST be a dark zinc band in both themes, using its own theme tokens
  (not colours hard-coded in components). Its text, icons, hover, focus and current-page
  states MUST meet FR-031 contrast against it. Its navigation text MUST be about 14px and
  the bar about 48px tall. Menus opened from it keep the normal surface colours.
- **FR-036**: The open architecture's provider and name MUST appear in a title row directly
  above the canvas, and MUST NOT appear in the header.
- **FR-037**: A search result's arrow MUST add that service, with the same default values
  the Service form starts with, to the selected box (application or VPC) or connector, then
  select it and bring the Service tab forward showing it. With nothing selected that can
  hold a service, it MUST add nothing and show "Select a box or connector on the canvas
  first". Its accessible name becomes "Add <service>" (it was "Configure <service>").
- **FR-038**: Saving a service MUST leave it selected and open in the Service tab, showing
  the saved values.
- **FR-039**: Save MUST be dark blue (the primary style) when any field differs from the
  saved service, and light blue (a soft primary style) otherwise. It stays clickable in
  both states.
- **FR-040**: Calculate MUST be dark blue when the price is out of date (FR-018a of 015) or
  the architecture has never been priced, and light blue otherwise. It stays clickable in
  both states. Save and Calculate MUST use the same light-blue style, which MUST meet
  FR-031 contrast.

**Architecture menu layout and rename (User Story 6)**

- **FR-041**: The architecture menu MUST open with the providers collapsed: AWS, GCP and
  Azure listed, with no architectures shown. Each provider MUST show its architecture count
  and state whether it is expanded (to assistive technology too).
- **FR-042**: Hovering or clicking a provider MUST show its group (architectures, "New …
  architecture…", Import, as in FR-002 and FR-003) in a panel to the right of the list, one
  provider at a time. From the keyboard, Enter, Space or ArrowRight on a provider MUST open
  its panel and move focus into it, and ArrowLeft MUST return focus to the provider. Escape
  MUST close the menu and return focus to the chevron (FR-006).
- **FR-043**: Each architecture row MUST have an edit button, "Rename <name>", between the
  share button and the delete button. It MUST turn the name into a text field holding the
  current name, selected. Enter or leaving the field MUST save a changed name; a blank or
  unchanged name MUST save nothing; Escape MUST cancel without closing the menu. The new name
  MUST be saved to the account (owner only, guests included) and shown everywhere the name
  appears. A failed save MUST keep the field open and show the error in the menu.

**Readable service names (User Story 7)**

- **FR-044**: Every saved service in an architecture's response MUST carry its item's
  description from the active pricing data (`summary`), alongside the existing
  `service_name`, resolved at response time and never stored. It is null when the item is not
  in the active data, and for AWS (whose readable details remain its attributes). An Azure
  description joins its product, SKU and meter names, leaving out any word an earlier name
  already has.
- **FR-045**: The canvas hover text and accessible name of a GCP or Azure service MUST start
  with its service name, then its description, then "service code / SKU" shown muted. AWS
  services MUST keep today's text.
- **FR-046**: The Service tab heading MUST show the service name and description, with
  "service code / SKU" muted beneath. AWS shows its service code with its identifying
  details. A GCP service MUST also list its category path in its details.
- **FR-047**: The Price per SKU list and the "could not be priced" list MUST show a GCP or
  Azure service as "name — description", with the full text on hover and "service code / SKU"
  muted beneath. AWS lines MUST keep "service code / SKU".

**Pinned tab tops (User Story 8)**

- **FR-048**: In the Pricing tab, the duration selector, Calculate, the total and the Price
  Change line (or its "not available" note) MUST stay in place above a divider while the rest
  of the tab scrolls on its own.
- **FR-049**: In the Service tab, the heading (name, description, muted codes) and the delete
  button MUST stay in place above a divider while the details and the form scroll on their
  own.

**Canvas hover text size (User Story 9)**

- **FR-050**: A canvas service's hover and focus pop-up MUST keep the tooltip's normal text
  size at every canvas zoom. This supersedes 015's FR-014 (pop-ups scaled with the zoom).
  Icons, boxes and labels still scale with the zoom.

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
  control they reach has moved, not where the behaviour has changed. The exception is the
  add-service and Save behaviour that User Story 5 changes on purpose; tests of those flows
  are updated to match.
- **SC-010**: Adding a service from the search takes one click once an application box or
  connector is selected (it took two before: the arrow, then Add).

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
- **Backend changes are small and additive:** the per-user preference store from 019 holds
  typed, versioned layout settings. Its layout section knows only the four column keys today,
  so it is extended to hold the inspector arrangement (a typed addition, per the
  constitution's Principle IV). Import gains a provider filter, and the architecture update
  gains a name for renaming (User Story 6). Pricing, data and every other API stay
  unchanged.
- **Design rules:** the rules in `.claude/system_prompts/design.md` apply as stated in
  FR-026–FR-033, using the app's theme rather than fixed colour values.

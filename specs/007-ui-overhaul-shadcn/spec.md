# Feature Specification: Five-Column Workspace UI Overhaul

**Feature Branch**: `007-ui-overhaul-shadcn`

**Created**: 2026-09-09

**Status**: Draft

**Input**: User description: "UI overhaul based on provided screen capture and usage of
Tailwind CSS + shadcn/ui + Lucide icons." The user supplied an annotated screenshot (a
layout mockup, not literal content) with the following notes:

- Note 1: "Cloud Providers in upper half, architectures defined for cloud provider in lower
  half w/ button to create new architecture at bottom of listed architectures."
- Note 2: "Upper section contains fixed fields for Collections (currently on the top of the
  architectures web page), Connect and Remove Connect buttons. Below that fixed section will
  be what is currently below the architecture pane … Search AWS Services and service
  selection to add to the selected collection."
- Note 3: "when a service is selected from the diagram or for addition to the diagram,
  service attributes (and inputs required by user) will be displayed … to right of the
  service selection and to the left of the architecture."
- Note 4: "The right most part of the screen will be the user input for Duration, Calculate
  and the calculated price."
- Final notes (augmenting/confirming the above): "this is a single display w/ 5 columnar
  sections - col 1: cloud provider + architecture selection/creation, col2: collections,
  connectors and services, col3: service attributes and user input for services, col4:
  assembled architecture, col5: user input for duration and calculated pricing."

## Clarifications

### Session 2026-09-09

- Q: Where should a Collection's or Data Connector's already-added services show up — as a
  list in the collections/search panel, or only reachable by selecting that service on the
  diagram itself? → A: Only reachable via the diagram. The collections/search panel does not
  duplicate a list of already-added services. Selecting a service **on the diagram** opens it
  in the service-configuration panel (column 3); column 3 auto-collapses (isn't shown at all)
  whenever nothing is selected. Two follow-on decisions this implies: only one service's
  configuration is shown at a time (selecting a different one replaces it, never stacks), and
  each individual service listed inside a Collection's/VPC's diagram box must become
  independently clickable — today only the whole box is selectable, not the services listed
  inside it, so this is new diagram behavior this feature must add.
- Q: Should the far-left provider/Architecture panel (column 1) stay a fixed width at all
  times, or be collapsible so the diagram can reclaim its space? → A: Collapsible. In
  collapsed mode, providers and Architectures are represented by icons rather than text
  labels, with the full text revealed on mouse-over (a tooltip). Two icon controls at the top
  of the column toggle it between expanded and collapsed.
- Q: Does this specification require Tailwind/shadcn/ui/Lucide usage everywhere
  unconditionally, or should code simplicity and maintainability be allowed to take priority
  over forcing package usage where it doesn't cleanly fit? → A: Simplicity/maintainability
  takes priority. FR-009/FR-010 apply "wherever it cleanly fits"; the clearest exception is
  the architecture diagram's own node/edge rendering (governed by the existing React Flow
  canvas, not shadcn/ui) — its internals may keep their current styling, while the panel
  chrome around the diagram still follows the shared design system like every other panel.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose a provider and Architecture from one persistent panel (Priority: P1)

A user opens the application and, in a single always-visible panel on the far left, picks a
cloud provider, sees that provider's list of Architectures, and creates a new Architecture —
all without leaving the screen they're working in. This panel can be collapsed to a narrow,
icon-only rail to give the rest of the screen more room, and expanded again, without losing
the ability to identify or pick a provider or Architecture.

**Why this priority**: This is the entry point to everything else; today it's a separate
page the user has to leave. Making it a persistent panel is the foundational structural
change the rest of the overhaul builds on.

**Independent Test**: Load the application, switch providers, create a new Architecture, and
select an existing one — verify all of this happens on the same single screen, in this one
panel, with no page navigation.

**Acceptance Scenarios**:

1. **Given** the application is open, **When** the user looks at the far-left panel,
   **Then** they see the list of cloud providers above the list of Architectures for
   whichever provider is currently selected.
2. **Given** an Architecture list for the selected provider, **When** the user looks for how
   to create a new one, **Then** the create-new-Architecture control appears below the list,
   not above it.
3. **Given** the user selects a different Architecture from the list, **When** the selection
   changes, **Then** the other four panels of the screen update to reflect the newly
   selected Architecture, with no page reload or URL-driven navigation required to see it.
4. **Given** this panel, **When** the user looks at its top, **Then** they find an explicit
   control to collapse it and, once collapsed, an explicit control to expand it again.
5. **Given** the panel is collapsed, **When** the user looks at it, **Then** providers and
   Architectures are each represented by a compact icon rather than a text label, and the
   panel is narrow enough to visibly free up space for the rest of the screen.
6. **Given** the panel is collapsed, **When** the user points at (hovers over) one of those
   icons, **Then** the provider's or Architecture's full name appears (e.g., as a tooltip).
7. **Given** the panel is collapsed, **When** the user clicks a provider's or an
   Architecture's icon, **Then** it's selected exactly as clicking its text label would be in
   the expanded state — collapsing the panel doesn't reduce what's selectable.

---

### User Story 2 - Manage Collections, Connectors, and service search in one panel (Priority: P1)

A user works with a persistent panel, positioned immediately to the left of the assembled
diagram, that always shows the controls for creating a Collection and for connecting or
removing a Data Connector, and — below that — whatever service search and selection
information belongs to the Collection or Connector currently selected.

**Why this priority**: These are the primary architecture-building actions; keeping them
permanently visible beside the diagram (rather than in a page section that scrolls away or
sits below the diagram) is central to the requested layout.

**Independent Test**: With an Architecture open, create a Collection, connect two
Collections, then search for and select an AWS service — verify the collection-creation and
Connect/Remove Connector controls stay visible throughout, regardless of how long the search
results list is.

**Acceptance Scenarios**:

1. **Given** an Architecture is open, **When** the user looks at this panel, **Then** the
   Collection-creation controls and the Connect/Remove Connector actions are visible at the
   top of the panel at all times.
2. **Given** a long list of AWS-service search results is showing below those controls,
   **When** the user scrolls through the results, **Then** the Collection-creation and
   Connect/Remove Connector controls remain in place, not scrolled out of view.
3. **Given** a Collection or a Data Connector is selected, **When** the user looks at this
   panel, **Then** they see that item's own details (its name and the ability to search for
   and select AWS services for it) — not a duplicate list of services already added to it;
   an already-added service is only reachable by selecting it on the diagram (User Story 3).

---

### User Story 3 - Configure a selected service in its own panel (Priority: P1)

When a user selects a service — either one already placed in a Collection or Data Connector
by clicking it directly on the diagram, or one just chosen from the search results to add —
the service's identifying attributes and the pricing inputs it requires appear together in a
dedicated panel positioned between the collections/search panel and the architecture diagram.
This panel shows at most one service at a time and isn't shown at all while nothing is
selected.

**Why this priority**: This is called out as its own distinct panel in the request; today
this information is buried inline within the search results, making it easy to miss which
attributes belong to which action. Reaching an already-added service only through the diagram
(Clarifications) means this panel's presence directly reflects the diagram's selection state.

**Independent Test**: Click a service directly within a Collection's box on the diagram, then
separately pick a new service from search results — verify both cases populate the same
dedicated panel with that service's attributes and required pricing inputs, that selecting a
different service replaces the panel's contents, and that the panel isn't shown when nothing
is selected.

**Acceptance Scenarios**:

1. **Given** a service already placed in a Collection, **When** the user clicks that specific
   service where it's listed inside the Collection's box on the diagram (not the box itself),
   **Then** this panel shows that service's identifying attributes and its current pricing
   inputs.
2. **Given** a service is picked from the search results to add to the selected Collection or
   Connector, **When** the user looks at this panel, **Then** it shows that service's
   identifying attributes and the pricing inputs needed before it can be added.
3. **Given** a service is already selected and shown in this panel, **When** the user selects
   a different service (from the diagram or from search results), **Then** the panel's
   contents are replaced by the newly selected service — never showing more than one service
   at once.
4. **Given** nothing is currently selected for configuration, **When** the user looks at the
   screen, **Then** this panel isn't shown (it collapses) rather than appearing as a visible
   but empty or broken panel.

---

### User Story 4 - View the assembled architecture in its own panel (Priority: P1)

A user sees the assembled architecture diagram in its own dedicated, appropriately sized
panel at the center of the screen, with the collection/search and service-configuration
panels to its left and the pricing panel to its right.

**Why this priority**: The diagram is the primary visual output of the tool; giving it a
clearly bounded central panel (rather than a fixed-height strip surrounded by unrelated
controls) is core to the requested layout.

**Independent Test**: Open an Architecture with several Collections and Connectors — verify
the diagram renders in its own bounded panel, positioned between the two left-hand panels
and the right-hand pricing panel.

**Acceptance Scenarios**:

1. **Given** an Architecture with Collections, nested Collections, and Data Connectors,
   **When** the user views the screen, **Then** the diagram appears in a single dedicated
   panel at the center, distinct from the panels beside it.
2. **Given** the diagram panel, **When** the user interacts with it (pan, zoom, select,
   drag, resize — the existing canvas interactions), **Then** every interaction continues to
   work exactly as it does today.
3. **Given** a Collection's or VPC's box on the diagram lists one or more services inside it,
   **When** the user clicks one of those individual services, **Then** it's selected for the
   service-configuration panel (User Story 3) without also being interpreted as a click on
   the containing box — this is new behavior this feature adds; today only the box as a whole
   is clickable/selectable.

---

### User Story 5 - Set duration, calculate, and see the price in one panel (Priority: P1)

A user sets the Calculate duration, triggers the calculation, and sees the resulting total
price, any warnings, and any unpriceable-item notices, all within one persistent panel at the
far right of the screen.

**Why this priority**: This is the tool's core value — a priced total — and the request
calls it out as its own panel rather than a toolbar control with results appearing
elsewhere on the page.

**Independent Test**: Set a duration, calculate, and verify the duration control, the
Calculate action, and the full result (total, warnings, unpriceable items) all appear
together in the far-right panel.

**Acceptance Scenarios**:

1. **Given** an Architecture is open, **When** the user looks at the far-right panel,
   **Then** they see the duration selector and the Calculate action together.
2. **Given** the user calculates a price, **When** the result returns, **Then** the total
   price, any warnings (e.g., unconnected VPCs), and any unpriceable-item notices all appear
   in that same far-right panel.

---

### User Story 6 - A single, consistent visual design across every panel (Priority: P2)

Every one of the five panels is built from the same design system — consistent buttons,
inputs, spacing, typography, and icons — so the screen reads as one cohesive application
rather than five differently-styled sections stitched together. This applies wherever it
cleanly can; code simplicity and maintainability take priority over forcing a design-system
component into a place it doesn't naturally fit.

**Why this priority**: Visual consistency is explicitly requested, but it's a refinement
layered on top of getting the five panels and their contents right first (User Stories
1-5); the layout has value even before the shared visual system is fully applied.

**Independent Test**: Compare buttons, inputs, and icons across all five panels — verify they
share the same look, spacing, and interaction style, and that common actions (add, remove,
connect, edit, search, calculate, warning) are reinforced with recognizable icons rather than
text alone.

**Acceptance Scenarios**:

1. **Given** the five-panel layout, **When** the user looks at controls in any panel (a
   button, an input, a select), **Then** they share the same visual style as the equivalent
   control in every other panel.
2. **Given** common actions across the panels (create, delete, connect, edit, search,
   calculate), **When** the user looks at the control for each, **Then** it's paired with an
   icon reinforcing its purpose, not text alone.
3. **Given** the architecture diagram's own node/edge rendering (governed by the existing
   React Flow canvas, not by the design system), **When** the user views it, **Then** it MAY
   keep its current styling rather than being forced into shadcn/ui components — the
   surrounding diagram panel's own chrome (borders, buttons, empty state) still follows the
   shared design system.

---

### Edge Cases

- What does a user see before any Architecture is selected? The collections/search, diagram,
  and pricing panels each show a clear empty/prompt state rather than appearing broken or
  blank; the service-configuration panel isn't shown at all (it collapses — Clarifications).
- What does a user see before any service is selected within an open Architecture (no
  Collection/Connector service clicked on the diagram, nothing picked from search)? The
  service-configuration panel isn't shown (collapsed); the collections/search panel still
  shows the selected Collection's/Connector's own name and search controls if one is selected.
- What happens if the user selects a second service while the service-configuration panel
  already shows one? The panel's contents are replaced by the newly selected service — it
  never shows more than one service at a time (Clarifications).
- What happens if the user deletes the currently-selected Architecture, Collection, or Data
  Connector? Every panel that depended on it resets to its appropriate empty/prompt state
  (or, for the service-configuration panel, collapses) rather than continuing to display
  stale data.
- What happens on a narrow browser window where five side-by-side panels don't comfortably
  fit? The layout is optimized for a desktop-width screen; graceful degradation (e.g.
  horizontal scrolling) is acceptable rather than a dedicated narrow-screen redesign.
- What happens with a very long provider or Architecture list? It scrolls within its own
  panel without displacing or resizing the other four panels.
- What happens to the create-new-Architecture control (FR-002) when column 1 is collapsed?
  It remains available as an icon, in its same below-the-list position, with its label shown
  on hover like every other collapsed-panel control.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The application MUST present cloud-provider selection, the selected provider's
  Architecture list, and the ability to create a new Architecture together in a single
  persistent panel that is one of five side-by-side panels on one screen — replacing
  today's separate landing page and Architecture page with a single, unified screen.
- **FR-002**: The control to create a new Architecture MUST appear below the list of existing
  Architectures for the selected provider, not above it.
- **FR-003**: The application MUST present Collection-creation controls, the Connect and
  Remove Connector actions, and the AWS-service search and results for the
  currently-selected Collection or Data Connector together in a single persistent panel,
  positioned immediately to the left of the architecture diagram.
- **FR-004**: Within that panel, the Collection-creation controls and the Connect/Remove
  Connector actions MUST remain visible at all times, regardless of how long the
  service-search results list below them is.
- **FR-005**: When a user clicks a service already present in a Collection's or VPC's box on
  the diagram, or picks one from search results to add, the application MUST show that
  service's identifying attributes and the pricing inputs it requires (term, purchase option,
  quantity where applicable) in a dedicated panel positioned between the panel from FR-003
  and the architecture diagram. The collections/search panel (FR-003) does NOT separately
  list a Collection's or Connector's already-added services — an already-added service is
  reachable only by clicking it on the diagram (Clarifications). For an already-added
  service, this panel MUST also provide the ability to remove that service selection
  entirely — the capability the now-dropped list's per-item Remove control provided (FR-008).
  A Data Connector has no "box" to click a listed service inside of (it has at most one
  attached service) — clicking the Connector itself (its edge on the diagram) is what selects
  its attached service, if any, into this panel, the same way clicking a listed service does
  for a Collection.
- **FR-006**: The assembled architecture diagram MUST occupy its own dedicated panel,
  positioned centrally among the five panels, with the panels from FR-003 and FR-005 to its
  left and the panel from FR-007 to its right.
- **FR-007**: The Calculate-duration selector, the Calculate action, and the resulting total
  price, warnings, and any unpriceable-item notices MUST all appear together in a single
  persistent panel at the far right of the screen.
- **FR-008**: Every capability available before this overhaul — creating/deleting an
  Architecture; creating/deleting a Collection; connecting/removing a Data Connector;
  searching, adding, editing, and removing a service selection; attaching a service to a Data
  Connector; calculating a price at a chosen duration — MUST remain fully available after it;
  this is a layout and visual change, not a functional one.
- **FR-009**: The application's visual design — buttons, inputs, panels, spacing, and
  typography — MUST be rebuilt on a single, consistent component design system (Tailwind CSS
  utility classes and shadcn/ui components) applied across all five panels, rather than each
  panel keeping its own ad hoc styling. This applies wherever a shadcn/ui component or
  Tailwind utility classes cleanly fit the control being built; where forcing one in would add
  complexity rather than reduce it (e.g., the architecture diagram's own node/edge rendering,
  which is governed by the existing React Flow canvas, not shadcn/ui), code simplicity and
  maintainability take priority over uniform library usage (see Assumptions).
- **FR-010**: Common actions and states (add, remove/delete, connect, edit, search,
  calculate, warning/error) MUST be reinforced with icons from a single consistent icon set
  (Lucide), not left as text-only controls, applying the same simplicity-first exception as
  FR-009 where an icon doesn't cleanly fit.
- **FR-011**: When no Architecture is selected, the collections/connectors/search panel, the
  diagram panel, and the duration/pricing panel MUST each show a clear empty/prompt state
  rather than appearing broken or blank.
- **FR-012**: The service-configuration panel MUST be shown only while a service is selected;
  it MUST collapse (occupy no visible space, rather than showing an empty state) whenever
  nothing is selected — whether because no Architecture is open, no service within an open
  Architecture is currently selected, or the previously-selected service was just removed
  (Clarifications).
- **FR-013**: Deleting the currently-selected Architecture, Collection, or Data Connector
  MUST reset every panel that depended on it to its appropriate empty/prompt state (or, for
  the service-configuration panel, collapse per FR-012), rather than continuing to display
  stale data.
- **FR-014**: Each individual service listed inside a Collection's or VPC's box on the
  diagram MUST be independently clickable to select it for the service-configuration panel,
  distinct from clicking the box to select its Collection as a whole. This is new diagram
  behavior this feature must add — today only the box as a whole is clickable/selectable, not
  the individual services listed inside it (Clarifications).
- **FR-015**: The service-configuration panel MUST display at most one service's attributes
  and pricing inputs at a time; selecting a different service (from the diagram or from
  search results) MUST replace the panel's contents rather than showing multiple services at
  once (Clarifications).
- **FR-016**: The provider/Architecture panel (FR-001) MUST be collapsible to a narrow,
  icon-only rail and expandable back to its full width, via two explicit icon controls at the
  top of the panel (Clarifications).
- **FR-017**: While the provider/Architecture panel is collapsed, each provider and each
  Architecture MUST be represented by a compact icon rather than its text label; hovering
  over an icon MUST reveal that provider's or Architecture's full name (e.g., via a tooltip).
  Every action available in the expanded state (selecting a provider, selecting an
  Architecture, creating a new one) MUST remain available, by icon, in the collapsed state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from choosing a cloud provider to viewing a fully assembled,
  priced Architecture without ever navigating to a different page or URL.
- **SC-002**: Every capability available in the application before this overhaul remains
  reachable after it, with zero loss of functionality.
- **SC-003**: A first-time user can correctly identify which of the five screen panels to
  use for a given task (choose an Architecture, manage collections/connectors/search,
  configure a selected service, view the diagram, see the price) without needing
  instructions.
- **SC-004**: All five panels of the screen share one consistent visual design (spacing,
  typography, color, icon style) rather than reading as five differently-styled sections —
  except the architecture diagram's own node/edge rendering, which may reasonably keep its
  existing styling where adopting the shared design system there would add complexity rather
  than reduce it.

## Assumptions

- The far-left panel (User Story 1) fully replaces today's separate landing page — selecting
  an Architecture there populates the other four panels for that Architecture without
  navigating to a different page or URL.
- The "fixed section" in the collections/connectors/search panel (User Story 2) is today's
  Collection-creation controls (type, name, Add Collection) and Connect/Remove Connector
  actions, which already sit at the top of today's Architecture page — they keep that
  relative position, now within this panel. Below them, this panel also shows the
  currently-selected Collection's or Data Connector's own name and delete control, plus the
  AWS-service search filters and results — but, per Clarifications, NOT a list of the
  Collection's/Connector's already-added services; that list is dropped, and an already-added
  service is reached only by clicking it on the diagram (User Story 3, FR-014).
- The service-configuration panel (User Story 3) applies uniformly whether the current
  selection is a service in a Collection or a service being attached to a Data Connector —
  both follow the same "attributes + pricing inputs" presentation. Since a Data Connector has
  no "box" on the diagram (it's an edge, not a node) and holds at most one attached service,
  clicking the Connector itself is what routes its already-attached service (if any) into
  this panel — there's no separate per-service click target to add for Connectors the way
  FR-014 adds one for services listed inside a Collection's/VPC's box.
- Making individual services independently clickable within a diagram box (FR-014) is a new
  interaction this feature adds to the existing canvas — today (per 002-006) only the box
  itself (representing the whole Collection) is a click/selection target. This is a real,
  non-trivial new capability, not a pure relocation, called out explicitly rather than left
  implicit, since it's the only place this overhaul adds new interactive behavior rather than
  just repositioning existing behavior.
- The pricing panel's "calculated price" (User Story 5) includes the complete existing
  calculation result — total price, warnings, and unpriceable-item notices — not just the
  headline number.
- Tailwind CSS, shadcn/ui, and Lucide icons are the specific technology requested for the
  shared visual design system (FR-009, FR-010); which shadcn/ui components map to which
  existing controls is a planning-level decision, not specified here.
- Adopting Tailwind/shadcn/ui/Lucide is not an unconditional, every-single-control mandate:
  code simplicity and maintainability take priority over forcing package usage where it
  doesn't cleanly fit. The clearest such case is the architecture diagram's own node/edge
  rendering, which is built on the existing React Flow canvas (002-006) — its internals are
  not required to be rebuilt in shadcn/ui, though the panel chrome around it (border, empty
  state, any buttons) does follow the shared design system like every other panel. Other such
  exceptions, if any turn out to be needed, are a planning/implementation-level judgment call
  guided by this same priority, not enumerated exhaustively here.
- This is a layout and visual-design-system change only — the pricing calculation logic,
  data model, and API behavior established in features 001-006 are unchanged.
- No dedicated narrow-screen/mobile layout is required for this feature; the five-panel
  layout is optimized for a desktop-width screen, consistent with this tool's existing usage
  pattern.
- The far-left provider/Architecture panel is always visible (never fully hidden) but is
  collapsible to a narrow icon rail (Clarifications, FR-016/FR-017); it is not required to be
  arbitrarily resizable (e.g., drag-to-resize to any width) — only the two-state
  expanded/collapsed toggle is in scope for this feature.
- Which specific icon represents each cloud provider, and how an Architecture (an arbitrary
  user-given name with no inherent icon) is represented as a compact icon when collapsed, are
  planning-level visual decisions, not specified here — the requirement is only that each is
  a recognizable, hoverable, clickable icon-sized control.

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

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose a provider and Architecture from one persistent panel (Priority: P1)

A user opens the application and, in a single always-visible panel on the far left, picks a
cloud provider, sees that provider's list of Architectures, and creates a new Architecture —
all without leaving the screen they're working in.

**Why this priority**: This is the entry point to everything else; today it's a separate
page the user has to leave. Making it a persistent panel is the foundational structural
change the rest of the overhaul builds on.

**Independent Test**: Load the application, switch providers, create a new Architecture, and
select an existing one — verify all of this happens in the same, single screen region with
no page navigation.

**Acceptance Scenarios**:

1. **Given** the application is open, **When** the user looks at the far-left region,
   **Then** they see the list of cloud providers above the list of Architectures for
   whichever provider is currently selected.
2. **Given** an Architecture list for the selected provider, **When** the user looks for how
   to create a new one, **Then** the create-new-Architecture control appears below the list,
   not above it.
3. **Given** the user selects a different Architecture from the list, **When** the selection
   changes, **Then** the other four regions of the screen update to reflect the newly
   selected Architecture, with no page reload or URL-driven navigation required to see it.

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
   panel, **Then** they see that item's own details (name, its existing service selections,
   and the ability to search for and select AWS services for it).

---

### User Story 3 - Configure a selected service in its own panel (Priority: P1)

When a user selects a service — either one already placed in a Collection or Data Connector,
or one just chosen from the search results to add — the service's identifying attributes and
the pricing inputs it requires appear together in a dedicated panel positioned between the
collections/search panel and the architecture diagram.

**Why this priority**: This is called out as its own distinct region in the request; today
this information is buried inline within the search results, making it easy to miss which
attributes belong to which action.

**Independent Test**: Select a service from the diagram, then separately pick a new service
from search results — verify both cases populate the same dedicated panel with that
service's attributes and required pricing inputs.

**Acceptance Scenarios**:

1. **Given** a service already placed in a Collection is selected (e.g., from the diagram),
   **When** the user looks at this panel, **Then** it shows that service's identifying
   attributes and its current pricing inputs.
2. **Given** a service is picked from the search results to add to the selected Collection or
   Connector, **When** the user looks at this panel, **Then** it shows that service's
   identifying attributes and the pricing inputs needed before it can be added.
3. **Given** nothing is currently selected for configuration, **When** the user looks at this
   panel, **Then** it shows a clear empty state rather than appearing blank or broken.

---

### User Story 4 - View the assembled architecture in its own panel (Priority: P1)

A user sees the assembled architecture diagram in its own dedicated, appropriately sized
region at the center of the screen, with the collection/search and service-configuration
panels to its left and the pricing panel to its right.

**Why this priority**: The diagram is the primary visual output of the tool; giving it a
clearly bounded central region (rather than a fixed-height strip surrounded by unrelated
controls) is core to the requested layout.

**Independent Test**: Open an Architecture with several Collections and Connectors — verify
the diagram renders in its own bounded region, positioned between the two left-hand panels
and the right-hand pricing panel.

**Acceptance Scenarios**:

1. **Given** an Architecture with Collections, nested Collections, and Data Connectors,
   **When** the user views the screen, **Then** the diagram appears in a single dedicated
   region at the center, distinct from the panels beside it.
2. **Given** the diagram region, **When** the user interacts with it (pan, zoom, select,
   drag, resize — the existing canvas interactions), **Then** every interaction continues to
   work exactly as it does today.

---

### User Story 5 - Set duration, calculate, and see the price in one panel (Priority: P1)

A user sets the Calculate duration, triggers the calculation, and sees the resulting total
price, any warnings, and any unpriceable-item notices, all within one persistent panel at the
far right of the screen.

**Why this priority**: This is the tool's core value — a priced total — and the request
calls it out as its own region rather than a toolbar control with results appearing
elsewhere on the page.

**Independent Test**: Set a duration, calculate, and verify the duration control, the
Calculate action, and the full result (total, warnings, unpriceable items) all appear
together in the far-right region.

**Acceptance Scenarios**:

1. **Given** an Architecture is open, **When** the user looks at the far-right region,
   **Then** they see the duration selector and the Calculate action together.
2. **Given** the user calculates a price, **When** the result returns, **Then** the total
   price, any warnings (e.g., unconnected VPCs), and any unpriceable-item notices all appear
   in that same far-right region.

---

### User Story 6 - A single, consistent visual design across every panel (Priority: P2)

Every one of the five panels is built from the same design system — consistent buttons,
inputs, spacing, typography, and icons — so the screen reads as one cohesive application
rather than five differently-styled sections stitched together.

**Why this priority**: Visual consistency is explicitly requested, but it's a refinement
layered on top of getting the five regions and their contents right first (User Stories
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

---

### Edge Cases

- What does a user see before any Architecture is selected? The four panels that depend on
  one (collections/search, service configuration, diagram, pricing) show a clear empty/prompt
  state rather than appearing broken or blank.
- What does a user see before any Collection or Data Connector is selected within an open
  Architecture? The service-configuration panel shows a clear empty/prompt state.
- What happens if the user deletes the currently-selected Architecture, Collection, or Data
  Connector? Every panel that depended on it resets to its appropriate empty/prompt state
  rather than continuing to display stale data.
- What happens on a narrow browser window where five side-by-side panels don't comfortably
  fit? The layout is optimized for a desktop-width screen; graceful degradation (e.g.
  horizontal scrolling) is acceptable rather than a dedicated narrow-screen redesign.
- What happens with a very long provider or Architecture list? It scrolls within its own
  panel without displacing or resizing the other four panels.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The application MUST present cloud-provider selection, the selected provider's
  Architecture list, and the ability to create a new Architecture together in a single
  persistent panel that is one of five side-by-side regions on one screen — replacing
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
- **FR-005**: When a user selects a service already present in the diagram, or picks one from
  search results to add, the application MUST show that service's identifying attributes and
  the pricing inputs it requires (term, purchase option, quantity where applicable) in a
  dedicated panel positioned between the panel from FR-003 and the architecture diagram.
- **FR-006**: The assembled architecture diagram MUST occupy its own dedicated panel,
  positioned centrally among the five regions, with the panels from FR-003 and FR-005 to its
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
  typography — MUST be rebuilt on a single, consistent component design system applied across
  all five regions, rather than each region keeping its own ad hoc styling.
- **FR-010**: Common actions and states (add, remove/delete, connect, edit, search,
  calculate, warning/error) MUST be reinforced with icons from a single consistent icon set,
  not left as text-only controls.
- **FR-011**: When no Architecture is selected, the four panels that depend on one
  (collections/connectors/search, service configuration, diagram, duration/pricing) MUST show
  a clear empty/prompt state rather than appearing broken or blank.
- **FR-012**: When no Collection or Data Connector is selected within an open Architecture,
  the service-configuration panel MUST show a clear empty/prompt state.
- **FR-013**: Deleting the currently-selected Architecture, Collection, or Data Connector
  MUST reset every panel that depended on it to its appropriate empty/prompt state, rather
  than continuing to display stale data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from choosing a cloud provider to viewing a fully assembled,
  priced Architecture without ever navigating to a different page or URL.
- **SC-002**: Every capability available in the application before this overhaul remains
  reachable after it, with zero loss of functionality.
- **SC-003**: A first-time user can correctly identify which of the five screen regions to
  use for a given task (choose an Architecture, manage collections/connectors/search,
  configure a selected service, view the diagram, see the price) without needing
  instructions.
- **SC-004**: All five regions of the screen share one consistent visual design (spacing,
  typography, color, icon style) rather than reading as five differently-styled sections.

## Assumptions

- The far-left panel (User Story 1) fully replaces today's separate landing page — selecting
  an Architecture there populates the other four panels for that Architecture without
  navigating to a different page or URL.
- The "fixed section" in the collections/connectors/search panel (User Story 2) is today's
  Collection-creation controls (type, name, Add Collection) and Connect/Remove Connector
  actions, which already sit at the top of today's Architecture page — they keep that
  relative position, now within this panel. Below them, this panel also shows the
  currently-selected Collection's or Data Connector's own details (name, delete control, its
  existing service selections) in addition to the AWS-service search filters and results —
  everything that renders below the diagram today, except the identifying-attributes/pricing-
  inputs portion, which moves to the service-configuration panel (User Story 3).
- The service-configuration panel (User Story 3) applies uniformly whether the current
  selection is a service in a Collection or a service being attached to a Data Connector —
  both follow the same "attributes + pricing inputs" presentation.
- The pricing panel's "calculated price" (User Story 5) includes the complete existing
  calculation result — total price, warnings, and unpriceable-item notices — not just the
  headline number.
- Tailwind CSS, shadcn/ui, and Lucide icons are the specific technology requested for the
  shared visual design system (FR-009, FR-010); which shadcn/ui components map to which
  existing controls is a planning-level decision, not specified here.
- This is a layout and visual-design-system change only — the pricing calculation logic,
  data model, and API behavior established in features 001-006 are unchanged.
- No dedicated narrow-screen/mobile layout is required for this feature; the five-panel
  layout is optimized for a desktop-width screen, consistent with this tool's existing usage
  pattern.
- The far-left provider/Architecture panel is always visible; it is not required to be
  collapsible or resizable for this feature.

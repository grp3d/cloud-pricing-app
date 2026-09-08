# Feature Specification: Service Selection Improvements

**Feature Branch**: `003-service-selection-improvements`

**Created**: 2026-09-08

**Status**: Draft

**Input**: User description: "service selection improvements: (1) show additional information to the user for services so they know what they are selecting (2) qty fields on services have no units (3) in the architecture window, need the ability to resize application component and vpc windows (4) application components in the arch diagram should show the services they include and resize accordingly"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See what a service actually is before selecting it (Priority: P1)

While searching the AWS catalog to add a service to a Collection or a Data Connector, a user
sees enough descriptive detail about each candidate — and about the one they're about to
confirm — to know what they're actually choosing, not just a service name and a single
ambiguous summary line.

**Why this priority**: Choosing the wrong SKU by mistake (e.g., picking the wrong instance size
or a similarly-named variant) undermines the accuracy of the whole tool — this is a trust and
correctness issue, not just cosmetic polish.

**Independent Test**: Search the catalog for a service family with several similar-looking
results (e.g., multiple EC2 instance types), and verify each result — and the one currently
selected, before confirming — shows distinguishing descriptive detail beyond its name and a
single summary line.

**Acceptance Scenarios**:

1. **Given** a catalog search returns multiple results, **When** the user views the results
   list, **Then** each result shows enough descriptive detail to tell it apart from similar
   results, not just a service name and one summary line.
2. **Given** a user has picked a specific SKU and is about to enter its pricing inputs,
   **When** they view the confirmation step, **Then** they see that SKU's available descriptive
   details before entering any pricing input.
3. **Given** a SKU has little or no descriptive detail available in the catalog data,
   **When** a user views it, **Then** the system shows a clear "no additional details
   available" state rather than a blank or broken display.

---

### User Story 2 - Know the unit a quantity is measured in (Priority: P1)

When a user enters a usage quantity for a SKU's pricing inputs, they see the specific unit that
quantity is measured in for that SKU (for example, hours, GB-months, or requests), instead of
an unlabeled number field.

**Why this priority**: A usage quantity is meaningless — and can produce a wrong price — without
knowing its unit; this is the same trust/correctness category as User Story 1 and is small and
self-contained enough to ship independently.

**Independent Test**: Select a SKU, open its pricing inputs, and verify the usage quantity
field displays that SKU's actual billing unit rather than being unlabeled.

**Acceptance Scenarios**:

1. **Given** a user has selected a SKU and is entering its pricing inputs, **When** they view
   the usage quantity field, **Then** the unit that quantity is measured in is shown alongside
   it.
2. **Given** two different SKUs bill in different units (e.g., one hourly, one by data volume),
   **When** a user enters pricing inputs for each, **Then** each shows its own correct unit, not
   a shared generic label.
3. **Given** a SKU already added to a Collection is being edited, **When** the user views its
   existing pricing inputs, **Then** the unit is shown there too, not only when first adding it.

---

### User Story 3 - Application Components show what they contain (Priority: P2)

On the assembly canvas, an Application Component's box shows the AWS services it currently
contains, and grows or shrinks automatically as services are added to or removed from it — so
the diagram reflects what's actually inside each component without the user having to click
into it to check.

**Why this priority**: This makes the diagram itself an accurate, at-a-glance representation of
the architecture being built — valuable on its own, and independent of the resize capability in
User Story 4 (an Application Component with zero manual resizing already needs to display and
auto-fit its contents correctly).

**Independent Test**: Add several AWS services to an Application Component and verify its box
on the canvas lists them and grows to fit; remove one and verify the box shrinks back down.

**Acceptance Scenarios**:

1. **Given** an Application Component has one or more AWS services added to it, **When** the
   user views the canvas, **Then** that component's box shows those services.
2. **Given** a user adds another service to an Application Component, **When** the canvas
   updates, **Then** the component's box grows to also show the new service without hiding the
   ones already shown.
3. **Given** a user removes a service from an Application Component, **When** the canvas
   updates, **Then** the component's box shrinks back down to fit its remaining contents.
4. **Given** an Application Component has no services yet, **When** the user views the canvas,
   **Then** the box shows a clear empty state at a small default size, not an oversized empty
   box.

---

### User Story 4 - Manually resize Component and VPC boxes (Priority: P3)

On the assembly canvas, a user can manually resize a VPC's box or an Application Component's
box by dragging, independent of whatever size the box would otherwise be sized to.

**Why this priority**: A convenience and readability improvement layered on top of the other
three — useful once the canvas has real content to arrange (User Stories 1-3), but not required
to prove the core selection/labeling/auto-fit value on its own.

**Independent Test**: On the canvas, drag a VPC box's resize handle and verify it changes size;
do the same for an Application Component box.

**Acceptance Scenarios**:

1. **Given** a VPC box on the canvas, **When** the user drags its resize handle, **Then** the
   box's size changes to match.
2. **Given** an Application Component box on the canvas, **When** the user drags its resize
   handle, **Then** the box's size changes to match.
3. **Given** a user manually resizes a VPC box, **When** they later add or remove a nested
   Application Component, **Then** the VPC box remains at least large enough to show its nested
   contents (it does not shrink below what's needed to display what's inside it).

---

### Edge Cases

- What happens when a SKU has little or no descriptive detail in the underlying catalog data
  (some AWS SKUs have sparse attributes)? The system shows a clear "no additional details
  available" state rather than leaving a blank or broken-looking display (User Story 1).
- What happens when a user resizes an Application Component or VPC box smaller than its current
  contents need? Contents remain reachable (e.g., scrollable within the box) rather than
  silently overflowing unreadably or disappearing.
- Does a manual resize survive reloading the page? No — per this feature's Assumptions, box
  sizing (whether auto-fit or manually resized) is not saved; it's recomputed fresh each time
  the Architecture is loaded, consistent with how box position already works today.
- What happens when an Application Component that was manually resized smaller than its content
  needs has a new service added to it? The box grows to fit the new content, superseding the
  prior manual size for the current view — resizing is a per-session convenience, not a fixed
  override that could otherwise hide newly-added services from view.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Catalog search results MUST show enough descriptive detail per SKU that a user
  can distinguish it from other, similarly-named results without selecting it first.
- **FR-002**: When a user has picked a specific SKU and is about to enter its pricing inputs,
  the system MUST display that SKU's available descriptive details as part of that step.
- **FR-003**: When a SKU has no meaningful descriptive detail available, the system MUST show a
  clear indication of that rather than an empty or broken-looking display.
- **FR-004**: When a user is entering or viewing a usage quantity for a SKU's pricing inputs,
  the system MUST display the specific unit that quantity is measured in for that SKU.
- **FR-005**: The unit shown for a usage quantity MUST reflect that specific SKU's actual
  billing unit, not a generic or placeholder label.
- **FR-006**: An Application Component's representation on the assembly canvas MUST display the
  AWS services currently contained within it.
- **FR-007**: An Application Component's representation on the assembly canvas MUST
  automatically resize to fit the number of services it currently contains, growing as services
  are added and shrinking as they are removed.
- **FR-008**: An Application Component with no services yet MUST display a clear empty state at
  a small default size rather than an oversized empty box.
- **FR-009**: Users MUST be able to manually resize a VPC's representation on the assembly
  canvas.
- **FR-010**: Users MUST be able to manually resize an Application Component's representation on
  the assembly canvas.
- **FR-011**: A VPC's representation MUST NOT be resizable below the minimum size needed to
  display its currently nested Application Components.

### Key Entities

- **AWS Pricing Catalog** *(existing entity, extended — see
  `001-assemble-price-aws-architecture`)*: Read-only vendor pricing data. This feature extends
  what's read and shown from it per SKU — its descriptive attributes (User Story 1) and its
  billing unit (User Story 2) — without changing what it is or how it's sourced.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given two or more similarly-named search results, a user can identify what
  distinguishes them without leaving the app to consult outside documentation.
- **SC-002**: For every SKU a user can select, the unit for its usage-quantity input is visible
  at the moment they enter that value — never an unlabeled number field.
- **SC-003**: An Application Component's box on the canvas always reflects its current contents
  without requiring a manual refresh or re-selection to update.
- **SC-004**: A user can resize a VPC or Application Component box in a single drag gesture.

## Assumptions

- Box sizing on the assembly canvas — whether automatically fit to content (User Story 3) or
  manually resized (User Story 4) — is not persisted. It's recomputed each time the Architecture
  loads, consistent with how node position on the canvas already behaves (established in
  `001-assemble-price-aws-architecture` / `002-vpc-component-nesting`).
- This feature does not add price information to catalog search results — showing a SKU's price
  before it's added is a separate concern from showing its descriptive detail, and pricing
  itself is already surfaced once a SKU is added and its pricing inputs are entered.
- A VPC's own directly-added AWS services (as opposed to its nested Application Components) are
  out of scope for the "shows contained services" behavior in User Story 3 — that story is
  scoped to Application Components specifically, matching what was requested.
- Manually resizing a box is a per-session, per-view convenience — it takes effect immediately
  but yields to auto-fit sizing (User Story 3) the next time that box's content changes, rather
  than acting as a fixed override that could hide newly-added content from view.

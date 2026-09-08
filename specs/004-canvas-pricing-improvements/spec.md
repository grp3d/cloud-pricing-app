# Feature Specification: Canvas & Pricing Improvements

**Feature Branch**: `004-canvas-pricing-improvements`

**Created**: 2026-09-08

**Status**: Draft

**Input**: User description: "Assembly canvas and pricing improvements: (1) Duration-based price
normalization with a 1 day/1 month/1 year selector and proration by pricing term, (2) richer
service attributes shown in the diagram, (3) cascading multi-level box resize plus VPC boxes
showing their own directly-attached services, (4) select-two-boxes connector create/remove UX
(and fixing the current inability to draw connectors by dragging), (5) unpriceable/excluded-SKU
warnings naming their containing component(s)."

## Clarifications

### Session 2026-09-08

- Q: When every service in an Architecture ends up excluded from a duration-scoped total (all
  unpriceable or all duration-unrecognized), should the total display as $0, or a distinct
  empty/"nothing could be calculated" state? → A: Show $0.00 as the total, with every excluded
  service still listed individually in the warnings (per FR-005/FR-012) — the $0 is technically
  correct ("nothing priceable was included") and the warnings list makes clear why.
- Q: Should the "Connect" / "Remove Connector" actions disappear entirely when inactive, or stay
  visible but disabled? → A: Always visible, disabled (grayed out, unclickable) when the current
  selection doesn't satisfy the condition — the same pattern "Add Collection" already uses
  (disabled until a name is typed).
- Q: Should duration-unrecognized exclusions (FR-005) share the same warnings list as today's
  unpriceable-SKU warnings, or appear in a visually separate list? → A: One combined list — every
  excluded/unpriceable service appears together, each with its own reason text (e.g., "no price
  for term/purchase_option" vs. "billing unit 'X' isn't recognized as time-based") and its
  containing component(s) per FR-012.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See a trustworthy total for a specific timeframe (Priority: P1)

A user wants to know what an Architecture costs for a specific period — a day, a month, or a
year — and trusts that every dollar in that total genuinely reflects that period, whether the
underlying service is billed on-demand, under a multi-year commitment, or by the month.

**Why this priority**: Today, the total mixes together services billed under completely
different timeframes (an hourly on-demand rate vs. a full year's reserved commitment) with no
way to express "the cost of this architecture for 1 month" — the total's meaning is ambiguous.
This is the same trust/correctness category as the pricing work already done in
`003-service-selection-improvements`.

**Independent Test**: Build an Architecture mixing an on-demand service and a 1-year reserved
service, calculate at each of the three durations, and verify the total changes accordingly —
the reserved service's contribution shrinks toward a day's share of its full-year cost, while an
unrelated per-request or per-GB-month service scales the way its own billing unit implies.

**Acceptance Scenarios**:

1. **Given** an Architecture with services on various pricing terms, **When** the user selects a
   calculation duration (1 day, 1 month, or 1 year) and calculates, **Then** the total reflects
   the cost of running that Architecture for exactly that duration.
2. **Given** a service under a 1-year Reserved commitment, **When** the user selects 1 day,
   **Then** that service's contribution is its full committed-term cost divided down to a single
   day's share (and multiplied back up proportionally for 1 month or the full year).
3. **Given** an on-demand service billed per hour, per minute, or per request (units with no
   inherent time period), **When** the user selects a duration, **Then** its contribution is the
   entered quantity treated as a steady daily rate, scaled to the selected duration.
4. **Given** an on-demand service billed by an already-period-denominated unit (e.g., per
   GB-month), **When** the user selects a duration, **Then** its contribution is scaled between
   that unit's own period and the selected duration, not treated as a daily rate.
5. **Given** a service whose billing unit isn't recognized as either "no inherent period" or
   "already a fixed period," **When** the user calculates, **Then** that service's cost is
   excluded from the total and listed separately with a clear reason, never included unscaled or
   guessed.

---

### User Story 2 - Reliable connector creation and removal (Priority: P1)

A user can dependably create a Data Connector between two components on the canvas, and remove
one, without the interaction silently failing.

**Why this priority**: Connectors are core to representing how parts of an architecture relate;
right now it isn't possible to draw one at all, which blocks a basic capability of the tool.

**Independent Test**: Select exactly two boxes on the canvas, confirm a connector is created
between them; select an existing connector and confirm it can be removed; verify dragging
between two boxes also creates a connector.

**Acceptance Scenarios**:

1. **Given** exactly two boxes are selected on the canvas, **When** the user views the canvas
   controls, **Then** the "Connect" action is enabled; **When** they confirm it, **Then** a Data
   Connector is created between the two selected boxes.
2. **Given** zero, one, or more than two boxes are selected, **When** the user views the canvas
   controls, **Then** the "Connect" action is visible but disabled.
3. **Given** an existing connector is selected on the canvas, **When** the user views the canvas
   controls, **Then** the "Remove Connector" action is enabled and, when confirmed, removes it;
   **When** no connector is selected, **Then** that action is visible but disabled.
4. **Given** two boxes on the canvas, **When** the user drags from one to the other, **Then** a
   Data Connector is created between them (restoring today's non-functional behavior — see Edge
   Cases).

---

### User Story 3 - Trace a warning or exclusion back to its component(s) (Priority: P1)

When a service can't be included in a calculated total — whether because no price exists for it
or because its billing unit couldn't be scaled to the selected duration — the message names the
Architecture component(s) that contain it, so the user can find and fix it directly.

**Why this priority**: Without this, finding the actual source of a warning means manually
inspecting every component in the Architecture one at a time — a real, demonstrated pain point.

**Independent Test**: Trigger both an unpriceable-SKU warning and a duration-exclusion warning
(User Story 1) on services placed in different components, and verify each message names the
specific component(s) containing that service.

**Acceptance Scenarios**:

1. **Given** a service attached to a Collection can't be priced, **When** the user views the
   warning, **Then** it names that Collection.
2. **Given** a service attached to a Data Connector can't be priced, **When** the user views the
   warning, **Then** it identifies the connector (e.g., by the two Collections it connects),
   since a connector has no name of its own.
3. **Given** a service is excluded from a duration-scoped total per User Story 1's Acceptance
   Scenario 5, **When** the user views that exclusion, **Then** it likewise names the
   component(s) containing that service.

---

### User Story 4 - See identifying details for services shown in the diagram (Priority: P2)

Each service listed inside a component's box on the canvas shows a short identifying detail —
not just its service code and SKU — so similar services can be told apart directly on the
diagram.

**Why this priority**: A readability improvement on top of the identification work already done
in `003-service-selection-improvements` for the search/confirmation flow; valuable but not
blocking core functionality.

**Independent Test**: Add two similar services (e.g., different EC2 instance types) to a
component and verify the canvas box shows a distinguishing detail for each without opening
either one.

**Acceptance Scenarios**:

1. **Given** a component contains one or more services, **When** the user views its box on the
   canvas, **Then** each listed service shows a short identifying detail alongside its service
   code and SKU.

---

### User Story 5 - Boxes always show their full content (Priority: P2)

A VPC's box shows the AWS services attached directly to it, not just its nested Application
Components, and every box on the canvas — at every level of nesting — resizes as needed so its
content is never clipped, with that growth cascading up through however many boxes contain it.

**Why this priority**: A visual-correctness improvement building on `003`'s auto-fit and nesting
work; valuable for an accurate diagram but not a blocking defect the way User Stories 1-3 are.

**Independent Test**: Attach a service directly to a VPC and verify its box shows it; nest a
component inside another nested component structure, grow its content, and verify every
containing box grows to keep fully showing it.

**Acceptance Scenarios**:

1. **Given** a VPC has AWS services attached directly to it, **When** the user views its box on
   the canvas, **Then** those services are shown, the same way an Application Component shows
   its own contained services.
2. **Given** a box is nested inside another box, **When** the inner box's content grows, **Then**
   the outer box also grows as needed to keep fully containing it.
3. **Given** multiple levels of nesting exist, **When** a box at the innermost level grows,
   **Then** every box containing it — at every level — grows in turn.
4. **Given** services are added to or removed from any box, **When** the canvas updates,
   **Then** that box's size always fits its current content without clipping its text.

---

### Edge Cases

- What happens when a Reserved-term service's billing unit isn't the usual per-hour rate? The
  full-committed-term treatment (User Story 1, Acceptance Scenario 2) is based on the commitment
  term itself, not the underlying unit, so it applies the same way regardless.
- What happens when a user selects three or more boxes, or a box and a connector together? The
  "Connect" action stays visible but disabled unless exactly two boxes are selected; selecting a
  connector continues to clear any selected box (and vice versa), as it already does today.
- What happens when a box's containing ancestor was previously resized smaller by hand, and then
  new content is added deeper inside it? The ancestor still grows to keep fully showing its
  content — auto-fit supersedes a prior manual size on content change, the same rule
  `003-service-selection-improvements` already established, now cascading through every level of
  nesting rather than just one.
- What happens when an Architecture mixes Reserved and On-Demand services at different billing
  granularities? Each service's contribution is computed independently under its own rule (User
  Story 1's Acceptance Scenarios 2-5) and summed — there's no single assumption applied
  architecture-wide beyond the one selected duration.
- Does the selected calculation duration get saved with the Architecture? No — it's a
  per-calculation choice, not persisted, consistent with how canvas box position and sizing
  already aren't saved (established in `001`/`002`/`003`).
- What happens when every service in an Architecture is excluded from the total (all
  unpriceable, all duration-unrecognized, or both)? The total still shows $0.00 rather than a
  distinct empty state — it's technically correct given nothing priceable was included — and
  every excluded service is still individually listed in the warnings (FR-005, FR-012), so the
  reason is never hidden behind a bare zero.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a duration selector (1 day / 1 month / 1 year) alongside
  the calculate action, applying to the whole Architecture's calculated total.
- **FR-002**: For a service priced under a Reserved commitment (1-year or 3-year), the system
  MUST treat its computed cost as covering the full commitment period, and scale it to the
  selected duration proportionally (e.g., a 1-year commitment's cost divided by 365 days and
  multiplied by the selected duration's day-count).
- **FR-003**: For a service priced On-Demand with a billing unit that has no inherent time
  period (e.g., per-hour, per-minute, per-request), the system MUST treat the entered usage
  quantity as a steady daily rate and scale its cost by the number of days in the selected
  duration.
- **FR-004**: For a service priced On-Demand with a billing unit that already represents a fixed
  period (e.g., per-GB-per-month), the system MUST scale its cost proportionally between that
  unit's own period and the selected duration, rather than treating the entered quantity as a
  daily rate.
- **FR-005**: When a service's billing unit cannot be classified into a recognized time-period
  category, the system MUST exclude that service's cost from the calculated total and list it,
  alongside any unpriceable services, with a reason specific to the exclusion (distinct from "no
  price for term/purchase_option"), rather than including an unscaled or guessed contribution.
- **FR-006**: The system MUST use consistent day-counts for every duration-based calculation: 1
  day = 1 day, 1 month = 31 days, 1 year = 365 days.
- **FR-007**: Wherever a usage quantity is entered or shown, the system MUST make clear whether
  it represents a per-day estimate (FR-003) or the service's own already-period-denominated
  quantity (FR-004, or a Reserved commitment), so users enter values with the correct assumption
  in mind.
- **FR-008**: Users MUST be able to create a Data Connector between two Collections by selecting
  exactly two boxes on the canvas and confirming via a dedicated, always-visible action.
- **FR-009**: The action to create a connector MUST be enabled only when exactly two boxes are
  currently selected, and disabled (visible but unclickable) when zero, one, or more than two
  boxes are selected.
- **FR-010**: Users MUST be able to remove a Data Connector by selecting it on the canvas and
  confirming via a dedicated, always-visible action, enabled only when a connector is currently
  selected and disabled otherwise.
- **FR-011**: Users MUST also be able to create a connector by dragging from one box to another
  directly on the canvas, in addition to the select-and-confirm method in FR-008.
- **FR-012**: When a service can't be included in the calculated total for any reason
  (unpriceable, or excluded per FR-005), it MUST appear in one combined warnings list — not a
  separate list per reason — and that message MUST name the Architecture component(s) —
  Application Component(s) or VPC(s) — that contain that service.
- **FR-013**: For a service attached to a Data Connector rather than a Collection, the message in
  FR-012 MUST identify the connector (e.g., by naming the two Collections it connects), since a
  connector has no name of its own.
- **FR-014**: An Application Component's or VPC's box on the canvas MUST show a short identifying
  detail (e.g., instance type, size) for each service it displays, not just that service's code
  and SKU identifier.
- **FR-015**: A VPC's box on the canvas MUST show the AWS services attached directly to it, in
  addition to the nested Application Components it already shows.
- **FR-016**: When a box's content grows and that box is itself nested inside another box, every
  containing box MUST also resize as needed to keep fully showing the box nested within it,
  however many levels deep the nesting goes.
- **FR-017**: A box's size MUST always be sufficient to show its current content without clipping
  its text, whenever services are added to or removed from it or from anything nested within it.

### Key Entities

- **Calculation Duration**: The period (1 day / 1 month / 1 year) a user selects when
  calculating an Architecture's total. Not a stored entity — a per-calculation choice applied at
  calculate time (see Edge Cases).
- **AWS Pricing Catalog** *(existing entity, extended read shape only — see `001`, `003`)*: this
  feature adds a classification of each SKU's billing unit into "no inherent period" (FR-003),
  "already a fixed period" (FR-004), or "unrecognized" (FR-005), used only to compute
  duration-scaled cost — it doesn't change what the catalog itself is or how it's sourced.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can see an Architecture's total cost for 1 day, 1 month, or 1 year by
  choosing from the duration selector, without re-entering any service's pricing inputs.
- **SC-002**: Every dollar included in a duration-scoped total genuinely reflects that duration
  for its service — no service's contribution is included unscaled or guessed.
- **SC-003**: When a service is excluded from a total for any reason, a user can identify which
  component(s) contain it directly from the message shown, without searching the Architecture.
- **SC-004**: A user can create a connector between two chosen components, and remove an existing
  one, using a single confirming action after selecting them.
- **SC-005**: A user can distinguish similar services shown in the same box by their identifying
  details without opening each one individually.
- **SC-006**: A box on the canvas, and everything containing it, always fully shows its current
  content with no text cut off, regardless of how many levels of nesting are involved.

## Assumptions

- Reserved-term commitments (1-year, 3-year) always use their full term length (365 / 1095 days)
  as the reference period for proration, regardless of the underlying billing unit label — the
  commitment period, not the unit, governs scaling for these (FR-002).
- The "no inherent period" and "already a fixed period" unit categories (FR-003, FR-004) are
  built from the common AWS billing-unit label variants actually observed in the pricing data
  (hour/minute/request-style labels for the former; month/GB-month-style labels for the latter).
  A billing unit outside these recognized variants is excluded per FR-005 rather than guessed;
  the recognized set is expected to grow over time as new variants are encountered.
- Custom or manually-overridden pricing for services whose real billing shape doesn't fit the
  recognized categories is explicitly out of scope for this feature and left for a future
  increment.
- This feature does not introduce new nesting capabilities (e.g., an Application Component
  nested inside another Application Component, or a VPC nested inside anything) — the cascading
  resize behavior in User Story 5 is built to handle however many levels of nesting exist today
  or are enabled by a future feature, without itself expanding what nesting relationships are
  allowed.
- Both the drag-to-connect interaction (FR-011) and the select-two-then-Connect action (FR-008)
  are expected to coexist as two ways to create a connector, rather than one replacing the other.
- The existing usage-quantity input's default value is unchanged by this feature (see Edge Cases
  discussion during clarification) — only its labeling changes per FR-007 to clarify what the
  entered value is assumed to represent.

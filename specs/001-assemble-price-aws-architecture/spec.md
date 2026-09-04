# Feature Specification: AWS Architecture Assembly & Pricing

**Feature Branch**: `001-assemble-price-aws-architecture`

**Created**: 2026-09-03

**Status**: Draft

**Input**: User description: "Assemble and price an AWS Architecture: create a reusable Architecture, group AWS SKUs into Application Component / VPC Collections, connect Collections with Data Connectors, enter pricing inputs, and calculate a total price."

## Clarifications

### Session 2026-09-03

- Q: What defines a distinct "user" for data isolation in the v1 placeholder identity model — does everyone share one global set of Architectures, or does each user get an isolated set? → A: Architectures MUST be linked to a real, distinct user identity from v1 (not anonymous, not globally shared). The long-term goal is that a user can also mark an Architecture as global, browse other users' global Architectures, price one, and clone one as a starting point for their own — but those global/clone capabilities are explicitly deferred to a later feature. Only per-user ownership is required now; the specific login/identification mechanism is a planning-level decision.
- Q: If the AWS pricing data source itself is temporarily unreachable or errors out (not just a missing price for one SKU), what should the user see? → A: A clear, blocking error message distinct from "no results," letting the user retry the action.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Build and price a single-Collection Architecture (Priority: P1)

A user creates a new Architecture, adds one Collection (Application Component or VPC) to it,
searches the AWS pricing catalog to find the AWS SKUs they want, adds those SKUs to the
Collection, enters pricing inputs for each SKU (commitment term, purchase option, and usage
quantity), and calculates a total price for the Architecture.

**Why this priority**: This is the smallest slice that delivers the product's core value —
turning an assembled set of AWS resources into a real price. Everything else in this feature
(multiple Collections, connectors, lifecycle management) builds on top of this loop.

**Independent Test**: Can be fully tested by creating one Architecture, adding one Collection,
searching for and adding at least one AWS SKU with pricing inputs, clicking calculate, and
verifying a total price is displayed.

**Acceptance Scenarios**:

1. **Given** a user has selected AWS as the active provider, **When** they create a new
   Architecture and give it a name, **Then** the Architecture is saved and appears in their
   Architecture list.
2. **Given** an Architecture exists, **When** the user adds a Collection and chooses its type
   (Application Component or VPC), **Then** the Collection is saved as part of that Architecture.
3. **Given** a Collection exists, **When** the user searches the AWS catalog by service code,
   product family, or free text, **Then** matching AWS SKUs are shown for selection.
4. **Given** search results are shown, **When** the user adds a SKU to the Collection and enters
   its term, purchase option, and usage quantity, **Then** those pricing inputs are saved against
   that SKU within the Collection.
5. **Given** an Architecture has at least one Collection with at least one priced SKU,
   **When** the user triggers a price calculation, **Then** the system displays a total price
   reflecting all entered SKUs and their inputs.
6. **Given** a SKU in the Architecture has no price available for the entered term/purchase
   option in the current pricing data, **When** the user calculates the price, **Then** that SKU
   is clearly flagged as unpriceable and is not silently omitted or estimated.

---

### User Story 2 - Compose multi-Collection Architectures with Data Connectors (Priority: P2)

A user adds multiple Collections to an Architecture and explicitly connects pairs of them with
Data Connectors to represent data flow between them (for example, between two Application
Components, or between an Application Component and a VPC). Where a connector represents a real
network boundary, the user can optionally attach a specific AWS SKU (such as a NAT Gateway,
Internet Gateway, or Transit Gateway) to that connector, with its own pricing inputs.

**Why this priority**: Extends the core loop to realistic architectures composed of multiple
parts, where the cost of data moving between components matters. It depends on User Story 1's
Collections already existing, and is not required to demonstrate the core pricing value on its
own.

**Independent Test**: Can be fully tested by creating an Architecture with two Collections,
adding a Data Connector between them, optionally attaching an AWS SKU to that connector with its
own pricing inputs, and verifying the connector's attached SKU cost is included in the
Architecture's calculated total.

**Acceptance Scenarios**:

1. **Given** an Architecture has two or more Collections, **When** the user creates a Data
   Connector between two of them, **Then** the connector is saved as part of the Architecture and
   visibly links those two Collections.
2. **Given** a Data Connector exists, **When** the user attaches a specific AWS SKU to it and
   enters that SKU's pricing inputs, **Then** the attached SKU and its inputs are saved against
   the connector.
3. **Given** an Architecture has Collections connected by a Data Connector with an attached
   priced SKU, **When** the user calculates the total price, **Then** the connector's SKU cost is
   included in the total alongside the Collections' SKU costs.
4. **Given** a user attempts to connect a Collection to itself, **When** they try to save the
   connector, **Then** the system rejects the connection and explains why.

---

### User Story 3 - Manage Architectures over time (Priority: P3)

A user views the list of their existing Architectures for the currently selected provider,
re-opens one to keep editing it, and can remove Architectures, Collections, or Data Connectors
they no longer want via a soft delete that requires confirmation.

**Why this priority**: Necessary for real, ongoing use of the tool, but not required to prove the
core assemble-and-price value within a single working session — a user could complete User
Stories 1 and 2 in one sitting without ever needing to revisit a saved Architecture.

**Independent Test**: Can be fully tested by creating two Architectures, confirming both appear
in the Architecture list, soft-deleting one after confirming the prompt, and verifying it
disappears from the list while the underlying record is retained (not physically removed).

**Acceptance Scenarios**:

1. **Given** a user has created one or more Architectures, **When** they open the Architecture
   list for AWS, **Then** all of their non-deleted AWS Architectures are shown.
2. **Given** the provider selector is shown, **When** the user views it, **Then** AWS is
   selectable and active, while GCP and Azure are visible but disabled.
3. **Given** an existing Architecture, **When** the user chooses to delete it, **Then** they are
   prompted to confirm before the deletion proceeds.
4. **Given** a user confirms deleting an Architecture, **When** the deletion completes,
   **Then** the Architecture no longer appears in their list, but its data is retained
   (soft-deleted, not physically removed).
5. **Given** a user chooses to delete a Collection or a Data Connector within an open
   Architecture, **When** they confirm the deletion, **Then** that Collection or connector is
   removed from view but retained (soft-deleted) in the same way as an Architecture.

---

### Edge Cases

- What happens when a user searches the AWS catalog and no SKUs match their filters/text? The
  system must show a clear "no results" state rather than an empty or ambiguous screen.
- What happens when a user deletes a Collection that still has an active Data Connector attached
  to it? The attached Data Connector is soft-deleted along with the Collection.
- What happens when a user adds the same AWS SKU to a Collection more than once, or to two
  different Collections within the same Architecture? Both are allowed — the same SKU may
  legitimately appear more than once (e.g., two identical EC2 instances), each with its own
  independent pricing inputs.
- What happens when an Architecture contains two or more VPC Collections that are not linked by
  any Data Connector? The system warns the user that unconnected VPCs may not reflect real data
  flow costs, but does not block price calculation.
- What happens when the underlying AWS pricing snapshot updates while a user is mid-edit on an
  Architecture? Price calculation always uses the most recently available snapshot at the moment
  the user triggers it; a SKU that becomes unavailable in a newer snapshot is flagged per the
  unpriceable-SKU behavior in User Story 1.
- What happens when the AWS pricing data source itself is unreachable or errors out during a
  search or a price calculation (as opposed to one SKU simply lacking a price)? The system shows
  a distinct, blocking error state — never silently treated as "no results" or a $0 price — and
  lets the user retry.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow users to create a new Architecture with a name, associated
  with a cloud provider.
- **FR-002**: The system MUST associate every Architecture — and its Collections, Data
  Connectors, SKU selections, and pricing inputs — with the distinct identity of the user who
  created it, and MUST show a user only their own Architectures. Marking an Architecture as
  global, browsing other users' global Architectures, pricing one, and cloning one are out of
  scope for this feature (see Assumptions).
- **FR-003**: In v1, AWS MUST be the only selectable/active provider; GCP and Azure MUST be
  visible in the provider selector but disabled.
- **FR-004**: Users MUST be able to add one or more Collections to an Architecture, each
  designated as either "Application Component" or "VPC".
- **FR-005**: Users MUST be able to search and filter the AWS pricing catalog by service code,
  product family, and free-text service name when selecting SKUs to add to a Collection.
- **FR-006**: Users MUST be able to add one or more specific AWS SKUs to a Collection, including
  adding the same SKU more than once.
- **FR-007**: For each SKU added to a Collection, users MUST be able to enter pricing inputs:
  commitment term (e.g., On-Demand, 1-year Reserved, 3-year Reserved), purchase option (e.g., No
  Upfront, Partial Upfront, All Upfront, where applicable to the chosen term), and a usage
  quantity appropriate to that SKU's pricing unit.
- **FR-008**: Users MUST be able to create a Data Connector between any two distinct Collections
  within the same Architecture; the system MUST reject a connector from a Collection to itself.
- **FR-009**: Users MUST be able to optionally attach a single specific AWS SKU (e.g., a NAT
  Gateway, Internet Gateway, or Transit Gateway) to a Data Connector, with its own pricing inputs
  entered the same way as for a Collection's SKU.
- **FR-010**: Users MUST be able to trigger a price calculation for an Architecture that totals
  the cost of every SKU across all of its Collections plus any SKUs attached to its Data
  Connectors, using each SKU's entered pricing inputs against the current AWS pricing data.
- **FR-011**: The system MUST display the calculated total price to the user after a calculation
  completes, and that price MUST be derived only from real, current AWS pricing data — never a
  cached, estimated, or fabricated value.
- **FR-012**: If a SKU included in an Architecture has no available price for its entered term
  and purchase option in the current AWS pricing data, the system MUST flag that SKU as
  unpriceable in the calculation result rather than omitting it silently or estimating a value.
- **FR-013**: Users MUST be able to view a list of their own, non-deleted Architectures for the
  currently selected provider.
- **FR-014**: Users MUST be able to delete an Architecture; the system MUST prompt for
  confirmation before deleting, and the deletion MUST be a soft delete (the Architecture is
  marked deleted and hidden from the user's list, but its data is retained, not physically
  removed).
- **FR-015**: Users MUST be able to delete a Collection or a Data Connector within an
  Architecture; the system MUST prompt for confirmation, and the deletion MUST be a soft delete
  consistent with FR-014. Deleting a Collection MUST also soft-delete any Data Connector attached
  to it.
- **FR-016**: The system MUST persist each user's Architectures, Collections, Data Connectors,
  SKU selections, and their most recently entered pricing inputs across sessions.
- **FR-017**: When an Architecture contains two or more VPC Collections with no Data Connector
  linking them, the system MUST warn the user but MUST NOT block price calculation.
- **FR-018**: If the AWS pricing data source is temporarily unreachable or fails while searching
  the catalog or calculating a price, the system MUST show a clear, blocking error message
  distinct from a "no results"/zero-cost outcome, and MUST let the user retry the action.

### Key Entities

- **User**: The distinct identity that owns Architectures. In v1 every Architecture, Collection,
  Data Connector, and pricing input is scoped to exactly one User; the login/identification
  mechanism itself is a planning-level decision, not specified here.
- **Architecture**: A user-owned, named, reusable design representing a priced AWS setup;
  associated with one cloud provider (AWS in v1); soft-deletable; composed of Collections and
  Data Connectors.
- **Collection**: A user-defined grouping of AWS SKUs within an Architecture, typed as either
  Application Component or VPC; soft-deletable.
- **SKU Selection**: A reference from a Collection (or from a Data Connector's attached service)
  to one specific AWS pricing catalog SKU, together with the user's entered pricing inputs
  (term, purchase option, usage quantity) for that occurrence.
- **Data Connector**: A user-created link between two distinct Collections within the same
  Architecture, representing data flow between them; may optionally reference one SKU Selection
  representing an attached connecting service (e.g., a gateway); soft-deletable.
- **AWS Pricing Catalog** *(external, read-only)*: The vendor pricing dataset — services,
  product families, SKUs, and prices — sourced from Parquet files via DuckDB. Not owned or
  written by this feature; only read from.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can assemble a simple Architecture (one Collection, at least one priced SKU)
  and see a calculated total price in a single working session, without needing help or
  documentation beyond the on-screen UI.
- **SC-002**: 100% of calculated prices shown to a user are traceable to a specific, real AWS
  pricing snapshot — no calculated price is ever an estimate or placeholder value.
- **SC-003**: A user can build an Architecture with two or more connected Collections and receive
  one consolidated total price that reflects every SKU in every Collection and every priced Data
  Connector.
- **SC-004**: Soft-deleted Architectures, Collections, and Data Connectors are removed from the
  user's active views immediately and consistently (never require a refresh or re-login to
  disappear), while remaining intact in the underlying data store.
- **SC-005**: A user searching the AWS catalog by service code, product family, or text can
  locate a specific well-known AWS service (e.g., EC2, S3, RDS) without having to browse the full
  unfiltered catalog.

## Assumptions

- Every Architecture is linked to a real, distinct user identity from v1 (not anonymous, not
  globally shared) per FR-002; however, the specific login/identification mechanism is a
  planning-level decision, not specified here. Marking an Architecture as global, browsing other
  users' global Architectures, pricing one, and cloning one as a starting point are confirmed
  future-phase goals and are explicitly out of scope for this feature.
- GCP and Azure are shown in the provider selector as disabled placeholders in v1 with no
  functionality behind them; full support is a future phase.
- The landing page's price-trend chart, the weekly service-count-change table, and any
  "standard architecture" starter templates (e.g., ETL, ML pipeline, basic website presets) are
  explicitly out of scope for this feature and will be specified separately.
- Attribute-level faceted search (e.g., filtering EC2 results by instance type or operating
  system) is deferred; v1 search/filter is limited to service code, product family, and free
  text, and browsing a very large product family's SKU list (e.g., all EC2 Compute Instance
  SKUs) is accepted as unwieldy for now.
- Data Connectors are treated as non-directional links between two Collections for pricing
  purposes in v1; no directionality is required to calculate a connector's attached-service cost.
- Price calculation always uses the most recently available AWS pricing snapshot at the moment
  the user triggers it; selecting a prior point-in-time snapshot for calculation is out of scope
  for this feature.

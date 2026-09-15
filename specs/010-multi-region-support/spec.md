# Feature Specification: Multi-Region Collections and Region-Grouped Pricing

**Feature Branch**: `010-multi-region-support`

**Created**: 2026-09-15

**Status**: Draft

**Input**: User description: "see docs/functionality_2026-09-15.md". The source document covers two updates driven by AWS pricing data now being retrieved per-region (each region in its own partition): (1) giving every VPC and Application Component collection an explicit AWS region — assigned at creation, locked once the collection has content, enforced when nesting an Application inside a VPC, and used to scope service search (including for cross-region Connectors, which gain explicit from/to direction and a directional arrow) — plus relabeling "Application Component(s)" to "Application(s)" to save horizontal space; and (2) restructuring column 5's per-SKU pricing breakdown to group line items into labeled sections by region, each with its own subtotal, below the existing Total and above the existing Data Timestamp line. During `/speckit-clarify`, the user additionally requested (not in the source document): displaying each collection's region name in the bottom-right corner of its box on the architecture diagram (column 4) — always for a VPC, and for an Application only while it is not nested inside a VPC.

## Clarifications

### Session 2026-09-15

- Q: When this feature ships, what region should already-existing VPC and Application collections (created before regions existed) be assigned? → A: Auto-backfill every existing collection with the app's former single global pricing region (e.g., us-east-1) — preserves current behavior unchanged, no user action needed.
- Q: When a user adds a new Application directly inside a specific VPC, does the system skip the region prompt and inherit that VPC's region, or still show the prompt and validate afterward? → A: Skip the prompt; the new Application silently inherits its parent VPC's region. (Noted separately: today, adding an Application while a VPC is selected does not visually snap the new box into the VPC on the diagram — a pre-existing issue independent of region inheritance; see Edge Cases.)
- Q: Should the region-selection prompt offer every AWS region, or only regions the pricing dataset actually has data for? → A: Only regions the pricing dataset currently has data for.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Assign a region when creating a collection (Priority: P1)

When a user clicks "+Add" to create a new VPC collection, or an unattached Application collection, in the Architecture Editor (column 2), they are asked to choose an AWS region from the regions currently available before the collection is created. If the user instead adds an Application while a specific VPC is already selected as its parent, no prompt appears — the new Application silently inherits that VPC's region.

**Why this priority**: This is foundational — every other rule in this feature (region locking, same-region nesting, region-scoped search, region-grouped pricing) depends on every collection having a region from the moment it exists.

**Independent Test**: Click "+Add" for a new collection, confirm a region-selection prompt appears listing available AWS regions, choose one, confirm, and verify the created collection is associated with that region.

**Acceptance Scenarios**:

1. **Given** column 2's "+Add" control, **When** the user adds a new VPC, **Then** a prompt appears with a dropdown of available AWS regions that must be chosen before the VPC is created.
2. **Given** the same "+Add" control, **When** the user adds a new Application, **Then** the same region-selection prompt appears and applies identically.
3. **Given** the region-selection prompt, **When** the user selects a region and confirms, **Then** the new collection is created and associated with that region.
4. **Given** the region-selection prompt, **When** the user cancels without selecting a region, **Then** no collection is created.
5. **Given** a VPC is already selected as the parent, **When** the user adds a new Application, **Then** no region-selection prompt appears, and the new Application is created with that VPC's region.

---

### User Story 2 - A collection's region locks once it has content (Priority: P1)

Once a collection contains a service (or, for a VPC, a nested Application or a service), its region can no longer be changed.

**Why this priority**: Changing a collection's region after services are attached would silently invalidate pricing/service data tied to the old region — a data-integrity failure in the app's core value proposition.

**Independent Test**: Create an empty collection and confirm its region is editable; attach a service to it; confirm the region control becomes disabled/rejects changes.

**Acceptance Scenarios**:

1. **Given** a newly created collection with no service and (for a VPC) no nested Application, **When** the user views it, **Then** its region is editable.
2. **Given** a collection (VPC or Application) with at least one service attached, **When** the user attempts to change its region, **Then** the change is rejected and the collection's region is unchanged.
3. **Given** a VPC with a nested Application but no service of its own, **When** the user attempts to change the VPC's region, **Then** the change is rejected.

---

### User Story 3 - Applications can only nest inside same-region VPCs (Priority: P1)

An Application collection belonging to region X can only be placed inside a VPC collection that is also in region X.

**Why this priority**: Enforces the fundamental region-consistency rule so architectures never end up implying an Application runs inside a VPC of a different region, and keeps the collections underneath it eligible for accurate, region-scoped pricing.

**Independent Test**: Create a VPC in region A and an Application in region B; attempt to nest the Application in the VPC and confirm it is rejected; then create an Application in region A and confirm nesting succeeds.

**Acceptance Scenarios**:

1. **Given** a VPC in region A and an unplaced Application in region B, **When** the user attempts to nest the Application inside the VPC, **Then** the action is rejected, the Application remains outside the VPC, and the user is shown a clear region-mismatch explanation.
2. **Given** a VPC in region A and an Application also in region A, **When** the user nests the Application inside the VPC, **Then** the nesting succeeds.

---

### User Story 4 - Service search is scoped to the selected collection's region (Priority: P2)

The service/catalog search in column 2 returns only services available in the region of whichever collection is currently selected.

**Why this priority**: Prevents a user from attaching a service to a collection that isn't actually offered in that collection's region — an otherwise-invalid pairing that this feature's data model now makes preventable.

**Independent Test**: Select a collection in region A, search the catalog, and confirm only region-A services appear; select a collection in region B and confirm results change to region-B services.

**Acceptance Scenarios**:

1. **Given** a collection in region A is selected, **When** the user searches the service catalog, **Then** only services available in region A are returned.
2. **Given** the user instead selects a collection in region B, **When** they repeat the search, **Then** results reflect region B's available services.

---

### User Story 5 - Connector service search and creation follow the "from" collection's region (Priority: P2)

For a Connector linking two collections that may be in different regions, the service catalog shown for that Connector is based on the "from" collection's region. In the explicit "Add Connector" flow, the user sets "From" and "To" directly; when a Connector is instead created by selecting two collections in column 2, the first-selected collection becomes "From" and the second-selected becomes "To."

**Why this priority**: Connectors — unlike Application-in-VPC nesting — are explicitly allowed to cross regions, but service availability still needs one well-defined region to resolve against.

**Independent Test**: Create two collections in different regions; connect them via "Add Connector" with an explicit From/To and confirm the shown services match the "From" collection's region; then create a connector by selecting the two collections directly (first = from, second = to) and confirm the same rule holds.

**Acceptance Scenarios**:

1. **Given** VPC A in region X and VPC B in region Y, **When** the user opens "Add Connector" and sets A as "From" and B as "To," **Then** the service catalog shown for that connector reflects region X.
2. **Given** the same two collections, **When** the user instead selects collection A, then collection B, and triggers the connect action in column 2, **Then** the resulting connector has A as "from" and B as "to," and the service catalog reflects region X.

---

### User Story 6 - Connectors display a directional arrow (Priority: P2)

Every Connector rendered on the architecture diagram (column 4) shows an arrow pointing from its "from" collection to its "to" collection.

**Why this priority**: Makes the from/to relationship visually unambiguous at a glance, which matters more now that a connector's "from" side determines which services are available for it.

**Independent Test**: Create a connector between two collections and confirm the diagram shows a directional arrow pointing toward the "to" collection.

**Acceptance Scenarios**:

1. **Given** a connector between collection A ("from") and collection B ("to"), **When** the user views the architecture diagram, **Then** an arrow is shown on the connector pointing toward collection B.

---

### User Story 7 - Pricing breakdown grouped and subtotaled by region (Priority: P1)

In column 5, the per-SKU pricing breakdown is restructured into labeled sections by region: each section lists only that region's line items followed by that region's subtotal. The existing Total stays above these sections, and the existing Data Timestamp line stays after them.

**Why this priority**: As architectures span multiple regions, an undifferentiated flat list of SKU prices no longer shows each region's cost contribution — this is a core pricing-clarity requirement for a pricing tool.

**Independent Test**: Build an architecture with priced services in two regions, calculate pricing, and confirm column 5 shows one labeled section per region, each with its line items and a subtotal, with the Data Timestamp line still present at the end.

**Acceptance Scenarios**:

1. **Given** priced services in two different regions, **When** column 5 renders the pricing breakdown, **Then** each region appears as its own labeled section containing only that region's line items.
2. **Given** a region's section, **When** all of that region's line items are listed, **Then** a region subtotal line follows, equal to the sum of that region's line items.
3. **Given** the full breakdown, **When** it renders, **Then** the Data Timestamp line remains present after all region sections.
4. **Given** only one region is in use across the architecture, **When** column 5 renders, **Then** that single region still appears as its own labeled, subtotaled section rather than reverting to an unlabeled flat list.

---

### User Story 8 - "Application Components" is relabeled "Applications" (Priority: P3)

All user-facing text that previously read "Application Component(s)" now reads "Application(s)," freeing horizontal space in column 2's collection-type selector and lists for the collection name.

**Why this priority**: A cosmetic, low-risk space-efficiency change with no behavioral impact — lowest priority among this feature's changes.

**Independent Test**: Open column 2's collection-type selector and any other collection labels; confirm they read "Application"/"Applications" instead of "Application Component(s)."

**Acceptance Scenarios**:

1. **Given** column 2's collection-type selector, **When** the user opens it, **Then** the option reads "Application" instead of "Application Component."
2. **Given** any other UI text that previously read "Application Component(s)," **Then** it now reads "Application(s)."

---

### User Story 9 - Region label shown on collection boxes in the diagram (Priority: P2)

On the architecture diagram (column 4), a VPC collection's box always displays its region name in the bottom-right corner. An Application collection's box displays its region name in the bottom-right corner only when it is not nested inside a VPC; once the Application is placed inside a VPC, its region label is removed (the containing VPC's label already conveys it).

**Why this priority**: Gives users an at-a-glance way to see which region each visible collection belongs to directly on the diagram; useful and reinforces the rest of this feature, but not correctness-blocking the way region locking and same-region nesting are.

**Independent Test**: Create a VPC and confirm its region name appears in the bottom-right corner of its box; create an unattached Application and confirm its region name also appears in its bottom-right corner; nest the Application inside the VPC and confirm its region label disappears while the VPC's remains.

**Acceptance Scenarios**:

1. **Given** a VPC on the diagram, **When** viewing its box, **Then** its region name is shown in the bottom-right corner.
2. **Given** an Application collection not nested in any VPC, **When** viewing its box, **Then** its region name is shown in the bottom-right corner.
3. **Given** an Application collection nested inside a VPC, **When** viewing its box, **Then** no region name is shown in its bottom-right corner.
4. **Given** an Application's region label is showing while unnested, **When** the user nests it inside its same-region VPC, **Then** the region label is removed from the Application's box.

---

### Edge Cases

- What happens to a line item whose service is globally scoped rather than tied to one AWS region? → It is grouped into its own clearly labeled section (e.g., "Global"), subtotaled the same way as a regional section.
- What happens if a user tries to change a locked collection's region through any control, not just the primary one? → The lock (User Story 2) is enforced everywhere a region could be edited, not only in one UI surface.
- What happens when a user attempts to nest an Application into a VPC of a different region by means other than drag (e.g., a menu action), if one exists? → The same region-match rejection applies regardless of the interaction path.
- What happens to the ordering of line items within a region's section? → Existing highest-price-first ordering is preserved within each section; only the grouping and subtotal are new.
- What happens to the "unpriceable SKUs" list and the overall Total/Price Change indicators above the per-SKU breakdown? → Unchanged by this feature; only the priced-SKU list becomes region-grouped.
- Does the new Application visually snap into its parent VPC's box on the diagram when created via region inheritance? → Not necessarily today: the diagram not visually nesting a newly added Application into a currently-selected VPC is a pre-existing, separate issue, independent of this feature. Region inheritance (FR-001a) applies to the logical parent/child relationship regardless of whether the diagram renders the nesting correctly.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST prompt the user to choose an AWS region from the currently available regions when creating a new VPC collection, or a new unattached Application collection, via "+Add," before the collection is created.
- **FR-001a**: System MUST skip the region-selection prompt when creating an Application while a specific VPC is already selected as its parent, and instead automatically assign the new Application that VPC's region.
- **FR-002**: System MUST persist the chosen region as an attribute of the collection.
- **FR-003**: System MUST prevent a collection's region from being changed once that collection (VPC or Application) has at least one service attached, or, for a VPC, at least one nested Application — enforced everywhere the region could otherwise be edited.
- **FR-004**: System MUST prevent an Application collection from being nested inside a VPC collection whose region differs from the Application's region, and MUST give the user clear feedback when this is attempted.
- **FR-005**: System MUST restrict service/catalog search results for a selected collection to services available in that collection's region.
- **FR-006**: System MUST determine service/catalog search results shown for a Connector using the region of that Connector's "from" collection, regardless of the "to" collection's region.
- **FR-007**: In the explicit "Add Connector" flow, System MUST let the user directly designate which collection is "From" and which is "To."
- **FR-008**: When a Connector is instead created by selecting two collections directly in column 2, System MUST treat the first-selected collection as "From" and the second-selected collection as "To."
- **FR-009**: System MUST render every Connector on the architecture diagram with a directional arrow pointing from its "From" collection toward its "To" collection.
- **FR-010**: System MUST relabel all user-facing occurrences of "Application Component(s)" to "Application(s)," including the collection-type selector in column 2.
- **FR-011**: System MUST group the per-SKU pricing breakdown in column 5 into sections by region, each section listing only that region's line items.
- **FR-012**: System MUST display a subtotal for each region's section, equal to the sum of that region's line items, positioned immediately after that region's line items.
- **FR-013**: System MUST keep the overall Total positioned above the region-grouped breakdown and the Data Timestamp line positioned after the last region section, unchanged from current placement/meaning.
- **FR-014**: System MUST preserve the existing highest-price-first ordering of line items within each region's section.
- **FR-015**: System MUST group any line item without a determinable specific region into its own clearly labeled section, subtotaled the same as a regional section.
- **FR-016**: System MUST automatically assign every collection that existed before this feature shipped to the AWS region that was previously the application's single global pricing region, without requiring any user action.
- **FR-017**: System MUST offer only regions the pricing dataset currently has data for in the region-selection prompt, excluding AWS regions without available pricing data.
- **FR-018**: System MUST display a VPC collection's region name in the bottom-right corner of its box on the architecture diagram (column 4).
- **FR-019**: System MUST display an Application collection's region name in the bottom-right corner of its box only while it is not nested inside a VPC, and MUST remove that label once the Application is nested inside a VPC.

### Key Entities

- **Collection (VPC / Application)**: A user-defined grouping (existing entity) that now carries a region attribute in addition to its existing name and type. A VPC may contain nested Applications. A collection's region is fixed once it has content (a service, or for a VPC, a nested Application or service).
- **Connector**: Links a "from" collection to a "to" collection, which may be in different regions. Its service search scope resolves to the "from" collection's region. Now rendered on the diagram with a direction-indicating arrow.
- **Region**: An AWS region identifier a collection can be assigned, drawn only from regions the pricing dataset currently has data for. Determines which services a collection (or a connector's "from" side) can search and select.
- **Pricing Breakdown Line Item**: An individual priced SKU's contribution in column 5, now attributed to a region (or a "Global" grouping) for the purpose of sectioning and subtotaling the breakdown.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can create a new VPC or Application and assign it a region in a single guided step, with no ambiguity about which region the collection belongs to.
- **SC-002**: 100% of attempts to change the region of a collection that already has content are prevented — no collection's region ever changes silently after content is attached.
- **SC-003**: 100% of attempts to nest an Application inside a differently-regioned VPC are rejected, so no architecture can end up with a region-mismatched nesting.
- **SC-004**: When viewing the pricing breakdown for an architecture spanning multiple regions, users can read each region's cost contribution directly from a subtotal, without manually summing individual line items.
- **SC-005**: Users can determine a connector's direction (which collection is "from" vs. "to") at a glance from the diagram, without opening any detail panel.
- **SC-006**: Service search results shown for a selected collection always match that collection's region, eliminating cross-region service-selection mistakes.

## Assumptions

- A collection is treated as having region-locking content (FR-003) as soon as one service selection exists on it, or, for a VPC, as soon as it has one nested Application — matching the source requirement's phrasing.
- Rejecting an invalid same-region nesting attempt (User Story 3) gives the user visible feedback (e.g., the Application returns to its prior position with an inline explanation) rather than a silent no-op.
- The "unpriceable SKUs" list and the overall Total/Price Change indicators in column 5 are out of scope for this feature and remain as they currently behave; only the priced-SKU list is restructured into region sections.
- The visual snapping of a newly added Application into its selected parent VPC's box on the architecture diagram (column 4) is a pre-existing, separate issue tracked outside this feature; region inheritance (FR-001a) is defined against the logical parent/child relationship, not the diagram's current rendering behavior.

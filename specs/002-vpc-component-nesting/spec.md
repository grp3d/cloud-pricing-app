# Feature Specification: Nest Application Components into VPCs

**Feature Branch**: `002-vpc-component-nesting`

**Created**: 2026-09-08

**Status**: Draft

**Input**: User description: "ability to drag and drop application components into VPC components (VPC components can contain aws services AND application components)"

## Clarifications

### Session 2026-09-08

- Q: When a VPC containing nested Application Components is deleted, what should happen to those nested Application Components? → A: They are un-nested and kept — the Application Components survive as top-level Collections in the Architecture, no longer inside any VPC. Nothing the user built is lost from deleting a VPC.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Organize Application Components inside a VPC (Priority: P1)

A user working on an Architecture drags an existing Application Component Collection onto a VPC Collection on the assembly canvas, nesting it inside that VPC. The Application Component keeps every AWS SKU it already contains and all of its pricing inputs — nesting only changes where it sits organizationally, not what it contains or what it costs. The user can later drag it into a different VPC to move it, or drag it back out to return it to the top level of the Architecture.

**Why this priority**: This is the entire feature — a single, self-contained capability that makes an Architecture with multiple VPCs and application tiers visually and organizationally match how the user actually thinks about their design.

**Independent Test**: Can be fully tested by creating an Architecture with one VPC and one Application Component (each with at least one AWS SKU already added), dragging the Application Component onto the VPC, and verifying it now displays as nested inside that VPC while its SKUs and the Architecture's calculated total are unchanged.

**Acceptance Scenarios**:

1. **Given** an Architecture has a VPC Collection and a separate, top-level Application Component Collection, **When** the user drags the Application Component onto the VPC, **Then** the Application Component is nested inside that VPC and displays as part of it.
2. **Given** an Application Component is nested inside VPC A, **When** the user drags it onto VPC B in the same Architecture, **Then** it is removed from VPC A and nested inside VPC B instead.
3. **Given** an Application Component is nested inside a VPC, **When** the user drags it off the VPC onto open canvas space, **Then** it returns to being a top-level Collection in the Architecture, no longer nested in any VPC.
4. **Given** an Application Component containing AWS SKUs with pricing inputs already entered, **When** the user nests it inside a VPC (or moves it, or un-nests it), **Then** every one of its SKUs and pricing inputs is preserved unchanged.
5. **Given** an Architecture has a calculated total price, **When** the user nests, moves, or un-nests an Application Component, **Then** recalculating produces the same total as before (nesting alone never changes cost).
6. **Given** a user attempts to drag a VPC Collection onto another VPC Collection, **When** they try to drop it, **Then** the system rejects the nesting and the VPC remains a top-level Collection.

---

### Edge Cases

- What happens when a VPC containing one or more nested Application Components is deleted? Per the Clarifications above, the nested Application Components are un-nested and survive as top-level Collections in the Architecture — deleting a VPC never deletes what was nested inside it.
- What happens when a nested Application Component itself is deleted? It is removed the same way a top-level Application Component is removed (existing soft-delete behavior); its containing VPC and the VPC's other contents are unaffected.
- What happens to Data Connectors attached to an Application Component that gets nested, moved, or un-nested? They continue to reference that Application Component exactly as before — nesting has no effect on Data Connectors or the connections they represent.
- What happens if a user tries to nest a VPC inside another VPC? Rejected — only Application Components can be nested inside a VPC; VPCs are always top-level.
- What happens to a VPC's own directly-added AWS SKUs (not part of any nested Application Component) when an Application Component is nested inside or removed from it? They are unaffected — a VPC's own SKUs and its nested Application Components are independent of each other.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to nest an existing top-level Application Component Collection inside a VPC Collection within the same Architecture by dragging it onto the VPC on the assembly canvas.
- **FR-002**: Users MUST be able to move an Application Component already nested inside one VPC directly into a different VPC in the same Architecture by dragging it onto the new VPC.
- **FR-003**: Users MUST be able to remove a nested Application Component from its VPC, returning it to a top-level Collection in the Architecture, by dragging it off the VPC.
- **FR-004**: The system MUST reject nesting a VPC Collection inside another VPC Collection; VPCs remain top-level Collections only.
- **FR-005**: A VPC Collection MUST be able to contain any number of nested Application Components (zero or more) at the same time, independent of the AWS SKUs already addable directly to that VPC (existing behavior, unchanged).
- **FR-006**: Nesting, moving, or un-nesting an Application Component MUST NOT change its own AWS SKU selections or their pricing inputs.
- **FR-007**: Deleting a VPC Collection that contains nested Application Components MUST soft-delete only the VPC; every Application Component that was nested inside it MUST survive as a top-level Collection in the Architecture.
- **FR-008**: Deleting a nested Application Component MUST behave the same as deleting a top-level one (existing soft-delete behavior) and MUST NOT affect its containing VPC or any of that VPC's other contents.
- **FR-009**: Price calculation for an Architecture MUST be unaffected by nesting structure — the total MUST include every Collection's SKU selections and every Data Connector's attached SKU exactly as it does today, regardless of which Collections are nested inside which VPCs.
- **FR-010**: Data Connectors involving a nested Application Component MUST continue to function exactly as they do for a top-level Application Component; nesting MUST NOT alter, remove, or restrict any existing Data Connector.

### Key Entities

- **Collection** *(existing entity, extended)*: In addition to its existing type (Application Component or VPC) and its own AWS SKU Selections, a Collection now also has an optional nesting relationship — an Application Component Collection may be nested inside exactly one VPC Collection within the same Architecture at a time, or be nested inside none (top-level). A VPC Collection cannot itself be nested inside another Collection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can nest an existing Application Component into a VPC in a single drag-and-drop action, with no separate confirmation step required.
- **SC-002**: A user can reorganize an Architecture — moving Application Components between VPCs or back to top-level — without ever losing an AWS SKU, a pricing input, or a Data Connector as a side effect.
- **SC-003**: 100% of calculated Architecture totals remain numerically identical before and after any nesting, moving, or un-nesting action performed on its own (with no other changes to SKUs or inputs).
- **SC-004**: Deleting a VPC that contains nested Application Components never results in the loss of those Application Components or their AWS SKUs.

## Assumptions

- An Application Component can be nested inside at most one VPC at a time (single parent), matching how a real workload sits inside exactly one network boundary.
- VPC-inside-VPC nesting is out of scope for this feature; VPCs are always top-level Collections within an Architecture.
- The drag-and-drop interaction happens on the same assembly canvas already used to create Data Connectors between Collections (per the AWS Architecture Assembly & Pricing feature); this feature only adds a new interaction on that existing canvas, it does not introduce a new page or view.
- Nesting is a purely organizational/visual relationship. It has no effect on pricing, on Data Connectors, or on any other Collection's contents.

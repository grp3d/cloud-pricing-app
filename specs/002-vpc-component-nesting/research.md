# Phase 0 Research: Nest Application Components into VPCs

This feature is small and builds directly on `001-assemble-price-aws-architecture`'s existing
stack — most of 001's `research.md` decisions apply unchanged. This document covers only the
new decisions this feature introduces.

## 1. Representing nesting on the React Flow canvas

- **Decision**: Use `@xyflow/react`'s built-in parent/child node support — set a nested
  Application Component node's `parentId` to its VPC node's id so it renders positioned inside
  the VPC's box. **Revised during implementation**: `extent: 'parent'` is deliberately *not*
  set. That option clamps a child's drag movement to stay inside its parent's bounds — which
  would make it impossible to drag a nested node fully outside its VPC to un-nest it (spec
  FR-003). `parentId` alone still gives correct parent-relative rendering and positioning
  without constraining the drag gesture. VPC nodes get a larger, container-style rendering
  (sized to fit their current children) instead of the compact box used today.
- **Rationale**: This is still the built-in "group node" pattern React Flow ships for — reusing
  it means no custom hit-testing and no custom rendering of a "contains" relationship. The
  `extent` option specifically conflicts with a stated requirement (un-nesting via drag-out),
  so it's the one piece of the built-in mechanism not used here.
- **Alternatives considered**: A custom overlay/highlight system built from scratch on raw drag
  events — rejected, reimplements what the library already provides for the containment
  rendering, adds real maintenance surface for no product benefit. Using `extent: 'parent'` and
  requiring a separate explicit "un-nest" button instead of drag-out — rejected, contradicts
  the spec's explicit ask for a symmetric drag-and-drop interaction (FR-002/FR-003) and
  SC-001's single-drag-action requirement.

## 2. Detecting a nest/move/un-nest gesture

- **Decision**: On `onNodeDragStop` for an Application Component node, compute whether its
  dropped position overlaps a VPC node's bounding box:
  - Overlaps a VPC it wasn't already nested in → nest/move: call
    `PATCH /collections/{id}` with the VPC's id, then let the success response's refetch set
    `parentId` for real (the drag position becomes a first optimistic hint, not the source of
    truth).
  - Doesn't overlap any VPC and it was nested → un-nest: call `PATCH /collections/{id}` with
    `parent_collection_id: null`.
  - Otherwise (still over the same VPC, or still at top-level and dropped on empty canvas) → no
    API call.
- **Rationale**: `onNodeDragStop` is the natural "gesture complete" moment; deriving the
  nest/move/un-nest decision from geometry rather than a separate explicit "drop zone" widget
  keeps the interaction a single continuous drag, matching the spec's "single drag-and-drop
  action" success criterion (SC-001).
- **Alternatives considered**: A distinct "Assign to VPC" dropdown per Application Component —
  rejected as a worse experience than what the user explicitly asked for (drag-and-drop) and no
  simpler to build.

## 3. Enforcing nesting rules (who can nest into what)

- **Decision**: Two layers, same pattern 001 already uses for Data Connector validation:
  - **Database**: a `CHECK` constraint that `parent_collection_id IS NULL OR type =
    'application_component'` — a VPC can never have a parent, enforced at the row level
    regardless of API bugs.
  - **API**: `PATCH /collections/{id}` validates that the referenced `parent_collection_id`
    (when non-null) is an existing, non-deleted, `type = 'vpc'` Collection in the *same*
    Architecture — a rule a single-row `CHECK` constraint cannot express (it depends on another
    row), so it lives in `architecture_service.py`, exactly where 001 already validates that a
    Data Connector's two Collections belong to the same Architecture.
- **Rationale**: Consistent with the existing validated pattern in the codebase rather than
  introducing a new one; the single-row rule at the DB layer is a real safety net, the
  cross-row rule at the API layer is exactly as strict.
- **Alternatives considered**: A Postgres trigger enforcing the cross-row rule at the DB layer
  too — rejected as unjustified complexity (Principle VI) for a rule already fully covered by
  the API layer plus test coverage, matching how 001 already treats the analogous connector rule.

## 4. Effect on price calculation

- **Decision**: No change to `src/services/price_calculation.py`. Confirmed by inspection:
  `calculate_architecture_price` iterates `architecture.collections` directly (every Collection
  belonging to the Architecture, regardless of any `parent_collection_id`) and sums every
  Collection's `sku_selections` — nesting never removes a Collection from that list, it only adds
  a relationship between two Collections that are both still members of the same Architecture.
- **Rationale**: Directly satisfies spec FR-009 (price calculation must be unaffected by
  nesting) by construction, with no new logic to write — only a test to prove it stays true.
- **Alternatives considered**: N/A — this is a confirmation, not a design choice.

## 5. VPC-deletion cascade behavior

- **Decision**: Extend `soft_delete_collection` (already used for the existing Data-Connector
  cascade in 001) to also set `parent_collection_id = NULL` on every non-deleted Application
  Component whose parent is the Collection being deleted, in the same transaction as the
  existing connector cascade.
- **Rationale**: Directly implements the spec's Clarifications decision (un-nest and keep,
  never cascade-delete) using the exact cascade mechanism 001 already established for
  connectors — one function, one transaction, no new pattern.
- **Alternatives considered**: A separate cascade function — rejected, the existing
  `soft_delete_collection` is already the single place Collection-deletion side effects belong.

## Outstanding items

None. All Technical Context fields are resolved; no `NEEDS CLARIFICATION` markers remain.

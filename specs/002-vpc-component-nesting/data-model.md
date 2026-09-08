# Phase 1 Data Model: Nest Application Components into VPCs

This feature extends exactly one entity already defined in
`specs/001-assemble-price-aws-architecture/data-model.md`: **Collection**. No new entity, no new
table. Everything else in 001's data model (User, Architecture, SKU Selection, Data Connector) is
unchanged and not repeated here.

## Collection *(extended)*

One new column, plus its validation rules.

| Field | Type | Notes |
|---|---|---|
| `parent_collection_id` | UUID, FK → `collections.id`, nullable | **NEW.** The VPC Collection this Application Component is nested inside, or `NULL` if it isn't nested (top-level). Always `NULL` for a `type = 'vpc'` Collection. `ON DELETE SET NULL` as a safety net (the application always soft-deletes, never hard-deletes, but this keeps referential integrity correct even so — see Cascade rule below). |

**New validation rules** (in addition to 001's existing ones):

- `parent_collection_id IS NULL OR type = 'application_component'` — a VPC can never have a
  parent (DB `CHECK` constraint: `ck_collection_parent_only_app_component`; spec FR-004).
- `parent_collection_id != id` — a Collection cannot be its own parent (DB `CHECK` constraint:
  `ck_collection_no_self_parent`; defensive, not reachable through the API today since a VPC can
  never be a valid parent value in the first place, but cheap and correct to state explicitly).
- **Application-layer only** (cannot be expressed as a single-row `CHECK` constraint): when
  `parent_collection_id` is set via the API, the referenced Collection MUST exist, MUST be
  `type = 'vpc'`, MUST NOT be soft-deleted, and MUST belong to the same `architecture_id` as the
  Collection being nested (spec FR-001, FR-002; mirrors how 001 already validates a Data
  Connector's two Collections belong to the same Architecture).

**Cascade rule** (extends 001's existing cascade): soft-deleting a `type = 'vpc'` Collection
(FR-007) sets `parent_collection_id = NULL` on every non-deleted Application Component Collection
whose `parent_collection_id` referenced it — in the same transaction as 001's existing cascade
that soft-deletes the VPC's Data Connectors. The Application Components themselves are never
soft-deleted by this cascade; they become top-level Collections in the Architecture again.

**State transitions** (new, for `parent_collection_id` specifically): `NULL ⇄ <a VPC's id>`, in
either direction, any number of times (nest, move to a different VPC, un-nest) — a strict
superset of 001's existing "no transition modeled" state for this field, since it didn't exist
before. A VPC being soft-deleted forces any children's `parent_collection_id` to `NULL` as
described above, which is a system-driven transition, not a user action, but uses the same value
space.

## Unaffected by this feature

- **Price calculation**: `SKU Selection` and how it sums into an Architecture's total is entirely
  unchanged — see `research.md` #4. Nesting is not read by `price_calculation.py` at all.
- **Data Connector**: unaffected structurally and behaviorally — a connector's
  `from_collection_id`/`to_collection_id` continue to reference Collections directly, regardless
  of which (if any) of those Collections is nested inside a VPC (spec FR-010).

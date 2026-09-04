# Phase 1 Data Model: AWS Architecture Assembly & Pricing

All entities below are user-defined data and live in **PostgreSQL** (Constitution Principle II).
The AWS Pricing Catalog itself is not modeled here — it is read live from DuckDB/Parquet and only
ever *referenced* (by `service_code` + `sku`) from `SKU Selection`, never copied in.

## Entity Relationship Overview

```text
User 1───* Architecture 1───* Collection 1───* SKU Selection
                     │              │
                     │              └───────────────┐
                     └───* Data Connector ───────────┴──0..1 SKU Selection (attached service)
                             │       │
                             │       └──→ to Collection
                             └──────────→ from Collection
```

## User

The identity that owns Architectures (Constitution: per-user data scoping; spec Clarification
session 2026-09-03 / FR-002).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | |
| `created_at` | timestamp | |

*The specific login/identification mechanism is a v1 implementation detail out of this feature's
functional scope beyond "a real, distinct user identity exists" — see `research.md` if a decision
is needed at implementation time; not blocking this data model, which only needs a stable
`user_id` to hang everything else off.*

## Architecture

A user-owned, named, reusable, priced design (spec Key Entities; FR-001, FR-002, FR-003).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → User) | Owner; not nullable |
| `provider` | enum (`aws`) | Explicit dimension per Constitution Principle III; only `aws` valid in v1, but the column exists so GCP/Azure are additive later, not a migration |
| `name` | text | Not empty |
| `deleted_at` | timestamp, nullable | Soft delete (FR-014); `NULL` = active |
| `created_at` / `updated_at` | timestamp | |

**Validation rules**: `name` required and non-empty. `provider` must be `aws` in v1 (enum
enforced at the DB and API layers so adding a provider later is an enum extension, not a schema
change).

## Collection

A user-defined grouping of AWS SKUs within an Architecture (spec Key Entities; FR-004).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | |
| `architecture_id` | UUID (FK → Architecture) | Not nullable |
| `type` | enum (`application_component`, `vpc`) | Exactly these two per FR-004 |
| `name` | text | Not empty |
| `deleted_at` | timestamp, nullable | Soft delete (FR-015) |
| `created_at` / `updated_at` | timestamp | |

**Validation rules**: `name` required. `type` restricted to the two enum values. A Collection
always belongs to exactly one Architecture (no cross-Architecture reuse in v1 — consistent with
"clone a global Architecture" being an explicitly deferred future feature, not something this
model needs to support yet).

## SKU Selection

A reference to one AWS pricing catalog SKU plus the user's pricing inputs for that occurrence
(spec Key Entities; FR-006, FR-007, FR-009).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | |
| `collection_id` | UUID (FK → Collection), nullable | Set when attached to a Collection |
| `connector_id` | UUID (FK → Data Connector), nullable | Set when attached to a Connector's service |
| `service_code` | text | AWS service code from the pricing catalog, e.g. `AmazonEC2` |
| `sku` | text | AWS SKU identifier from the pricing catalog (`product_dim.sku`) |
| `pricing_term` | enum (`on_demand`, `reserved_1yr`, `reserved_3yr`) | FR-007 |
| `purchase_option` | enum (`no_upfront`, `partial_upfront`, `all_upfront`, `not_applicable`) | FR-007; `not_applicable` for on-demand |
| `usage_quantity` | numeric | Unit implied by the SKU's `price_fact.unit` at calculation time (not duplicated here) |
| `created_at` / `updated_at` | timestamp | `updated_at` tracks "last-entered inputs" per Constitution's data-layer note |

**Validation rules**: Exactly one of `collection_id` / `connector_id` is set, never both, never
neither (DB check constraint) — a SKU Selection always belongs to exactly one parent. The same
`(service_code, sku)` may repeat any number of times, across the same or different Collections
(FR-006; Edge Cases) — no uniqueness constraint on that pair. `service_code`/`sku` are opaque
references, not validated against the catalog at write time beyond non-empty (the price
calculation step is what surfaces an unpriceable/unknown SKU per FR-012, not a foreign-key
constraint into a datastore this feature must not treat as relational per Principle II).

## Data Connector

A user-created, directed link between two distinct Collections within the same Architecture,
optionally with one attached SKU Selection (spec Key Entities; FR-008, FR-009).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | |
| `architecture_id` | UUID (FK → Architecture) | Redundant with the two Collections' `architecture_id` but kept for simpler scoping/query — both Collections must share this same Architecture (validated at write time) |
| `from_collection_id` | UUID (FK → Collection) | |
| `to_collection_id` | UUID (FK → Collection) | Must differ from `from_collection_id` (FR-008 self-connect rejection) |
| `deleted_at` | timestamp, nullable | Soft delete (FR-015); cascades from either endpoint Collection's soft delete |
| `created_at` / `updated_at` | timestamp | |

**Validation rules**: `from_collection_id != to_collection_id` (DB check constraint doubles the
FR-008 API-level rejection). Both Collections must belong to `architecture_id`. Treated as
non-directional for *pricing* purposes (research.md #2 / spec Assumptions) even though the
`from`/`to` fields exist structurally for the diagram; no additional directionality field is
modeled since nothing in scope needs it.

**Cascade rule**: soft-deleting a Collection (FR-015) also soft-deletes every Data Connector
where that Collection is `from_collection_id` or `to_collection_id`.

## State Transitions

Every soft-deletable entity (Architecture, Collection, Data Connector) has exactly one
transition in v1: **active → deleted** (`deleted_at` set). There is no "restore" transition —
not required by any FR, and explicitly not built per the spec's assumptions. SKU Selections are
hard-deleted when removed (they have no independent lifecycle value once detached — removing one
is just removing a line item, not a decision worth soft-delete semantics).

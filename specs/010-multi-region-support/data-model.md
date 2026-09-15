# Data Model: Multi-Region Collections and Region-Grouped Pricing

Source: spec.md Key Entities + Functional Requirements; grounded against `backend/src/models/orm.py` and `backend/src/models/schemas.py` (see research.md for file:line citations).

## Collection (modified)

Existing entity (`backend/src/models/orm.py:63-111`), type `vpc` or `application_component`.

| Field | Type | Notes |
|---|---|---|
| `region` | `str`, **NOT NULL** (new) | AWS region code (e.g. `us-east-1`). Set at creation (FR-001/FR-001a); immutable once locked (FR-003). Not a DB enum/FK — validated at the API layer against the live available-regions list (research.md §3), since the valid set changes with upstream data, not with app code. |

**Backfill** (FR-016): every pre-existing row gets the app's former single global pricing region via a 3-step Alembic migration (add nullable → `UPDATE` → set NOT NULL) — see research.md §1.

**Region-locking rule** (FR-003) — computed, not a stored flag:
```
locked(collection) :=
  EXISTS(SKUSelection WHERE collection_id = collection.id)
  OR (collection.type == "vpc" AND EXISTS(Collection AS child WHERE child.parent_collection_id = collection.id))
```
Enforced server-side by the new `PATCH /collections/{id}/region` endpoint (contracts/api.md) — `409 Conflict` if `locked`.

**Creation-time region resolution** (FR-001, FR-001a) — server-authoritative:
```
if parent_collection_id is given:
    region := parent VPC's region   # client-supplied region field, if any, is ignored
else:
    region := client-supplied region, validated against available-regions list
```

**Same-region nesting rule** (FR-004), evaluated whenever `parent_collection_id` is set or changed (creation with a parent, or the existing `PATCH .../parent_collection_id` endpoint):
```
valid_nest(application, vpc) := application.region == vpc.region
```
Enforced both client-side (`decideNestingChange`, extended — research.md §8) for immediate drag feedback, and server-side (`409 Conflict` on mismatch) as the authoritative gate.

## DataConnector (unchanged schema)

Existing entity (`backend/src/models/orm.py:114-144`) — `from_collection_id`/`to_collection_id`, both NOT NULL (existing CHECK constraint), optional one `SKUSelection`. No new fields. Two behavior changes, both presentation/derivation only:

- **Service search scope** (FR-006): the catalog search triggered for a Connector always uses `from_collection.region`.
- **Diagram rendering** (FR-009): rendered with a directional arrow (`markerEnd`) from `from_collection` toward `to_collection` — no data-model impact, edge-construction only (research.md §9).
- **Pricing attribution** (research.md §11): a Connector's own `SKUSelection`, if priced, is attributed to `from_collection.region` for the purposes of `PriceLineItem.region` grouping.

## PriceLineItem (modified)

Existing entity (`backend/src/models/schemas.py:184-189`), returned inside `CalculationResult.line_items`.

| Field | Type | Notes |
|---|---|---|
| `region` | `str \| None` (new) | Resolved server-side in `calculate_architecture_price` (research.md §11): Collection-owned selections use that Collection's `region`; Connector-owned selections use `from_collection.region`. Given `Collection.region` and `DataConnector.from_collection_id` are both NOT NULL, this is expected to always resolve to a real region in practice — `None` is a defensive fallback only (grouped under a "Global" section per FR-015), not a normally-reachable state. |

## AvailableRegions (derived, not a stored entity)

Not a database table. Computed on demand (research.md §3) by intersecting the `region=<code>` partition directories present under each of the 5 Parquet tables (`service_dim, product_dim, product_attribute, region_dim, price_fact`) at the latest snapshot date, mirroring the existing `resolve_latest_snapshot_date` pattern. Exposed via `GET /regions` (contracts/api.md). Used to:
- Populate the region-selection prompt (FR-001, FR-017).
- Validate a client-supplied `region` on collection creation/region-update (400 if not in the list).

## Region-Grouped Pricing Breakdown (frontend-only derived shape)

Not a backend entity — a pure frontend transform (`frontend/src/lib/regionPricingGroups.ts`, research.md §11) over `CalculationResult.line_items`:

```
type RegionPricingGroup = {
  region: string;           // or "Global" fallback label
  items: PriceLineItem[];   // preserves existing price-descending order (FR-014)
  subtotal: number;         // sum of items' price (FR-012)
};
```

Rendered by `PricingPanel.tsx` as one section per group, between the existing `Total` and `Data Timestamp` lines (FR-013), replacing the current single flat `PricePerSkuSection` list.

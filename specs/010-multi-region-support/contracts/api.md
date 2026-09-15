# API Contracts: Multi-Region Collections and Region-Grouped Pricing

All schema changes below are Pydantic-native (`backend/src/models/schemas.py`) per Constitution Principle IV — `check-api-types` MUST pass after each change, regenerating the corresponding TypeScript types consumed by `frontend/src/api/client.ts`.

## 1. `POST /architectures/{architecture_id}/collections` (modified)

**Request** `CollectionCreate` — was `{type, name}` (`schemas.py:96-98`):

```jsonc
{
  "type": "vpc" | "application_component",
  "name": "string",
  "region": "string | null",              // NEW — required unless parent_collection_id given
  "parent_collection_id": "uuid | null"    // NEW — application_component only; parent must be an existing vpc
}
```

**Server behavior** (research.md §6):
- If `parent_collection_id` is present: `type` must be `application_component`, the referenced collection must exist and be `type: vpc`; `region` is **ignored if supplied** and set to the parent VPC's actual region.
- If `parent_collection_id` is absent: `region` is required and validated against `GET /regions`' current list; `400` if not a currently-available region.

**Response** `CollectionOut` — was `{id, type, name, parent_collection_id, sku_selections}` (`schemas.py:101-106`), gains:

```jsonc
{ "...": "unchanged fields", "region": "string" }
```

**New error cases**: `400` — `region` missing (no parent given) or not in the available-regions list; `400` — `parent_collection_id` given but doesn't reference a `vpc`-type collection.

## 2. `PATCH /collections/{id}/region` (new)

Mirrors the existing per-field `PATCH .../parent_collection_id` convention (`client.ts:107-111`) rather than a generic collection-update endpoint (research.md §7's sibling reasoning: Principle VI — smallest addition consistent with existing style).

**Request**:
```jsonc
{ "region": "string" }
```

**Response**: `200` + updated `CollectionOut`.

**Errors**:
- `409 Conflict` — collection is locked (data-model.md's `locked(collection)`, FR-003): has at least one `SKUSelection`, or (VPC only) at least one child `Collection`.
- `400` — `region` not in the current `GET /regions` list.
- `404` — collection not found.

## 3. `PATCH /collections/{id}/parent_collection_id` (modified — new error case)

Existing endpoint (`client.ts:107-111`, `api.updateCollectionParent`) — request/response shape unchanged. New validation (FR-004, research.md §8):

**New error case**: `409 Conflict` — the dragged/target Application's `region` does not match the destination VPC's `region`. Response body includes both regions so the frontend can render a specific message (e.g. `{"detail": "region_mismatch", "application_region": "us-east-1", "vpc_region": "eu-west-1"}`).

## 4. `GET /catalog/skus` (modified)

Existing endpoint (`backend/src/api/catalog.py:13-37`). Adds one new **required** query param, distinct from the existing `from_region_code`/`to_region_code` (research.md §5):

| Param | Type | Notes |
|---|---|---|
| `region` | `string`, required | Which Parquet partition to search — the selected collection's region (FR-005), or a connector's `from_collection.region` (FR-006). Unrelated to `from_region_code`/`to_region_code`, which remain AWSDataTransfer attribute filters, untouched by this feature. |

**New error case**: `400` — `region` not in the current `GET /regions` list.

## 5. `GET /regions` (new)

Returns the regions the pricing dataset currently has data for (research.md §3 — derived from Parquet partition directories, intersected across all 5 tables at the latest snapshot; no DuckDB query, no caching layer).

**Response**:
```jsonc
{ "regions": [{ "code": "us-east-1" }, { "code": "eu-west-1" }, "..."] }
```

## 6. Pricing calculation endpoint (modified response)

Whichever existing endpoint returns `CalculationResult` (backend/src/services/price_calculation.py's consumer route) — `PriceLineItem` (`schemas.py:184-189`) gains one field:

```jsonc
{ "...": "unchanged (sku_selection_id, service_code, sku, price, priceable)", "region": "string | null" }
```

`null` is a defensive fallback only (data-model.md) — not expected in normal operation given `Collection.region` and `DataConnector.from_collection_id` are both NOT NULL.

## Frontend API client changes (`frontend/src/api/client.ts`)

- `createCollection(architectureId, type, name, region?, parentCollectionId?)` — signature extended (was `(architectureId, type, name)`, `client.ts:99-103`).
- `updateCollectionRegion(collectionId, region)` — **new**, mirrors `updateCollectionParent` (`client.ts:107-111`).
- `updateCollectionParent(...)` — signature unchanged; caller must now handle a `409` region-mismatch response.
- `searchCatalog({..., region})` — `region` added as a required param alongside existing `from_region_code`/`to_region_code` (`client.ts:113-119`).
- `listRegions()` — **new**.

# Phase 1 API Contract: AWS Architecture Assembly & Pricing

This is the design-time contract. The authoritative, always-current contract is the OpenAPI
schema FastAPI generates from the backend's Pydantic models at runtime (Constitution Principle
IV) — this document exists so frontend and backend work can start from the same shared shape
before that code exists, and to trace every endpoint back to the functional requirement(s) it
satisfies. All endpoints are implicitly scoped to the authenticated user (FR-002); no endpoint
accepts or returns another user's data.

Base path: `/api/v1`

## Providers

### `GET /providers`

Returns the provider list for the landing page's selector (FR-003).

**Response** `200`:
```json
[
  {"code": "aws", "name": "AWS", "active": true},
  {"code": "gcp", "name": "GCP", "active": false},
  {"code": "azure", "name": "Azure", "active": false}
]
```

## AWS Pricing Catalog (read-only, DuckDB-backed)

### `GET /catalog/skus`

Search the AWS pricing catalog (FR-005). All filters are optional and combine with AND;
omitting all filters is rejected (`400`) to avoid returning the full ~173k-row catalog.

**Query params**: `service_code` (exact), `product_family` (exact), `q` (free text over
service/product name), `limit` (default 50, max 200), `cursor` (opaque pagination token).

**Response** `200`:
```json
{
  "results": [
    {
      "service_code": "AmazonEC2",
      "service_name": "Amazon Elastic Compute Cloud",
      "product_family": "Compute Instance",
      "sku": "7MS6E9W2YWKJZRX5",
      "summary": "c3.xlarge, Linux, Shared tenancy"
    }
  ],
  "next_cursor": "..." ,
  "snapshot_date": "2026-09-03"
}
```

**Error** `503`: pricing data source unreachable (FR-018) — distinct from a `200` with an empty
`results` array (Edge Cases: "no results" vs. a real outage are never the same response shape).

## Architectures

### `POST /architectures`

Create an Architecture (FR-001, FR-002, FR-003).

**Request**: `{"name": "string", "provider": "aws"}` — `provider` other than `"aws"` → `400`.

**Response** `201`: the created Architecture.

### `GET /architectures?provider=aws`

List the current user's non-deleted Architectures for a provider (FR-013).

**Response** `200`: array of Architecture summaries (id, name, provider, created_at).

### `GET /architectures/{id}`

Get one Architecture with its Collections and Data Connectors (for the Create Architecture page).

**Response** `200`: Architecture + nested `collections[]` (each with its `sku_selections[]`) +
`connectors[]` (each with its optional attached `sku_selection`).
**Error** `404`: not found, not owned by the caller, or soft-deleted.

### `DELETE /architectures/{id}`

Soft-delete an Architecture after confirmation (FR-014). Idempotent: deleting an
already-deleted Architecture returns `204`.

## Collections

### `POST /architectures/{id}/collections`

Add a Collection to an Architecture (FR-004).

**Request**: `{"type": "application_component" | "vpc", "name": "string"}`

**Response** `201`: the created Collection.

### `DELETE /collections/{id}`

Soft-delete a Collection (FR-015); cascades to soft-delete any Data Connector referencing it
(data-model.md Cascade rule).

## SKU Selections

### `POST /collections/{id}/sku-selections`

Add an AWS SKU to a Collection with its pricing inputs (FR-006, FR-007).

**Request**:
```json
{
  "service_code": "AmazonEC2",
  "sku": "7MS6E9W2YWKJZRX5",
  "pricing_term": "on_demand",
  "purchase_option": "not_applicable",
  "usage_quantity": 730
}
```

**Response** `201`: the created SKU Selection.

### `PATCH /sku-selections/{id}`

Update an existing SKU Selection's pricing inputs (any subset of `pricing_term`,
`purchase_option`, `usage_quantity`).

### `DELETE /sku-selections/{id}`

Remove a SKU Selection (hard delete — see data-model.md State Transitions).

## Data Connectors

### `POST /architectures/{id}/connectors`

Create a Data Connector between two Collections in the same Architecture (FR-008).

**Request**: `{"from_collection_id": "uuid", "to_collection_id": "uuid"}`
**Error** `400`: `from_collection_id == to_collection_id`, or either Collection does not belong
to this Architecture.

**Response** `201`: the created Data Connector.

### `POST /connectors/{id}/sku-selection`

Attach (or replace) the single AWS SKU on a Data Connector, with its pricing inputs (FR-009).
Same request/response shape as `POST /collections/{id}/sku-selections`.

### `DELETE /connectors/{id}`

Soft-delete a Data Connector (FR-015).

## Price Calculation

### `POST /architectures/{id}/calculate`

Calculate the Architecture's total price (FR-010, FR-011, FR-012, FR-017, FR-018).

**Response** `200`:
```json
{
  "snapshot_date": "2026-09-03",
  "total_price": 412.18,
  "currency": "USD",
  "line_items": [
    {"sku_selection_id": "uuid", "service_code": "AmazonEC2", "sku": "...", "price": 45.90, "priceable": true}
  ],
  "unpriceable": [
    {"sku_selection_id": "uuid", "service_code": "AmazonRDS", "sku": "...", "reason": "no price for term/purchase_option in current snapshot"}
  ],
  "warnings": [
    {"code": "unconnected_vpcs", "message": "2 VPC collections have no Data Connector between them"}
  ]
}
```
`total_price` sums only `priceable` line items (FR-012: unpriceable SKUs are flagged, not
silently omitted from the response, but they cannot contribute an estimated number to the
total). `warnings` carries the FR-017 unconnected-VPCs case; it never blocks the `200` response.

**Error** `503`: pricing data source unreachable during calculation (FR-018).

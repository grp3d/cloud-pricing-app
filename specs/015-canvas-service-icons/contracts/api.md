# API Contract Changes: 015-canvas-service-icons

The only change is **one additive, optional field** on the existing `SKUSelectionOut` schema. It
adds no new endpoints, changes no request bodies, and makes no breaking changes.

## `SKUSelectionOut`: add `product_family`

```jsonc
{
  "id": "uuid",
  "service_code": "AmazonEC2",
  "sku": "ABCD1234EFGH5678",
  "pricing_term": "OnDemand",
  "purchase_option": "No Upfront",
  "usage_quantity": "730",
  "unit": "Hrs",
  "attributes": { "usagetype": "USE1-NatGateway-Hours", "operation": "NatGateway", "...": "..." },
  "product_family": "NAT Gateway"   // NEW — string | null
}
```

| Field | Type | Required | Semantics |
|---|---|---|---|
| `product_family` | `string \| null` | no (default `null`) | The SKU's `product_family` from the pricing catalog (Parquet `product_dim`), resolved read-only at response time using the same region scoping as `attributes`. `null` when the SKU has no matching catalog row or its product family is empty. Never persisted. |

### Endpoints whose responses carry it (all existing)

Every `SKUSelectionOut` in the following responses is affected:

- `GET /architectures/{architecture_id}`: every `collections[].sku_selections[]` and
  `connectors[].sku_selection`. This is batch-resolved with one lookup per distinct region.
- `POST /collections/{collection_id}/sku-selections` (create)
- `PATCH /sku-selections/{sku_selection_id}` (update)
- `PUT`/`POST` connector SKU-selection attach in `connectors.py` (the `response_model=SKUSelectionOut`
  route)

### Type-safety (Principle IV)

- The field is declared on the Pydantic model in `backend/src/models/schemas.py`.
- `frontend/src/api/generated/schema.d.ts` is regenerated (`npm run generate-api-types`).
  `npm run check-api-types` must pass in CI.

### Contract tests to add (written first)

1. `GET /architectures/{id}` for an architecture with an EC2 NAT Gateway SKU returns
   `product_family == "NAT Gateway"` on that selection.
2. A selection whose SKU is missing from the snapshot returns `product_family: null`, and
   `attributes: {}` is unchanged.
3. Create and update SKU-selection responses include `product_family`.
4. A data-transfer selection resolves `product_family` using `fromRegionCode` scoping, the same as
   `attributes`.

## Not changed

- `POST /architectures/{id}/calculate` and the snapshot-calculation endpoint have the same request
  and response. Per-architecture result storage is entirely client-side.
- Architecture export/import definitions (014) are unchanged. `product_family` is response-only
  and is not part of `SKUSelectionDefinition`.

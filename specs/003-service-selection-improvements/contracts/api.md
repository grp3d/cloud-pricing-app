# Phase 1 API Contract: Service Selection Improvements

This is a delta on `001`'s and `002`'s contracts — two response shapes gain fields; **no new
endpoint**, no changed request shape, no changed status codes. As always, the authoritative
contract is the live OpenAPI schema FastAPI generates; this document traces the change back to
its requirement before the code exists.

## Changed: `CatalogSKUOut` (`GET /catalog/skus` results)

Adds two fields:

```json
{
  "service_code": "AmazonEC2",
  "service_name": "Amazon Elastic Compute Cloud",
  "product_family": "Compute Instance",
  "sku": "NN4EGUUQRWVYP98C",
  "summary": "t3.medium",
  "attributes": {
    "instanceType": "t3.medium",
    "vcpu": "2",
    "memory": "4 GiB",
    "operatingSystem": "Linux",
    "...": "..."
  },
  "unit": "Hrs"
}
```

- `attributes`: the SKU's full descriptive attributes as a flat key/value map (spec FR-001,
  FR-002). Empty map `{}` if none are available (spec FR-003) — never `null`.
- `unit`: the SKU's billing unit (spec FR-004, FR-005), e.g. `"Hrs"`, `"GB-Mo"`, `"Requests"`.
  `null` if no price data exists for this SKU at all (the same condition that makes a SKU
  unpriceable per `001`'s FR-012).

## Changed: `SKUSelectionOut` (used by `POST`/`PATCH .../sku-selections`,
`POST .../connectors/{id}/sku-selection`, and nested inside `GET /architectures/{id}`)

Adds one field:

```json
{
  "id": "uuid",
  "service_code": "AmazonEC2",
  "sku": "NN4EGUUQRWVYP98C",
  "pricing_term": "on_demand",
  "purchase_option": "not_applicable",
  "usage_quantity": "730.0000",
  "unit": "Hrs"
}
```

- `unit`: same meaning as above, resolved fresh for the SKU this selection references (spec
  FR-004, FR-005). `null` under the same condition as `CatalogSKUOut.unit`.

No other part of `001`'s or `002`'s contract changes — every existing request shape, status
code, and error condition is unchanged.

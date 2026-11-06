# API Contract Changes: 020

Both changes are additive. Older clients keep working unchanged. Frontend types are regenerated
from the OpenAPI schema (Principle IV).

## 1. `POST /api/v1/catalog/calculate-snapshot` (request gains fields)

Request:

```json
{
  "duration": "yearly",
  "provider": "gcp",
  "selections": [
    {
      "service_code": "6F81-5844-456A",
      "sku": "<core sku id>",
      "pricing_term": "OnDemand",
      "purchase_option": "No Upfront",
      "usage_quantity": "730",
      "region": "us-east1",
      "provider_options": {
        "kind": "gcp_machine", "version": 1, "vcpus": 4, "memory_gib": "16", "ram_sku": "<ram sku id>"
      }
    }
  ]
}
```

**New fields**

| Field | Required | Default when missing | Meaning |
|---|---|---|---|
| `provider` | no | `aws` | The architecture's provider |
| `selections[].region` | no | `AWS_PRICING_REGION` (today's behaviour) | The region the selection was priced in |
| `selections[].provider_options` | no | none | The selection's provider-specific options |

**Response:** unchanged (`CalculationResult`). The total comes from the same pricing path as every
other calculation.

**Errors**

| Status | Cause |
|---|---|
| 400 `empty_snapshot` | Empty `selections`, as today |
| 422 | `provider_options.kind` doesn't match `provider`, or the options are invalid |
| 503 | The provider has no active snapshot, the same body as other pricing endpoints |

## 2. SKU selection responses gain `service_name`

Every response that returns `SKUSelectionOut` gains:

```json
{ "service_name": "Compute Engine" }
```

These are the architecture detail, collection and connector payloads.

- `service_name` is a string, or null when the SKU isn't in the active snapshot.
- It is read-only and never accepted on create or update.

## Not changed

- No new endpoints.
- No changes to selection create or update, connectors, export/import format, preferences or
  Trends.
- Icons are chosen entirely in the frontend from checked-in generated maps; no API carries icon
  data.

# Phase 1 API Contract: Canvas & Pricing Improvements

This is a delta on `001`-`003`'s contracts — one existing endpoint gains an optional query
parameter, two response shapes are enriched. **No new endpoint.** As always, the authoritative
contract is the live OpenAPI schema FastAPI generates; this document traces the change back to
its requirement before the code exists.

## Changed: `POST /architectures/{id}/calculate`

Gains one optional query parameter:

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `duration` | `CalculationDuration` (`"1_day"` \| `"1_month"` \| `"1_year"`) | `"1_month"` | The period the total is scoped to (spec FR-001). Existing callers that don't pass it get a month-scoped total rather than a breaking change. |

## Changed: `CalculationResult`

Adds one field:

```json
{
  "snapshot_date": "2026-09-08",
  "duration": "1_month",
  "total_price": "142.50",
  "currency": "USD",
  "line_items": [ /* ... */ ],
  "unpriceable": [ /* ... */ ],
  "warnings": [ /* ... */ ]
}
```

- `duration`: echoes the `CalculationDuration` the total was computed for (spec FR-001).

`total_price` and each `line_items[].price` now reflect the **duration-scaled** cost per spec
FR-002/FR-003/FR-004 — a Reserved-term line item's `price` is its full-term cost prorated to
`duration`; an on-demand `no_period`-unit line item's `price` is its entered quantity treated as
a daily rate scaled to `duration`; an on-demand `fixed_period`-unit line item's `price` is scaled
between that unit's own period and `duration`. When every line item is excluded, `total_price` is
`"0.00"` (spec Clarifications — not a distinct empty state).

## Changed: `UnpriceableItem`

Now covers both today's "no price" case and the new duration-unrecognized-unit case (spec
FR-005), in **one combined list** (spec Clarifications) — adds one field:

```json
{
  "sku_selection_id": "uuid",
  "service_code": "AmazonMWAA",
  "sku": "6FW89S9DDHFSFGM2",
  "reason": "no price for term/purchase_option in current snapshot",
  "components": ["us-west-1 vpc B"]
}
```

- `components`: the name(s) of the Architecture component(s) (Application Component(s) or
  VPC(s)) containing this service (spec FR-012), or a single string describing the Data
  Connector (e.g. `"Data Connector between App A and App B"`) when the selection is attached to
  a connector rather than a Collection (spec FR-013).
- `reason` distinguishes the two cases textually — the existing
  `"no price for term/purchase_option in current snapshot"` for today's case, and a new
  `"billing unit 'X' isn't recognized as time-based; excluded from the N-day total"`-style
  message for the FR-005 case. No new schema for the second case (spec Clarifications: one
  combined list).

## Changed: `SKUSelectionOut` (used by `POST`/`PATCH .../sku-selections`,
`POST .../connectors/{id}/sku-selection`, and nested inside `GET /architectures/{id}`)

Adds one field, mirroring `003`'s `CatalogSKUOut.attributes`:

```json
{
  "id": "uuid",
  "service_code": "AmazonEC2",
  "sku": "NN4EGUUQRWVYP98C",
  "pricing_term": "on_demand",
  "purchase_option": "not_applicable",
  "usage_quantity": "730.0000",
  "unit": "Hrs",
  "attributes": {
    "instanceType": "t3.medium",
    "vcpu": "2",
    "memory": "4 GiB",
    "...": "..."
  }
}
```

- `attributes`: same meaning and shape as `003`'s `CatalogSKUOut.attributes` — the SKU's full
  descriptive attributes as a flat key/value map, resolved fresh for the SKU this selection
  references (spec FR-014). Empty map `{}` (never `null`) when unavailable.

No other part of `001`-`003`'s contract changes — every other existing request shape, status
code, and error condition is unchanged.

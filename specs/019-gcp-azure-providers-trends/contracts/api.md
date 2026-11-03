# API Contract Changes: 019-gcp-azure-providers-trends

These are FastAPI routes. Request and response shapes are Pydantic models, and the frontend types are generated from OpenAPI (`npm run generate-api-types`), so a mismatch fails the type check (Principle IV).

**Compatibility rule**: every existing route keeps its path. A missing `provider` means `aws`, and new fields are optional, so today's AWS behavior and clients are unchanged.

All routes need the existing identity: a named or guest user, the same as today. HTTP 503 with a per-provider reason is returned when that provider has no usable snapshot.

---

## 1. Providers

### `GET /providers` (changed)

```jsonc
[
  { "code": "aws", "name": "AWS", "active": true,
    "status": "current",                  // current | partial | failed | stale | none
    "reason": null,                       // short public phrase when not current
    "snapshot_date": "2026-10-26", "snapshot_revision": 1 },
  { "code": "azure", "name": "Azure", "active": false, "status": "none",
    "reason": "no snapshot available", "snapshot_date": null, "snapshot_revision": null }
]
```

- **`active`**: true exactly when the provider has a usable active snapshot (FR-001).
- **`stale`**: the active snapshot is older than `SNAPSHOT_STALE_DAYS`, a new setting with default 14 (two missed weekly runs). A stale provider stays active and shows the reason.

## 2. Regions

### `GET /regions?provider=<code>` (changed)

The response is unchanged, plus `display_name` per region. The list holds the provider's selectable regions (research R5). `global` and Azure geographies are never listed.

## 3. Catalog search

### `GET /catalog/skus?provider=<code>&region=…&q=…&service_code=…&product_family=…&kind=…&limit=…&offset=…` (changed)

- **`provider`**: new parameter, default `aws`.
- **`product_family`**: the provider's grouping filter. Azure: `product_name`. GCP: a taxonomy path segment.
- **`kind`** (optional): `vm`, `block_storage`, `object_storage`, `data_transfer` or `managed_db`. It applies the reference-lookup filters for that kind (R6).
- **AWS-only parameters**: `from_region_code` and `to_region_code`. Sending them for another provider returns HTTP 422.

`CatalogSKUOut` gains optional fields:

```jsonc
{
  "provider": "gcp",
  "service_code": "6F81-5844-456A",          // GCP service_id
  "service_name": "Compute Engine",
  "product_family": "Compute > GCE > VMs On Demand > Cores: Per Core",
  "sku": "BB77-5FDA-69D9",
  "summary": "N2 Instance Core running in Americas",
  "attributes": { "geo_taxonomy_type": "TYPE_MULTI_REGIONAL" },
  "unit": "h",
  "location_scope": "multi_regional",       // regional | multi_regional | global
  "kind": "vm",                             // null when not a tuned kind
  "price_types": ["on_demand", "commitment_1yr", "commitment_3yr"]
}
```

## 4. SKU selections

### `POST /collections/{id}/sku-selections`, `PATCH /sku-selections/{id}`, connector selection routes (changed)

- **`pricing_term`**: accepts the widened enum (R6).
- **`provider_options`**: an optional discriminated union (`gcp_machine`, `azure_vm`).
- **HTTP 422 cases**, each with a field-level message:
  - a price type the item doesn't publish;
  - options that don't match the architecture's provider;
  - a `purchase_option` other than `not_applicable` for Azure or GCP.

## 5. Calculation

### `POST /architectures/{id}/calculate`, `POST /calculate/snapshot` (changed)

- **Snapshot**: the architecture's provider picks the snapshot. The result's `snapshot_date` and `snapshot_revision` are that provider's (FR-003).
- **`PriceLineItem`** gains:
  - `price_type_label`;
  - `tiers`: a list of `{from_quantity, to_quantity, rate, quantity, cost}`, or null when not tiered (R8). This applies to all three providers, so AWS lines with tiered prices gain it too, and their cost becomes the sum of the tier parts;
  - `components`: for `gcp_machine`, the core and RAM parts.
- **Missing prices**: still reported as `UnpriceableItem` with the reason "not published" (FR-007).

## 6. Connectors

### `POST /architectures/{id}/connectors`, `PATCH /connectors/{id}` (changed)

New optional fields: `arrow_style`, `arrow_reversed`.

### `POST /connectors/{id}/branches`, `DELETE /connectors/{id}/branches/{collection_id}` (new)

- **Adding a branch**: requires `arrow_style` to be `one_to_many` or `many_to_one`, and the collection to be in the same architecture and not already linked.
- **Removing a branch**: when it leaves 2 boxes, the response shows the connector with `arrow_style: "one_way"` (data-model §5).

`DataConnectorOut` gains `arrow_style`, `arrow_reversed` and `branch_collection_ids` (in order).

## 7. Preferences

### `GET /me/preferences` (new)

Returns `{ "schema_version": 1, "data": Preferences }`, where `Preferences` is defined in data-model §1. With no row yet, it returns the empty defaults.

### `PATCH /me/preferences` (new)

The body has one or more of the top-level sections, and each one sent replaces that section. It returns the full stored preferences. Unknown keys and invalid values return HTTP 422.

## 8. Trends

### `GET /trends/series` (new)

Query: `category=all|compute|storage|database|networking`, and one or more `select=<provider>:<region,region,…>` (an empty region list means all regions), plus an optional `weeks` (default 52).

```jsonc
{
  "metric": "skus_changed",                 // the only metric in this version
  "category": "compute",
  "series": [
    {
      "provider": "aws", "regions": ["us-east-1", "us-west-2"],
      "status": "ok",                       // ok | building | not_enough_history | provider_unavailable
      "weeks_built": 52,                    // with status building: weeks built so far, of weeks_total
      "weeks_total": 52,
      "points": [
        { "week": "2026-10-26", "from_snapshot": "2026-10-19 r1", "to_snapshot": "2026-10-26 r1",
          "increased": 3, "decreased": 41,  // SKU counts
          "increased_pct": 0.0004, "decreased_pct": 0.005,  // % of compared
          "compared": 812345, "excluded": 120,
          "gap": false }                    // true when a week is missing in between
      ]
    }
  ]
}
```

A week with no compared SKUs gets null counts and percentages, shown as "no data", never 0.

`building` means the history backfill is still running for that provider: `points` holds the weeks built so far, and the page shows "building history (n of m weeks)".

A global-only item counts once per provider, as location `global`, whenever the selection covers all regions or at least one region of that provider (spec Edge Cases).

### `GET /trends/movers` (new)

Query: `provider`, `category`, `regions` (comma list; empty means all), `period_weeks=1|4|13|52`.

```jsonc
{
  "provider": "aws", "category": "compute", "regions": [],
  "from_snapshot": "2025-10-27 r1", "to_snapshot": "2026-10-26 r1",
  "weeks_available": 52,                    // < period when history is shorter
  "increases": [
    { "service_name": "Amazon EC2", "description": "m7i.large Linux On Demand", "region": "us-east-1",
      "unit": "Hrs", "start_price": "0.1008", "end_price": "0.1058", "change_pct": 4.96,
      "tier_note": null }
  ],
  "decreases": [],
  "message": null                           // "No price changes in this period" when both are empty
}
```

Prices are decimal strings exactly as published (FR-019). `change_pct` is rounded to 2 decimal places.

## 9. Admin

### `GET /admin/system` (changed)

Snapshot, latest run, rejection and issues become per provider. A `history` block per provider is added:

```jsonc
{
  "providers": {
    "aws": { "active_snapshot": { … }, "latest_run": { … }, "rejected": null, "issues": [],
             "history": { "weeks_built": 52, "gaps": ["2026-03-02"], "backfill": "done",
                          "last_error": null } }
  }
}
```

# Phase 1 Data Model: Canvas & Pricing Improvements

**No Postgres schema change.** Every entity defined in `001`'s data model and extended by `002`
and `003` is unchanged — no new column, no new table, no new migration. This feature adds
request-time-resolved facts (from the existing read-only DuckDB/Parquet pricing data) and one
request parameter, following the exact pattern `003` already established for `unit`.

## Calculation Duration *(new, not persisted)*

A user's choice of `1_day` | `1_month` | `1_year`, sent as a query parameter on
`POST /architectures/{id}/calculate`. Not a database entity — never stored with the Architecture
(spec Edge Cases, Assumptions), consistent with how canvas box position/sizing already aren't
persisted.

| Value | Day-count used throughout this feature (spec FR-006) |
|---|---|
| `1_day` | 1 |
| `1_month` | 31 |
| `1_year` | 365 |

## AWS Pricing Catalog *(existing entity, extended read shape only — see `001`, `003`)*

Two additional facts, both resolved read-only at request time, never persisted:

| Field | Resolved from | Exposed on |
|---|---|---|
| Billing-unit time-period classification | A fixed lookup table (`no_period` / `fixed_period(days)` / `unrecognized`) keyed by the `unit` string `003` already resolves via `resolve_units` | Used internally by price calculation only — not a new response field, just an input to FR-002/003/004/005's proration math |
| `attributes` (per already-added SKU Selection) | `product_dim.attributes_json`, parsed the same way `003` already parses it for catalog search results, via a new batched `resolve_attributes(skus)` lookup | `SKUSelectionOut` (wherever it's already returned — single-object endpoints and the nested Architecture tree), mirroring how `003` attached `unit` |

**Rules** (mirroring `003`'s `data-model.md` rules for `unit`):

- Both are resolved **read-only**, using the same snapshot-pinning discipline `001` established
  (`resolve_latest_snapshot_date()`) — no new snapshot-selection logic.
- A billing unit outside the recognized classification table is `unrecognized` — that selection's
  cost is excluded from the duration-scoped total and listed with a reason (spec FR-005), never
  guessed or defaulted to either bucket.
- `SKUSelectionOut.attributes` is `{}` (never `null`) when unavailable, matching
  `CatalogSKUOut.attributes`'s existing contract from `003`.

## Calculation Result *(existing entity, extended response shape — see `001`)*

No new Postgres-backed entity — `CalculationResult` and `UnpriceableItem` are response shapes
built fresh on every calculate call, same as today. Two changes:

| Field | Meaning |
|---|---|
| `CalculationResult.duration` | Echoes back which `CalculationDuration` the total was computed for (spec FR-001), so a response is self-describing without the caller needing to remember what it asked for. |
| `UnpriceableItem.components` | The name(s) of the Architecture component(s) — Application Component(s) or VPC(s) — containing the excluded/unpriceable service, or a Data-Connector description when the selection is attached to a connector rather than a Collection (spec FR-012, FR-013). Derived from relationships already loaded for the calculation (`architecture.collections`/`architecture.connectors`) — no new query. |

`PriceLineItem.price` now reflects the **duration-scaled** cost (per FR-002/003/004/005), not
the raw `unit_price × usage_quantity` `001` originally computed — its meaning changes with this
feature, though its shape (`Decimal | None`) does not.

## Unaffected by this feature

- **Collection, Data Connector, SKU Selection (Postgres columns), User, Architecture**: no
  change. `SKUSelectionOut.attributes` is a response-shape addition only, same as `003`'s `unit`
  — the underlying `SKUSelection` row still stores only `service_code`/`sku`/pricing inputs.
- **Nesting depth**: `Collection.parent_collection_id` and its constraints are unchanged — this
  feature does not add new nesting relationships (spec Assumptions); the cascading-resize logic
  (frontend-only, `nodeLayout.ts`) is written to handle however many levels exist without the
  data model itself changing.

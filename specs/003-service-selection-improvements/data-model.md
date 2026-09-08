# Phase 1 Data Model: Service Selection Improvements

**No Postgres schema change.** Every entity defined in
`specs/001-assemble-price-aws-architecture/data-model.md` and extended in
`specs/002-vpc-component-nesting/data-model.md` is unchanged — no new column, no new table, no
new migration. This feature adds two pieces of information that are resolved from the existing
read-only DuckDB/Parquet pricing data at request time and never persisted, per Constitution
Principle II.

## AWS Pricing Catalog *(existing entity, extended read shape only — see 001)*

Two additional facts are now read and exposed alongside what `001` already exposed:

| Field | Resolved from | Exposed on |
|---|---|---|
| `attributes` | `product_dim.attributes_json` (parsed to a plain key/value map) | `CatalogSKUOut` (catalog search results) |
| `unit` | `price_fact.unit` for that SKU (any term — a SKU's metering unit does not vary by commitment term) | `CatalogSKUOut` (catalog search results) **and** `SKUSelectionOut` (an already-added SKU Selection, wherever it's returned) |

**Rules**:

- Both are resolved **read-only**, from the same snapshot-pinning discipline `001` already
  established (`research.md` #2 in `001`) — no new snapshot-selection logic needed here, the
  existing `resolve_latest_snapshot_date()` continues to apply.
- If a SKU has no `attributes_json` content, `attributes` is an empty map, not `null` — the
  frontend renders the spec's "no additional details available" state (FR-003) for an empty
  map, keeping the contract simple (always a map, never a nullable field to special-case).
- If a SKU has no resolvable `unit` (no matching `price_fact` row at all — the same condition
  that already makes a SKU "unpriceable" per `001`'s FR-012), `unit` is `null`. The frontend
  shows no unit label rather than a placeholder (spec FR-005 — never a generic/fabricated unit).
- `unit` on `SKUSelectionOut` is resolved fresh on every read (batched per request — see
  `research.md` #3), not cached or stored — consistent with `001`'s Principle I requirement that
  every price-adjacent fact stay live-traceable to the current snapshot.

## Unaffected by this feature

- **Collection, Data Connector, SKU Selection (Postgres columns), User, Architecture**: no
  change. `SKUSelectionOut.unit` is a response-shape addition only — the underlying
  `SKUSelection` row still stores only `service_code`/`sku`/pricing inputs, exactly as `001`
  defined.
- **Price calculation**: `unit` is informational for data entry; it plays no role in
  `price_calculation.py`'s math, which already resolves price directly from `pricing_term`/
  `purchase_option`/`usage_quantity` without needing to know the unit's label.

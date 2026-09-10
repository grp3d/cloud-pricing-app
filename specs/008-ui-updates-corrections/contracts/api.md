# Phase 1 API Contract: UI Updates and Corrections

A delta on `001`-`007`'s contracts — one existing endpoint's filtering semantics and
response shape change, and one new, stateless endpoint is added. As always, the
authoritative contract is the live OpenAPI schema FastAPI generates; this document traces
the change back to its requirement before the code exists.

## Changed: `GET /api/v1/catalog/skus`

Filtering semantics change (spec FR-020, research.md §2): `service_code` and
`product_family` move from **exact match** to **regex match**; `q` (free text) moves from
`ILIKE` substring match to **regex match**. All three are case-insensitive. Every existing
plain-text search (no regex metacharacters) returns the same results it always did — a
literal string is itself a valid regex matching that same substring. Query parameters
themselves are unchanged in name/type/default.

New failure mode: a syntactically invalid pattern in `service_code`, `product_family`, or
`q` now returns **400** (previously, exact/substring matching had no such failure mode —
any string was valid input):

```json
{
  "error": "invalid_regex_pattern",
  "message": "Invalid regex pattern in 'service_code': unterminated character class",
  "field": "service_code"
}
```

- `field`: which of `service_code` \| `product_family` \| `q` contained the invalid
  pattern (spec FR-021) — lets the caller show the error next to the right input rather
  than as a generic message.

`limit` is unchanged in type/range (`1`-`200`, existing clamp) — spec FR-023 changes only
the *frontend's* requested/default value (50 → 200), not this endpoint's own ceiling
(research.md §4).

## Changed: `CatalogSearchResult`

Adds one field (spec FR-024, research.md §3):

```json
{
  "results": [ /* ... */ ],
  "next_cursor": null,
  "snapshot_date": "2026-09-10",
  "total": 37
}
```

- `total`: the true count of catalog rows matching the current filters, independent of how
  many are present in `results` (capped at the request's `limit`). Always present, always
  exact — never an estimate (Constitution Principle I). When `results.length == total`,
  every match is already displayed.

## New: `POST /api/v1/catalog/calculate-snapshot`

Stateless — takes no `architecture_id`, persists nothing, requires no ownership check
beyond the existing `CurrentUser` auth dependency every endpoint already uses. Prices an
arbitrary, caller-supplied set of SKU selections at a given duration, using the exact same
pricing-lookup code path `POST /architectures/{id}/calculate` uses (spec FR-016a,
research.md §5) — this exists specifically to compute a duration-adjusted comparison total
for Price Change (spec FR-015/016/016a) when both the architecture's contents and the
Duration selection have changed since the last accepted calculation.

**Request**:

```json
{
  "duration": "1_year",
  "selections": [
    {
      "service_code": "AmazonEC2",
      "sku": "NN4EGUUQRWVYP98C",
      "pricing_term": "reserved_1yr",
      "purchase_option": "all_upfront",
      "usage_quantity": "1"
    }
  ]
}
```

- `duration`: same `CalculationDuration` enum as the existing calculate endpoint.
- `selections`: non-empty (400 if empty — an empty snapshot has no meaningful price to
  compute); each entry is the same shape `POST .../sku-selections` already accepts
  (`service_code`, `sku`, `pricing_term`, `purchase_option`, `usage_quantity`), with no
  `id` and no relationship to any live Collection/Connector — this is a value, not a
  reference.

**Response**: exactly `CalculationResult` — identical shape to
`POST /architectures/{id}/calculate`'s response, so the frontend's existing
result-rendering code needs no special-casing for a snapshot-derived result. `line_items`
in this response carry no meaningful `sku_selection_id` continuity guarantee with any live
Architecture (there is no live Architecture involved) — callers needing to correlate a line
item back to a specific prior selection should rely on `(service_code, sku)` pairing, not
`sku_selection_id`, when consuming this endpoint's response specifically.

**Error**: empty `selections` → 400:

```json
{ "error": "empty_snapshot", "message": "selections must contain at least one entry" }
```

No other part of `001`-`007`'s contract changes — every other existing request shape,
status code, and error condition is unchanged. In particular, `POST
/architectures/{id}/calculate` itself is untouched by this feature (FR-015/016's
non-duration-adjusted case reuses the frontend's already-stored Prior Calculation total
directly, with no new call to any endpoint).

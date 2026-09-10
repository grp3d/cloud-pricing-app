# Data Model: UI Updates and Corrections

No Postgres schema changes. No new domain entities in the Constitution Principle II sense
(vendor pricing data / user-defined data) — everything below is either a small addition to
an existing API response shape, a new stateless calculation request, or frontend-only
`localStorage`-resident view state.

## Backend: `CatalogSearchResult` (extended)

`backend/src/models/schemas.py` — existing model, one field added.

| Field | Type | Notes |
|---|---|---|
| `results` | `list[CatalogSKUOut]` | unchanged |
| `next_cursor` | `str \| None` | unchanged |
| `snapshot_date` | `str` | unchanged |
| `total` | `int` | **new** (FR-024) — the true count of catalog rows matching the current filters, independent of how many are returned in `results` (which is capped at 200, FR-023). Computed by a `COUNT(*)` query using the same `WHERE` clause as the paged query (research.md §3) — never estimated. |

## Backend: Snapshot calculation request (new)

New endpoint `POST /api/v1/catalog/calculate-snapshot` (research.md §5) — prices an
arbitrary, caller-supplied set of SKU selections, independent of any persisted Architecture.
No ownership/auth-scoping beyond the existing `CurrentUser` dependency (kept for
consistency with every other endpoint; there is no `architecture_id` to check ownership
against).

**Request** — `CalculateSnapshotRequest`:

| Field | Type | Notes |
|---|---|---|
| `duration` | `CalculationDuration` | the duration to price the snapshot at (the *new* Duration, per FR-016a) |
| `selections` | `list[SnapshotSelection]` | the prior architecture's SKU selections as of the last accepted calculation (research.md §6/§7 — this is exactly what the frontend already has stored as the Prior Calculation) |

**`SnapshotSelection`** (one entry per prior SKU selection — note this intentionally omits
`sku_selection_id`/any Postgres foreign key; it's a plain value, not a reference to a live
row, since the row it originally came from may since have been edited or deleted):

| Field | Type | Notes |
|---|---|---|
| `service_code` | `str` | |
| `sku` | `str` | |
| `pricing_term` | `PricingTerm` | existing enum (006) |
| `purchase_option` | `PurchaseOption` | existing enum (006) |
| `usage_quantity` | `Decimal \| str` | same shape as `SKUSelectionCreate.usage_quantity` |

**Response**: the existing `CalculationResult` schema, unchanged — same shape as
`POST /architectures/{id}/calculate` returns, so the frontend's existing result-rendering
logic (total, warnings, unpriceable, line items) needs no special-casing for a
snapshot-derived result versus a live-architecture one.

**Validation rule**: `selections` MUST NOT be empty (mirrors the existing
`EmptyCatalogFilterError`-style "reject a meaningless request" pattern already used
elsewhere in this codebase) — an empty snapshot has no meaningful "prior total" to adjust,
and this path should only ever be invoked with the real prior selections from a stored
Prior Calculation (research.md §7), which by construction is never empty (a Calculate only
ever runs once at least one SKU is selected).

## Frontend-only: Column width preference (`localStorage`)

Key: `cloud-pricing-column-widths` (research.md §7). Value: a JSON object.

| Field | Type | Notes |
|---|---|---|
| `provider` \| `collections` \| `service` \| `pricing` | `number` (pixels) | one entry per resizable column (columns 1, 2, 3, 5 — column 4/diagram already has its own independent height-resize handle and grows to fill remaining width by default, so it is not a *fixed* width preference the way the others are) |

Absent keys fall back to each column's existing default width (unchanged from 007). No
version/migration field — a missing or malformed entry for a given column is treated as
"use the default," never an error (consistent with this codebase's existing
`localStorage` read pattern in `api/client.ts`'s `getUserId()`).

## Frontend-only: Prior Calculation (`localStorage`)

Key: `cloud-pricing-prior-calculation-{architectureId}` (research.md §7) — one entry per
Architecture, so switching Architectures never mixes baselines (Edge Cases).

| Field | Type | Notes |
|---|---|---|
| `total` | `string` (decimal) | the locked-in total this baseline represents |
| `duration` | `CalculationDuration` | the Duration this total was computed at |
| `selections` | `SnapshotSelection[]` | the same shape as the new endpoint's request (above) — the architecture's own SKU selections as of this calculation, kept so a later Duration-only-changed-too case (FR-016a) can be resent to `calculate-snapshot` |

Written every time a Calculate succeeds **and** the architecture's own contents changed
since the last write (FR-016) — never written on a Duration-only or no-op Calculate, per
the baseline-update decision (research.md §6). Read once per Architecture, on that
Architecture becoming the selected one in column 1.

## Frontend-only: Price per Sku entry (derived, not stored)

Not a new entity — a display-only view over `CalculationResult.line_items` (already
returned by both `/calculate` and the new `/calculate-snapshot`), filtered to
`priceable: true` and sorted by `price` descending (Clarifications, FR-017). No new backend
field: `PriceLineItem` already carries `sku`, `service_code`, and `price`.

## Frontend-only: Search match count / regex validity (derived, not stored)

`CatalogSearchResult.total` (above) drives the "(n of m results displayed)" indicator
directly — `n = results.length`, `m = total`, shown only when `n < total`. A 400 response
from the search endpoint (FR-021, an invalid regex in one field) follows this codebase's
existing exception-handler convention (`PricingDataUnavailableError`/
`EmptyCatalogFilterError` in `backend/src/main.py`, each a distinct exception class with a
registered `@app.exception_handler`, returning `{"error": "<slug>", "message": "<text>"}`):
a new `InvalidRegexPatternError` with `{"error": "invalid_regex_pattern", "message":
"<text>", "field": "service_code" | "product_family" | "text"}` — the added `field` key
lets the frontend show the message inline next to the offending input rather than as a
generic banner.

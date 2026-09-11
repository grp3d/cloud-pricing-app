# Data Model: UI Fixes and Enhancements — Next Iteration

Phase 1 output. Covers only what changes or is newly introduced by this feature; unchanged
entities from 001-008 are not repeated here.

## Postgres (user-defined data, Constitution Principle II) — unchanged shape, one behavior change

### DataConnector / SKUSelection (unchanged schema)

No column, constraint, or table changes. `SKUSelection.connector_id` already carries
`unique=True` (enforces FR-007 — at most one `SKUSelection` per `DataConnector` — at the
database level, already true before this feature). `DataConnector` already carries no
uniqueness constraint on `(from_collection_id, to_collection_id)` (already permits FR-009's
multiple Connectors between the same Collection pair).

**Behavior change (FR-008)**: `POST /connectors/{connector_id}/sku-selection` changes from
delete-existing-then-insert ("replace") to refuse-with-409 when a `SKUSelection` already exists
for that connector. No schema change — the response shape on success (`SKUSelectionOut`) is
unchanged; the conflict path returns FastAPI's standard `HTTPException(409, detail=...)` shape,
this codebase's existing error-response convention (no typed error schema precedent to match).

## Vendor pricing data (Parquet/DuckDB, read-only, Constitution Principle I) — no schema change

No Parquet column is added, renamed, or reinterpreted. `AWSDataTransfer`'s `fromRegionCode`/
`toRegionCode` fields already exist inside `product_dim.attributes_json` and are already
surfaced through `search_catalog()`'s existing `attributes` dict — this feature only adds two
new *query parameters* to filter by them (§ below), and a frontend-only derived display value
computed from data the API already returns.

### `search_catalog()` — two new optional filter parameters (FR-029)

| Parameter | Type | Behavior |
|---|---|---|
| `from_region_code` | `str \| None` | Case-insensitive RE2 regex (same convention as every existing filter), matched against `json_extract_string(p.attributes_json, '$.fromRegionCode')`. AND-combined with every other active filter. |
| `to_region_code` | `str \| None` | Same, against `'$.toRegionCode'`. |

Both are additive to the existing `service_code`/`product_family`/`text` filters — a search with
none of the five filters set still raises `EmptyCatalogFilterError` exactly as today (at least
one filter of any kind is required); these two count toward that "at least one" the same as the
other three.

## Frontend types and state

### `PriceChangeSelection` / `PriorCalculation` / `BaselineDecision` (`lib/priceChange.ts`) — one new outcome value

```ts
export type BaselineDecision =
  | "establish"
  | "unchanged"
  | "direct"
  | "duration_adjusted"     // existing: content AND duration both changed
  | "duration_only";        // NEW (FR-002/003): content unchanged, duration alone changed —
                             // caller MUST use the same calculate-snapshot recalculation
                             // `duration_adjusted` already uses, never a client-side multiply.
```

`decideBaselineUpdate()`'s branching changes from:

```
if content unchanged → "unchanged"                    // duration ignored entirely (the bug)
```

to:

```
if content unchanged:
  if duration unchanged → "unchanged"
  else                  → "duration_only"              // NEW branch
if content changed:
  if duration unchanged → "direct"
  else                  → "duration_adjusted"
```

The stored `PriorCalculation.duration` field (unchanged shape) advances to the new duration on
both `"duration_adjusted"` and the new `"duration_only"` outcome — `WorkspacePage.tsx`'s caller
logic, not `priceChange.ts` itself, is what actually calls the snapshot-calculation endpoint and
writes the new baseline; `priceChange.ts` only decides which of the (now five) outcomes applies.

### `DiagramLayout` (new — `lib/diagramLayout.ts`, FR-024, research.md §7a)

Per-browser, per-Architecture `localStorage` entry, modeled on `priorCalculation.ts`'s existing
per-Architecture key pattern:

```ts
export interface CollectionLayoutOverride {
  width: number;
  height: number;
  x: number;
  y: number;
}

export type DiagramLayout = Record<string /* collection id */, CollectionLayoutOverride>;
```

- **Storage key**: `` `cloud-pricing-diagram-layout-${architectureId}` `` (same
  `cloud-pricing-` prefix and per-Architecture suffix convention as `priorCalculation.ts`'s
  `storageKey()`).
- **Read**: once per Architecture load, merged into `ArchitectureDiagramPanel`'s existing
  `manualSizeRef`-style override map (extended to also carry `x`/`y`, not just `width`/`height`)
  so a stored override applies from the very first render, the same way `manualSizeRef` already
  overrides `initialNodes`' computed size.
- **Write**: on `NodeResizer`'s `onResizeEnd` (already fires today, just needs its handler to
  also persist, not only update `manualSizeRef`) and on node drag stop (`onNodeDragStop` — new
  persistence; position is not currently preserved even in-session, research.md §7a).
- **Lifecycle**: no entry is required for a Collection that has never been manually
  resized/moved (falls back to the existing computed layout); a deleted Collection's stray
  entry is harmless dead data (same tolerance `ownHeights` already has for stale ids) but MAY be
  pruned opportunistically on next write, matching this feature's US3 fix for stale-id map
  entries generally.
- **Failure mode**: `localStorage` unavailable/quota-exceeded → silently no-op on write, same
  `try/catch` convention `columnWidths.ts` already established; a manual resize/move still works
  for the current session, it just won't survive a reload in that (already-degraded) browser
  state.

### AWSDataTransfer display label (new — `lib/awsDataTransfer.ts`, FR-027/028/030)

```ts
/** Returns the derived "{fromRegionCode}=>{toRegionCode}" label for an AWSDataTransfer SKU, or
 * `null` when service_code isn't AWSDataTransfer, or either region field is absent from
 * `attributes` (research.md §9 — never fabricate a missing region code). Callers fall back to
 * their own existing default label whenever this returns `null`. */
export function awsDataTransferLabel(
  serviceCode: string,
  attributes: Record<string, string>,
): string | null;
```

Pure function, no new state — consumed by `CatalogSearchPanel.tsx`'s `summaryText()`,
`ArchitectureDiagramPanel.tsx`'s `ServiceList` item text, and `PricingPanel.tsx`'s per-SKU
breakdown line, each falling back to their existing today's-behavior label when this returns
`null`.

### Edge offset for parallel Connectors (new — pure helper, FR-010)

```ts
/** Given all edges, returns each edge's curvature/offset index within its own (order-
 * independent) source/target pair group — 0 for the first edge in a pair, 1 for the second,
 * etc. — so multiple Connectors between the same two Collections render as visually distinct,
 * independently clickable paths instead of exactly overlapping. Pure, unit-testable the same
 * way `nodeLayout.ts`'s functions are. */
export function edgeOffsetIndex(
  edges: { id: string; source: string; target: string }[],
): Record<string /* edge id */, number>;
```

## Key Entities recap (spec.md, unchanged relationships — restated for traceability)

- **Connector**: unchanged relationships; behavior corrected (refuse, not replace, a second
  SKU) and rendering corrected (multiple Connectors between the same pair stay visually
  distinct).
- **Collection**: gains an optional `localStorage`-resident layout override
  (`CollectionLayoutOverride`) — presentational only, not a new Postgres column.
- **Prior Calculation (baseline)**: `decideBaselineUpdate()` gains the `"duration_only"` outcome;
  no change to what's actually stored (`PriorCalculation`'s shape is unchanged).
- **AWSDataTransfer Service**: no new persisted attribute — a derived, computed-on-read display
  value only.

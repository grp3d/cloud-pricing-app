# Research: Multi-Region Collections and Region-Grouped Pricing

**Input**: spec.md's FR-001–FR-019, Assumptions. **Method**: three parallel research passes over the live codebase (backend data model/migrations; frontend collections/diagram UI; pricing panel + test conventions). All findings below are grounded in file:line citations gathered during those passes.

## 1. Region storage: new `Collection.region` column, no DB enum

**Decision**: Add `region: str` (NOT NULL) to the `Collection` ORM model (`backend/src/models/orm.py:63-111`) via a new Alembic migration, as a plain `String` column — not a Postgres enum type and not a foreign key to a `regions` table.

**Rationale**: The set of valid regions is driven entirely by which `region=<code>` partitions currently exist under the AWS pricing Parquet data (see §3) — a set that changes whenever the upstream pricing-data project adds/drops a region, with no code change on this side. A DB enum or FK table would need a migration every time that happens, which fights the reason the data is partitioned this way in the first place (Constitution Principle VI: no complexity not justified by a current requirement). Validation against "is this a currently-available region" happens at the API layer (§3), not the schema layer.

**Alternatives considered**: (a) Postgres enum type — rejected, requires a migration per new AWS region. (b) FK to a `regions` table synced from Parquet partitions — rejected as premature; nothing else needs to join against regions relationally, and the derived list (§3) is cheap enough to compute on demand.

**Migration shape**: No existing migration in this repo backfills a new NOT-NULL column (`backend/src/db/migrations/versions/0002_collection_nesting.py` only adds a nullable column + index/check-constraint). This feature introduces that 3-step pattern fresh, per FR-016:
1. `op.add_column("collections", sa.Column("region", sa.String(), nullable=True))`
2. `op.execute("UPDATE collections SET region = '<former settings.aws_pricing_region value>' WHERE region IS NULL")` — the literal value is baked into the migration at the time it's written (the app's current single global region), matching FR-016.
3. `op.alter_column("collections", "region", nullable=False)`

## 2. Region locking is computed, not stored

**Decision**: "Has content" (FR-003) is evaluated at write time from existing relationships — no new boolean/flag column. A collection is locked once: `SELECT 1 FROM sku_selections WHERE collection_id = :id` returns a row, OR (VPC only) `SELECT 1 FROM collections WHERE parent_collection_id = :id` returns a row.

**Rationale**: Both queries are simple existence checks against already-indexed foreign keys; a denormalized flag would need to be kept in sync on every SKU-selection and nesting change, which is more moving parts for no benefit (Principle VI).

## 3. Available regions: derive from Parquet partition directories, no new query cost

**Decision**: Add a `list_available_regions()` function (new `backend/src/pricing_data/regions.py`, or alongside `snapshot.py`) that mirrors the existing `_snapshot_dates()` pattern (`backend/src/pricing_data/snapshot.py:19-28`): `Path.iterdir()` over each table's `snapshot_date=<latest>/` directory, strip the `region=` prefix, and intersect across all 5 tables (mirroring `resolve_latest_snapshot_date`, `snapshot.py:31-49`) so only regions with complete data across `service_dim, product_dim, product_attribute, region_dim, price_fact` are offered.

**Rationale**: This is a filesystem listing, not a DuckDB scan — cheap enough to call directly from a `GET /regions` endpoint with no caching layer (Principle VI: don't add caching before there's a demonstrated cost). Verified live against the actual data directory: all 5 tables currently expose the identical region set at `snapshot_date=2026-09-15`: `ap-northeast-1, eu-west-1, eu-west-2, us-east-1, us-east-2, us-west-1, us-west-2`.

**Alternatives considered**: A DISTINCT query against the (unused-today) `region_dim` Parquet table via DuckDB — rejected as strictly more expensive than directory listing for the same answer, and would require reading a table nothing else in the backend touches yet.

## 4. Threading `region` through the three partition-path helpers

**Decision**: Replace all 3 reads of `settings.aws_pricing_region` (`pricing.py:44`, `catalog.py:56`, `catalog.py:63` — all inside the private `_..._path(snapshot_date)` helpers) with an explicit `region: str` parameter threaded in from every public caller (`search_catalog`, `resolve_attributes`, `lookup_price`, `lookup_reserved_price`, `resolve_units`). `settings.aws_pricing_region` stops being read at runtime by these paths; it remains only as the literal value baked into the migration's backfill (§1).

**Rationale**: There are only 3 call sites total — this is a narrow, mechanical parameter-threading change, not a redesign. Keeping the config field around (for the migration) but no longer reading it at request time avoids a hidden global default silently overriding a collection's actual region.

## 5. Catalog search's new `region` param is distinct from `from_region_code`/`to_region_code`

**Decision**: `GET /catalog/skus` gains a new required query param named `region` (backend/src/api/catalog.py:13-37, `search_catalog()` at catalog.py:79-101 gains a required `region` kwarg). This is **not** the same thing as the existing `from_region_code`/`to_region_code` params (catalog.py:14-21), which are AWSDataTransfer-specific *attribute* filters on the product's own region-pair fields, unrelated to which Parquet partition is read.

**Rationale**: Reusing a name here would conflate "which partition to search" (this feature) with "which AWSDataTransfer region-pair to filter on" (009's feature) — two orthogonal concepts that happen to both be about regions. Keeping them as separate, clearly-named params avoids that confusion and keeps 009's filters untouched.

## 6. Collection creation: `region` required unless `parent_collection_id` given (server-authoritative inheritance)

**Decision**: `CollectionCreate` (`schemas.py:96-98`, currently `{type, name}`) gains two new optional fields: `region: str | None` and `parent_collection_id: UUID | None`. Validation rule: if `parent_collection_id` is provided (only valid for `type == "application_component"`, parent must be an existing VPC), the server **ignores/overrides any client-supplied `region`** and sets it to the parent VPC's actual region — the client never gets to assert a region that contradicts the parent it's nesting into. If `parent_collection_id` is omitted, `region` is required and validated against §3's available-regions list.

**Rationale**: Matches FR-001a (skip prompt, inherit silently) while keeping the server as the single source of truth for region correctness — a client bug or stale UI state can't create a mismatched nested Application, closing the same class of gap Constitution Principle I cares about for pricing data, applied here to user data integrity.

**Frontend gap this closes**: Research confirmed collection creation today (`WorkspacePage.tsx:295-303`, `client.ts:99-103`) sends only `{type, name}` — no `parent_collection_id` at all; nesting today only happens later, via drag (§8). `selectedCollectionId` (`WorkspacePage.tsx:247`) exists but isn't wired into creation. This feature wires it: when the selected collection is a VPC and the user adds an Application, the create call now includes `parent_collection_id` (and the region prompt — a reused `Dialog`, see §7 — is skipped).

## 7. Region-selection prompt reuses the existing `Dialog` primitive

**Decision**: Build the new region-selection popup (FR-001) as a new component using the existing Radix-based `Dialog` (`frontend/src/components/ui/dialog.tsx`), the same primitive 009's `AddConnectorDialog` already uses (`ArchitectureDiagramPanel.tsx:521-610`). Do **not** use `ConfirmDeleteDialog`'s hand-rolled plain-div modal pattern — its own code comment explicitly scopes that pattern to a single yes/no prompt, not a form with a dropdown.

**Rationale**: No new dependency, consistent with Principle VI and this codebase's own established shadcn-copy-in convention (`plan.md` precedent from 009).

## 8. Same-region nesting: extend `decideNestingChange`, not a new module

**Decision**: The existing pure function `decideNestingChange(intersectingVpcIds, currentParentId)` (`frontend/src/pages/dropTargetDetection.ts:19-28`), called from `onNodeDragStop` (`ArchitectureDiagramPanel.tsx:1065-1146`), is extended to also take the dragged Application's region and each candidate VPC's region, and to reject (return a "rejected" outcome) when they don't match — rather than adding a second, parallel decision function.

**Rationale**: This function already owns "should this drag change the parent," which is exactly the decision FR-004 modifies; region-matching is one more input to the same decision, not a separate concern. Research confirmed there is **no existing toast/inline-rejection/snap-back pattern anywhere in the drag flow today** — this feature is the first to need one. The plan adds a minimal inline rejection surface (e.g., a short-lived message near the diagram) rather than pulling in a new toast library, since no toast system was found in this codebase and Principle VI disfavors adding one for a single feature's use.

**Server-side mirror**: The existing `PATCH .../parent_collection_id` endpoint (behind `api.updateCollectionParent`, `client.ts:107-111`) gains the same region-match check server-side, returning `409 Conflict` on mismatch — mirroring 009's precedent of refusing rather than silently allowing an invalid state (its Connector-conflict `409`), so the rule holds even if a client bypasses the UI check.

## 9. Connector arrows: set `markerEnd` at edge construction

**Decision**: Add `markerEnd: { type: MarkerType.ArrowClosed }` to the edge object built in `rawEdges` (`ArchitectureDiagramPanel.tsx:935-981`, specifically alongside the object's other fields around line 948) or the subsequent `.map()` at 983-987. `OffsetEdge` already forwards a `markerEnd` prop straight to React Flow's `<BaseEdge>` (lines 454, 475, 502) — it was simply never given a value, which is why no arrows render today (confirmed: zero `markerEnd` value assignments found).

**Rationale**: Smallest possible change — the rendering plumbing already exists; only the data needs a value.

## 10. Region label placement on diagram nodes

**Decision**: Add a small absolutely-positioned label (`absolute bottom-1 right-1 ...`) inside the existing `relative h-full w-full` wrapper already present in both `ApplicationComponentNode` (`ArchitectureDiagramPanel.tsx:324-365`) and `VpcNode` (`386-429`), as a sibling to the existing bordered content div. For `ApplicationComponentNode`, the label renders conditionally on `!parent_collection_id` (unnested) per FR-019.

**Rationale**: Both node components already establish the positioning context (`relative`) this needs; no restructuring required, matching each component's existing wrapper pattern.

## 11. Pricing breakdown: region resolved server-side, attached to `PriceLineItem`

**Decision**: `PriceLineItem` (`schemas.py:184-189`, currently `sku_selection_id, service_code, sku, price, priceable`) gains `region: str | None`, resolved in `calculate_architecture_price` (`backend/src/services/price_calculation.py:68-99, 173-183`) — specifically alongside the existing `selection_components` dict (lines 76-90), which already does an id → owning-Collection(s)/Connector lookup for the unpriceable list's `components` field. The same lookup resolves each selection's region: a Collection-owned `SKUSelection` uses that Collection's `region`; a Connector-owned one (FR-006's precedent) uses the connector's `from_collection.region`.

**Important design consequence found during research**: because `Collection.region` is NOT NULL post-migration (§1) and `DataConnector.from_collection_id` is already NOT NULL (existing CHECK constraint), **every** `PriceLineItem` will always resolve to a real region under this data model — there is no code path today that produces an item with no determinable region. FR-015's "Global" section is implemented as a defensive fallback branch (for defense-in-depth / future-proofing, e.g. a not-yet-anticipated ownerless selection), but is expected to be **unreachable in normal operation** given the finalized entity model. This is documented here rather than silently dropped, so a future reader doesn't mistake the dead branch for a bug.

**Frontend grouping**: A new pure function `frontend/src/lib/regionPricingGroups.ts` takes the (region-tagged) line items and returns an ordered `{ region, items, subtotal }[]`, preserving the existing price-descending order (`PricingPanel.tsx:243-245`) within each group. `PricingPanel.tsx`'s existing `PricePerSkuSection` (227-276) is restructured to render one section per group (reusing the existing `PriceLine` row component, 285-312) instead of one flat list, with the `Total` (line 130) and `Data Timestamp` (170-172) lines unmoved.

**Rationale**: No existing grouping/subtotal UI precedent was found anywhere in the frontend (`grep`ped for `subtotal|groupBy` — zero hits); this feature is the first, so the plan follows the established `lib/`-module convention (`priceChange.ts`, `awsDataTransfer.ts`, `edgeOffset.ts` from 009) rather than inlining the grouping logic into the component.

## 12. Label change ("Application Component" → "Application")

**Decision**: A text-only find/replace across the identified UI strings (`CollectionsPanel.tsx`'s type-selector option and any other literal occurrences) — no research risk here; noted for completeness since it's still an FR (FR-010).

## Test conventions confirmed (for tasks.md planning)

- **Backend**: `backend/tests/{contract,integration,unit}/`, `pytest.mark.asyncio`, httpx `client` + `auth_headers` fixtures from `conftest.py` for contract tests (`test_collections.py` pattern); pure-logic unit tests import functions directly and use real Parquet data per Constitution Principle I (`test_catalog_search.py`, `test_duration.py` — `@pytest.mark.parametrize`, plain `assert`, no mocking).
- **Frontend**: `frontend/tests/unit/*.test.ts(x)` (flat), Vitest, `describe`/`it`/`expect` style, no mocking for pure `lib/` functions (`awsDataTransfer.test.ts` pattern).

# Implementation Plan: Multi-Region Collections and Region-Grouped Pricing

**Branch**: `010-multi-region-support` | **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-multi-region-support/spec.md`

## Summary

Drawn from `docs/functionality_2026-09-15.md` plus three clarifications (spec.md's Clarifications section): give every VPC and Application collection an explicit, immutable-once-locked AWS `region`, assigned at creation via a new region-selection dialog (or silently inherited from a selected parent VPC), enforced when nesting an Application into a VPC and when scoping service search (including for cross-region Connectors, scoped to their "from" side and now rendered with a directional arrow); add region-name labels to diagram boxes; relabel "Application Component(s)" to "Application(s)"; and restructure column 5's pricing breakdown into region-labeled, subtotaled sections. Research (research.md) found this is a genuine, if narrow, data-model change — not a presentation-only pass like 009: a new NOT-NULL `Collection.region` column (with a 3-step backfill migration, no precedent for that pattern in this repo yet), a new cheap available-regions derivation from existing Parquet partition directories, and a new region field threaded through `PriceLineItem` server-side. The frontend side reuses existing machinery wherever it already fits (the `Dialog` primitive from 009's Add Connector feature, the `decideNestingChange` pure function, the `lib/` pure-module convention) rather than introducing parallel new abstractions.

## Technical Context

**Language/Version**: TypeScript ~5.6, React 18.3, Vite 5.4 (frontend, unchanged); Python 3.x, FastAPI ≥0.115, Pydantic ≥2.9, SQLAlchemy 2.0 async, Alembic (backend, unchanged) — both `frontend/` and `backend/` are touched.

**Primary Dependencies**: No new npm/pip dependency. Frontend reuses the existing `Dialog` primitive (`components/ui/dialog.tsx`, added in 009) for the new region-selection popup, `@xyflow/react`'s existing `markerEnd`/`MarkerType` support (already plumbed through `OffsetEdge`, just never given a value) for connector arrows, and the established `lib/` pure-module convention (`priceChange.ts`, `awsDataTransfer.ts`, `edgeOffset.ts`) for the new `regionPricingGroups.ts` and the extended `dropTargetDetection.ts`. Backend reuses FastAPI + Pydantic + SQLAlchemy/Alembic + DuckDB — nothing new to install; the new available-regions derivation is a filesystem `Path.iterdir()` (already the pattern used by `snapshot.py`'s `_snapshot_dates`), not a new query engine or caching layer.

**Storage**: PostgreSQL (existing) — one schema change: `collections.region` (`String`, NOT NULL after a 3-step add/backfill/constrain Alembic migration — research.md §1, data-model.md). No new tables. Parquet-via-DuckDB (existing, read-only, unchanged) — three existing partition-path helpers (`pricing.py:44`, `catalog.py:56,63`) gain a `region` parameter instead of reading `settings.aws_pricing_region` (research.md §4); no schema/partition-layout change, since the data is already region-partitioned (this feature only starts using the dimension that already exists).

**Testing**: Backend — pytest, test-first (Constitution Principle V) for: the region-backfill migration's resulting data shape (verified via an integration test against the test DB), the region-locking `409` on `PATCH /collections/{id}/region` and on `PATCH .../parent_collection_id` (contract tests alongside `test_collections.py`), `list_available_regions()` (new unit test, real-data-backed per `test_catalog_search.py`'s no-mocking convention), and `PriceLineItem.region` resolution in `calculate_architecture_price` (unit test alongside existing pricing-calculation tests). Frontend — Vitest + Testing Library, test-first for the two new/extended pure-logic modules: `regionPricingGroups.ts` (new) and `dropTargetDetection.ts`'s extended same-region check (existing file, extended) — mirroring `awsDataTransfer.test.ts`'s no-mocking style. `claude-in-chrome` live verification against `quickstart.md` for the presentational work (region-selection dialog, drag-rejection feedback, diagram region labels, connector arrows, region-grouped pricing sections), per Principle V's carve-out and 009's precedent — and specifically required before the drag-rejection UI is written, since research.md §8 confirms no existing feedback pattern to model it on.

**Target Platform**: Existing web SPA, desktop-width browsers (unchanged).

**Project Type**: Web application (`backend/` + `frontend/` split) — both sides touched.

**Performance Goals**: No new numeric target. `list_available_regions()` is a directory listing over ≤~10 region subdirectories per table, called once per dialog-open / `GET /regions` request — not benchmarked further per Constitution Principle VI. The three region-parameterized partition-path helpers read exactly one partition per call, same cost shape as today's single-global-region reads.

**Constraints**: `check-api-types` MUST stay clean for every schema change in contracts/api.md (Constitution Principle IV). Region validation (client-supplied `region` on create/update) MUST check against the live `GET /regions` list, never a hardcoded list (spec.md's clarified FR-017). Same-region nesting (FR-004) MUST be enforced server-side even though a client-side check also exists, so a bypassed/stale client can't create an invalid nesting (Constitution Principle I's data-integrity posture, applied to user data here). Migration backfill (FR-016) MUST use the literal historical `aws_pricing_region` value, not a placeholder, so existing architectures' pricing behavior is unchanged post-migration. Existing backend and frontend test suites stay green throughout.

**Scale/Scope**: One new Postgres column, no new tables; one new backend endpoint (`GET /regions`) plus one new per-field PATCH (`/collections/{id}/region`); pricing/catalog data volume unchanged (same Parquet tables, now read per-region instead of from one global default).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Pricing Data Integrity**: PASS — region becomes an explicit modeled column threaded through the existing three partition-path helpers (research.md §4); no price is estimated or fabricated. The backfill migration uses the app's real former global-region value (FR-016), not a guess. FR-015's "Global" pricing-breakdown bucket is implemented defensively but documented as expected-unreachable under the finalized entity model (research.md §11, data-model.md) — this is called out explicitly rather than silently left dead code, so it isn't later mistaken for a live gap in traceability.
- **II. Clear Data-Layer Separation**: PASS — `region` is a Postgres attribute of the user-defined `Collection` (user truth), not written into Parquet. The available-regions derivation reads Parquet directory structure directly and read-only (research.md §3); it does not write anything, and nothing here blurs which store is authoritative for what.
- **III. Provider-Extensibility by Design**: PASS — `region` is modeled as a plain string field, matching the existing `from_region_code`/`to_region_code` convention rather than an AWS-hardcoded type; `GET /regions` is framed generically ("regions the pricing dataset currently has data for"), not structurally AWS-specific, even though the values happen to be AWS codes today (the app remains AWS-only per Principle III's current scope — no multi-provider code path is introduced).
- **IV. Type-Safe Frontend/Backend Contract**: GATE — every schema change in contracts/api.md (`CollectionCreate`/`CollectionOut`, new `PATCH .../region`, new `409` on `.../parent_collection_id`, `GET /catalog/skus`'s new `region` param, new `GET /regions`, `PriceLineItem.region`) is Pydantic-native; `check-api-types` MUST pass and regenerate the frontend types each change depends on.
- **V. Test-First Development**: GATE — region-locking `409`s, `list_available_regions()`, and `PriceLineItem.region` resolution are backend pricing/data-relationship logic → NON-NEGOTIABLE test-first. `regionPricingGroups.ts` and the extended `dropTargetDetection.ts` are frontend pure logic in the established `lib/`/pure-module convention → also test-first, matching 007/008/009 precedent. The region-selection dialog, drag-rejection message, diagram region labels, and connector arrows are presentational UI → tests-after / live-verified per Principle V's carve-out, with the explicit obligation (research.md §8) to verify the drag-rejection UX live before considering it done, since no prior pattern exists to crib from.
- **VI. Simplicity & YAGNI**: PASS, with explicit fences carried from research.md: no DB enum/FK table for regions (§1 — would force a migration per new upstream region); no caching layer for the cheap available-regions listing (§3); no generic multi-field `PATCH /collections/{id}` redesign — one new per-field endpoint matching the existing `.../parent_collection_id` convention (§6/§7 in research, contracts/api.md); no new toast/notification library for the single drag-rejection message (§8); the "Global" pricing bucket gets a defensive branch, not elaborate global-service-detection logic, since it's unreachable under the current entity model (§11).

No unjustified violations. Complexity Tracking is not needed.

**Post-Design re-check** (after Phase 0/1 artifacts above): every gate still holds against the concrete design. I's obligation is discharged by data-model.md's explicit note on the "Global" bucket and research.md §1/§4/§11; II is confirmed by data-model.md's `AvailableRegions` section being explicitly non-persisted/derived-only; III is confirmed by contracts/api.md's plain-string `region` fields and generically-framed `GET /regions`; IV's gate is discharged by contracts/api.md's explicit before/after schemas for all six changed/new surfaces; V's obligations are named against specific files in the Project Structure below. No new violations were introduced while designing data-model.md/contracts/quickstart.md.

## Project Structure

### Documentation (this feature)

```text
specs/010-multi-region-support/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── api.md
├── checklists/
│   └── requirements.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── db/migrations/versions/
│   │   └── 0003_collection_region.py     # NEW — add nullable, backfill (FR-016), set NOT NULL
│   ├── models/
│   │   ├── orm.py                        # Collection.region column
│   │   └── schemas.py                    # CollectionCreate/Out, PriceLineItem gain `region`
│   ├── api/
│   │   ├── collections.py                # create: region/parent_collection_id handling;
│   │   │                                  #   NEW PATCH /collections/{id}/region
│   │   ├── catalog.py                    # search_catalog(): new required `region` param
│   │   └── regions.py                    # NEW — GET /regions
│   ├── pricing_data/
│   │   ├── pricing.py                    # _price_fact_path: region param (no more settings read)
│   │   ├── catalog.py                    # _product_dim_path/_service_dim_path: region param
│   │   └── regions.py                    # NEW — list_available_regions() (mirrors snapshot.py)
│   └── services/
│       └── price_calculation.py          # PriceLineItem.region resolution (Collection/Connector)
└── tests/
    ├── contract/
    │   └── test_collections.py           # extended: region on create, inheritance, 409 lock cases
    ├── integration/
    │   └── test_us2_connectors.py        # extended: 409 region-mismatch on parent_collection_id
    └── unit/
        ├── test_regions.py               # NEW — list_available_regions()
        ├── test_catalog_search.py        # extended: region param cases
        └── test_price_calculation.py     # extended: PriceLineItem.region resolution (name approximate)

frontend/
├── src/
│   ├── components/workspace/
│   │   ├── CollectionsPanel.tsx          # "+Add" flow: region dialog, parent-VPC inheritance,
│   │   │                                  #   "Application" label (FR-010)
│   │   ├── RegionSelectDialog.tsx        # NEW — reuses ui/dialog.tsx (research.md §7)
│   │   ├── ArchitectureDiagramPanel.tsx  # markerEnd arrows; region labels on node components;
│   │   │                                  #   drag-rejection feedback wiring
│   │   └── PricingPanel.tsx              # region-grouped/subtotaled breakdown (replaces flat list)
│   ├── pages/
│   │   ├── WorkspacePage.tsx             # createCollection: region + parent_collection_id wiring
│   │   └── dropTargetDetection.ts        # decideNestingChange: extended with region-match check
│   ├── lib/
│   │   └── regionPricingGroups.ts        # NEW — pure grouping/subtotal transform
│   └── api/client.ts                     # createCollection, updateCollectionRegion (new),
│                                          #   searchCatalog(region), listRegions (new)
└── tests/unit/
    ├── regionPricingGroups.test.ts       # new (test-first)
    └── dropTargetDetection.test.ts       # extended: region-mismatch rejection case (test-first)
```

**Structure Decision**: Existing `backend/` + `frontend/` split (unchanged from 001-009). No new top-level directories. Backend adds one new small module (`pricing_data/regions.py`, `api/regions.py`) rather than folding region-listing into an existing file, since it's a genuinely new capability with its own tests. Frontend keeps the new pure logic in `lib/` (`regionPricingGroups.ts`) and extends the existing `dropTargetDetection.ts` rather than creating a parallel nesting-decision module, matching 007/008/009's established convention.

## Complexity Tracking

*No Constitution Check violations requiring justification.*

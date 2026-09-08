# Implementation Plan: Service Selection Improvements

**Branch**: `003-service-selection-improvements` | **Date**: 2026-09-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-service-selection-improvements/spec.md`

## Summary

Four related UI/UX improvements to the existing assembly flow (`001`, extended by `002`):
(1) expose each SKU's full descriptive attributes and a richer list-row summary so users can
tell similar SKUs apart before selecting; (2) expose each SKU's real billing unit wherever a
usage quantity is entered or shown; (3) give Application Component nodes on the canvas a custom
renderer that lists their contained services and sizes itself to fit; (4) let users manually
resize VPC and Application Component nodes via React Flow's built-in `NodeResizer`, with a
minimum size on VPCs enforced by that same mechanism so a VPC can never shrink below what its
nested children need. No new Postgres tables or columns — everything here is either read-time
enrichment from the existing read-only DuckDB/Parquet pricing data, or purely a frontend canvas
change.

## Technical Context

**Language/Version**: Same as `001`/`002` — Python 3.12+ (backend), TypeScript 5.x / Node.js 20+
(frontend). No change.

**Primary Dependencies**: Same as `001`/`002` — no new dependency. Uses `@xyflow/react`'s
built-in `NodeResizer` (already part of the installed package, unused until now) for manual
resize, and its custom-node-type support (`nodeTypes` prop) for the Application Component
renderer — both are the library's own built-in mechanisms, not new code frameworks.

**Storage**: No schema change. PostgreSQL is untouched — `unit` and `attributes` are resolved at
request time from the existing read-only DuckDB/Parquet pricing data (`product_dim.attributes_json`,
`price_fact.unit`), never stored. No Alembic migration in this feature.

**Testing**: Same as `001`/`002` — pytest (backend, against real Postgres + the real Parquet
data) and Vitest (frontend). The canvas height-estimation math is extracted as a pure,
DOM-independent function so it's unit-testable without rendering React Flow, matching the
`dropTargetDetection.ts` precedent from `002`.

**Target Platform**: Same as `001`/`002` — web application, no change.

**Project Type**: web (extends the existing `backend/` and `frontend/`; no new top-level
structure).

**Performance Goals**: The one new potentially-expensive read is resolving billing units for
every SKU Selection in an Architecture when `GET /architectures/{id}` is called. This is done as
a single batched DuckDB query per request (one `IN (...)` lookup over the distinct SKUs
referenced), not one query per SKU Selection — same "resolve once per request" discipline `001`
already established for snapshot-date resolution.

**Constraints**: Reading `attributes`/`unit` MUST remain strictly read-only against DuckDB
(Constitution Principle I) — same as every other pricing-data read in this project. A SKU with
no available attributes or unit MUST be surfaced as a clear "unavailable" state (spec FR-003),
never a fabricated or blank value.

**Scale/Scope**: Unchanged from `001`/`002`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Pricing Data Integrity | `attributes`/`unit` are read-only DuckDB lookups, same access pattern as existing catalog search/price lookups; a missing value is surfaced as "unavailable," never fabricated (FR-003). | PASS |
| II. Clear Data-Layer Separation | Zero Postgres schema change — Postgres continues to hold only user-defined data; the two new pieces of information are resolved from DuckDB at read time and never persisted into Postgres. | PASS |
| III. Provider-Extensibility by Design | `attributes` is exposed as a generic key/value map, not typed AWS-specific fields — a future non-AWS provider's catalog could expose its own attributes the same generic way with no schema change. | PASS |
| IV. Type-Safe Frontend/Backend Contract | The two schema additions (`CatalogSKUOut.attributes`/`.unit`, `SKUSelectionOut.unit`) flow through the same FastAPI→OpenAPI→`openapi-typescript` pipeline and CI drift gate already established in `001`. | PASS |
| V. Test-First Development | The batched-unit-lookup logic and the canvas height-estimation function are both pure/isolable and get tests written first per `tasks.md`, matching `001`/`002`'s discipline. | PASS (enforced at task-generation/implementation time) |
| VI. Simplicity & YAGNI | Reuses React Flow's built-in `NodeResizer` and custom-node-type support rather than building custom resize/rendering logic; reuses the existing "resolve once per request" batching pattern rather than per-row DuckDB calls; no new dependency, table, or service. | PASS |

No violations — Complexity Tracking table is empty.

**Post-Design Re-Check** (after Phase 1 `data-model.md`/`contracts/api.md`): all six gates still
PASS. `data-model.md` confirms no Postgres schema changed; `contracts/api.md`'s enrichment of
existing response shapes (rather than new endpoints) keeps the surface area minimal. No new
complexity was introduced during design.

## Project Structure

### Documentation (this feature)

```text
specs/003-service-selection-improvements/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command) — no schema change; documents
│                          # the two request-time-resolved (non-persisted) fields
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── api.md            # delta on existing contracts — enriched response shapes only
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

No new top-level structure — this feature extends files already established by `001`/`002`:

```text
backend/
├── src/
│   ├── models/schemas.py            # ADD: CatalogSKUOut.attributes/.unit,
│   │                                  #      SKUSelectionOut.unit
│   ├── pricing_data/
│   │   ├── catalog.py                 # EXTEND: search_catalog returns attributes + unit
│   │   └── pricing.py                  # ADD: resolve_units(skus) batched lookup
│   ├── api/
│   │   ├── architectures.py             # EXTEND: get_architecture batch-resolves and
│   │   │                                 #         attaches units to the nested tree
│   │   ├── sku_selections.py             # EXTEND: attach unit to the single returned object
│   │   └── connectors.py                  # EXTEND: attach unit to the attached SKU Selection
│   └── services/
│       └── architecture_service.py         # ADD: a small shared "attach units to a response
│                                             #      tree" helper used by the above
└── tests/                                    # ADD unit/contract tests for the above

frontend/
├── src/
│   ├── components/
│   │   ├── CatalogSearchPanel.tsx       # EXTEND: richer per-row detail line, "no details"
│   │   │                                 #         fallback
│   │   └── SkuDetail.tsx                  # NEW: generic attributes key/value display, used
│   │                                       #      at the "Selected: ..." confirmation step
│   ├── pages/
│   │   └── nodeLayout.ts                   # NEW: pure functions estimating Application
│   │                                        #      Component / VPC node height from content
│   │                                        #      (extracted for unit testing, no DOM)
│   └── pages/CreateArchitecturePage.tsx      # EXTEND: custom Application Component node type
│                                              #         showing its services; NodeResizer on
│                                              #         both VPC and Application Component
│                                              #         nodes; VPC height now sums children's
│                                              #         estimated heights instead of a fixed
│                                              #         per-child amount
└── tests/                                       # ADD unit tests for nodeLayout.ts
```

**Structure Decision**: No structural change to the web application split established in `001`.
This feature is additive within the existing `backend/` and `frontend/` trees, and touches the
`002`-introduced VPC height computation in `CreateArchitecturePage.tsx` to account for
variable-height children (documented in `research.md`).

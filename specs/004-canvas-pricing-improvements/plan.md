# Implementation Plan: Canvas & Pricing Improvements

**Branch**: `004-canvas-pricing-improvements` | **Date**: 2026-09-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-canvas-pricing-improvements/spec.md`

## Summary

Five related improvements to the assembly canvas and pricing flow (`001`-`003`): (1) a
duration-scoped calculation (1 day / 1 month / 1 year) that prorates Reserved commitments
against their real term length and on-demand costs against their billing unit's own implicit
time period, excluding — never guessing — anything unrecognized; (2) richer per-service detail
shown directly in canvas boxes; (3) cascading, multi-level box resizing plus VPC boxes showing
their own directly-attached services; (4) reliable connector creation/removal via a
select-two-then-Connect flow, alongside restoring drag-to-connect (a regression from `003`'s
custom node types dropping React Flow's `Handle` elements); (5) unpriceable/excluded-service
warnings that name their containing component(s). No new Postgres tables or columns — duration
is a request-time parameter, and the two new pieces of read-time enrichment (billing-unit
classification, per-selection attributes) follow the exact "resolve once per request" pattern
`003` already established for `unit`.

## Technical Context

**Language/Version**: Same as `001`-`003` — Python 3.12+ (backend), TypeScript 5.x / Node.js 20+
(frontend). No change.

**Primary Dependencies**: Same as `001`-`003` — no new dependency. Uses `@xyflow/react`'s
built-in `Handle` component (restoring what the default node type provided before `003`'s
custom node types), `useOnSelectionChange` hook (multi-node selection tracking, already part of
the installed package, unused until now), and its default shift/ctrl-click multi-select
interaction — all library built-ins, not new code frameworks (research.md #2, #3).

**Storage**: No schema change. PostgreSQL is untouched. `CalculationDuration` is a request
parameter, never persisted (spec Edge Cases). Billing-unit classification and per-SKU-Selection
`attributes` are resolved at request time from the existing read-only DuckDB/Parquet pricing
data, exactly like `003`'s `unit` field — no Alembic migration in this feature.

**Testing**: Same as `001`-`003` — pytest (backend, against real Postgres + real Parquet data)
and Vitest (frontend). Duration-proration math and billing-unit classification are pure,
DOM/DB-independent logic and get tests written first per Constitution Principle V; the
generalized N-level box-height recursion in `nodeLayout.ts` is likewise pure and unit-tested
without rendering React Flow, matching the `dropTargetDetection.ts`/`nodeLayout.ts` precedent
from `002`/`003`.

**Target Platform**: Same as `001`-`003` — web application, no change.

**Project Type**: web (extends the existing `backend/` and `frontend/`; no new top-level
structure).

**Performance Goals**: The calculate endpoint already resolves `unit` once per request (`003`);
this feature adds one more batched, resolve-once-per-request DuckDB query for per-SKU
`attributes` (mirroring `resolve_units`), not a query per SKU Selection. Billing-unit
classification is pure Python over already-resolved `unit` strings — no additional DuckDB round
trip beyond that single batched attributes query.

**Constraints**: Duration proration MUST NOT guess a price or a billing-unit's time-period
category (Constitution Principle I) — a billing unit outside the recognized set is excluded and
listed with a reason (spec FR-005), never approximated. Every dollar in a duration-scoped total
must be traceable to exactly one of FR-002/FR-003/FR-004's explicit rules.

**Scale/Scope**: Unchanged from `001`-`003`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Pricing Data Integrity | Duration proration is pure arithmetic over already-retrieved real prices/units — no fabricated numbers; a billing unit outside the recognized classification is excluded and surfaced with a reason (FR-005), never guessed. | PASS |
| II. Clear Data-Layer Separation | Zero Postgres schema change — `CalculationDuration` is a request parameter (never persisted); billing-unit classification and per-selection `attributes` are resolved from DuckDB at read time only, same as `003`'s `unit`. | PASS |
| III. Provider-Extensibility by Design | The billing-unit classification table is keyed by generic string labels (a lookup, not AWS-specific field names baked into a schema) — a future provider's own unit vocabulary plugs into the same two-bucket mechanism without a redesign. | PASS |
| IV. Type-Safe Frontend/Backend Contract | All new/changed fields (`CalculationDuration`, `UnpriceableItem.components`, `CalculationResult.duration`, `SKUSelectionOut.attributes`) flow through the same FastAPI→OpenAPI→`openapi-typescript` pipeline and CI drift gate established in `001`. | PASS |
| V. Test-First Development | Duration-proration math, billing-unit classification, and the generalized N-level height recursion are all pure/isolable and get tests written first per `tasks.md`, matching `001`-`003`'s discipline. | PASS (enforced at task-generation/implementation time) |
| VI. Simplicity & YAGNI | Reuses React Flow's built-in `Handle` and `useOnSelectionChange` rather than building custom connection-point or multi-select geometry; reuses `003`'s "resolve once per request" batching pattern for the new `attributes` lookup rather than inventing a new one; no new dependency, table, or service. | PASS |

No violations — Complexity Tracking table is empty.

**Post-Design Re-Check** (after Phase 1 `data-model.md`/`contracts/api.md`): all six gates still
PASS. `data-model.md` confirms no Postgres schema changed; `contracts/api.md`'s changes are all
additive/enrichment to existing response shapes (plus one new optional query parameter) —
no new endpoint. No new complexity was introduced during design.

## Project Structure

### Documentation (this feature)

```text
specs/004-canvas-pricing-improvements/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command) — no schema change; documents
│                          # the request-time-resolved (non-persisted) fields and lookups
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── api.md            # delta on existing contracts — one new query param, enriched
│                          # response shapes, no new endpoint
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

No new top-level structure — this feature extends files already established by `001`-`003`:

```text
backend/
├── src/
│   ├── models/schemas.py               # ADD: CalculationDuration enum,
│   │                                     #      SKUSelectionOut.attributes;
│   │                                     #      EXTEND: UnpriceableItem.components,
│   │                                     #      CalculationResult.duration
│   ├── pricing_data/
│   │   ├── duration.py                   # NEW: billing-unit -> time-period classification
│   │   │                                  #      table and classify_unit()
│   │   └── catalog.py                     # ADD: resolve_attributes(skus) batched lookup,
│   │                                       #      mirroring resolve_units (003)
│   ├── api/
│   │   ├── calculate.py                    # EXTEND: accept `duration` query param
│   │   ├── architectures.py                 # EXTEND: attach attributes alongside unit in the
│   │   │                                     #         nested tree
│   │   ├── sku_selections.py                 # EXTEND: attach attributes alongside unit
│   │   └── connectors.py                      # EXTEND: attach attributes alongside unit
│   └── services/
│       ├── price_calculation.py                # EXTEND: accept duration, apply
│       │                                        #         FR-002/003/004/005 proration rules,
│       │                                        #         track each selection's containing
│       │                                        #         component name(s) for FR-012/013
│       └── architecture_service.py               # EXTEND: shared "attach attributes" helper,
│                                                  #         mirroring the existing unit helper
└── tests/                                          # ADD unit/contract/integration tests for
                                                      # the above

frontend/
├── src/
│   ├── api/client.ts                        # EXTEND: calculate() accepts a duration param;
│   │                                         #         CalculationDuration type
│   ├── lib/skuDetail.ts                       # NEW: shared "pick a short identifying detail
│   │                                           #      from attributes" helper, extracted from
│   │                                           #      CatalogSearchPanel.tsx so the canvas node
│   │                                           #      renderers reuse the same candidate-key
│   │                                           #      logic (003, DRY)
│   ├── components/
│   │   └── CatalogSearchPanel.tsx              # EXTEND: use the shared helper instead of its
│   │                                            #         own local copy
│   └── pages/
│       ├── nodeLayout.ts                        # EXTEND: generalize height computation to
│       │                                         #         recurse through however many levels
│       │                                         #         of nesting exist (replaces the
│       │                                         #         one-level-only estimateVpcHeight)
│       └── CreateArchitecturePage.tsx             # EXTEND: duration selector next to
│                                                   #         Calculate; VpcNode renders its own
│                                                   #         sku_selections; <Handle> added to
│                                                   #         both node types (fixes drag
│                                                   #         regression); multi-select tracking
│                                                   #         via useOnSelectionChange;
│                                                   #         Connect/Remove Connector actions;
│                                                   #         warnings list shows component
│                                                   #         name(s)
└── tests/                                           # ADD unit tests for nodeLayout.ts's
                                                       # generalized recursion and the shared
                                                       # skuDetail helper
```

**Structure Decision**: No structural change to the web application split established in `001`.
This feature is additive within the existing `backend/` and `frontend/` trees, and — like `003`
did for VPC height — replaces one specific piece of `002`/`003`-era logic (the one-level-only
VPC height formula) with a generalized version, documented as a deliberate evolution rather than
new complexity (research.md #6).

## Complexity Tracking

*No violations — table intentionally empty.*

# Implementation Plan: Nest Application Components into VPCs

**Branch**: `002-vpc-component-nesting` | **Date**: 2026-09-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-vpc-component-nesting/spec.md`

## Summary

Let a user drag an Application Component Collection onto a VPC Collection on the existing
assembly canvas (from `001-assemble-price-aws-architecture`) to nest it inside that VPC; drag it
onto a different VPC to move it; drag it out to un-nest it back to top-level. Technical approach:
add one nullable self-referential column (`parent_collection_id`) to the existing `collections`
table, one new `PATCH /collections/{id}` endpoint to set/clear it (with server-side validation
that only an Application Component can have a parent and that parent must be a VPC in the same
Architecture), and — on the frontend — use `@xyflow/react`'s built-in parent/child node support
(`parentId`, deliberately without `extent: 'parent'` — see `research.md` #1, that option would
block dragging a node back out to un-nest it) rather than building custom nesting UI from
scratch. Deleting a
VPC un-nests (never cascade-deletes) its children, per the spec's Clarifications. No change to
price calculation is needed: it already sums every Collection in an Architecture regardless of
nesting.

## Technical Context

**Language/Version**: Same as `001-assemble-price-aws-architecture` — Python 3.12+ (backend),
TypeScript 5.x / Node.js 20+ (frontend). No change.

**Primary Dependencies**: Same as 001 — no new dependency is required. This feature is
implemented entirely with `@xyflow/react`'s existing built-in parent/child node support
(`Node.parentId`; not `extent: 'parent'` — see `research.md` #1), already installed for the
Collections/Connectors canvas; SQLAlchemy/Alembic for the new column; FastAPI/Pydantic for the
new endpoint.

**Storage**: PostgreSQL — one new nullable self-referential column
(`collections.parent_collection_id → collections.id`) via an Alembic migration. No new table.
DuckDB/Parquet is untouched by this feature (nesting is purely user-defined-data, per
Constitution Principle II).

**Testing**: Same as 001 — pytest (backend, against real Postgres) and Vitest (frontend).

**Target Platform**: Same as 001 — web application, no change.

**Project Type**: web (extends the existing `backend/` and `frontend/` from 001; no new
top-level structure).

**Performance Goals**: Nesting/moving/un-nesting is a single `PATCH` request plus a UI refetch —
negligible; no new performance concern beyond what 001 already established.

**Constraints**: Nesting MUST NOT alter price calculation (spec FR-009) — `price_calculation.py`
already iterates every Collection in `architecture.collections` regardless of any parent
relationship, so no change to that module is needed; this plan only needs to confirm that
invariant holds and add a test proving it. A VPC's `parent_collection_id` MUST always be `NULL`
(only Application Components may be nested — spec FR-004).

**Scale/Scope**: Unchanged from 001.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Pricing Data Integrity | This feature never touches DuckDB/Parquet or price calculation logic; it is entirely a Postgres-side relationship between two rows the user already owns. | PASS |
| II. Clear Data-Layer Separation | `parent_collection_id` is a plain FK within the existing Postgres `collections` table — no vendor data involved. | PASS |
| III. Provider-Extensibility by Design | No regression: `type = 'vpc'`/`'application_component'` already existed in 001's schema; this feature adds a relationship between existing typed rows, not a new AWS-specific concept. | PASS |
| IV. Type-Safe Frontend/Backend Contract | `CollectionOut.parent_collection_id` and the new `PATCH /collections/{id}` request/response flow through the same FastAPI→OpenAPI→`openapi-typescript` pipeline and CI drift gate already built in 001 — no new tooling needed, just re-running it. | PASS |
| V. Test-First Development | DB constraint tests (only `application_component` may have a parent) and the `PATCH /collections/{id}` contract tests are written before their implementation per `tasks.md`, same discipline as 001. | PASS (enforced at task-generation/implementation time) |
| VI. Simplicity & YAGNI | Uses React Flow's *built-in* parent/child node support instead of a custom nesting framework; one column, one endpoint, no new tables or services. | PASS |

No violations — Complexity Tracking table is empty.

**Post-Design Re-Check** (after Phase 1 `data-model.md`/`contracts/api.md`): all six gates still
PASS. `data-model.md` confirms the DB-level guard (`parent_collection_id` non-null only when
`type = 'application_component'`) plus the app-level guard (parent must reference a VPC in the
same Architecture) together fully enforce FR-004/FR-005 without a trigger, keeping Principle VI
intact. No new complexity was introduced during design.

## Project Structure

### Documentation (this feature)

```text
specs/002-vpc-component-nesting/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command) — delta on 001's Collection
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── api.md            # delta on 001's contracts/api.md — one new/changed endpoint
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

No new top-level structure — this feature extends files already established by
`001-assemble-price-aws-architecture`:

```text
backend/
├── src/
│   ├── models/
│   │   ├── orm.py                # ADD: Collection.parent_collection_id + constraints
│   │   └── schemas.py             # ADD: CollectionOut.parent_collection_id, a small
│   │                                #      CollectionNestingUpdate request schema
│   ├── api/
│   │   └── collections.py          # ADD: PATCH /collections/{id}
│   ├── services/
│   │   └── architecture_service.py  # EXTEND: soft_delete_collection's cascade also
│   │                                  #         un-nests (not deletes) any children;
│   │                                  #         ADD: a helper validating a nesting change
│   └── db/migrations/versions/
│       └── 0002_collection_nesting.py  # NEW migration
└── tests/                                # ADD contract/unit/integration tests for the above

frontend/
├── src/
│   ├── api/client.ts                # ADD: a call for PATCH /collections/{id}
│   └── pages/
│       └── CreateArchitecturePage.tsx  # EXTEND: React Flow parentId wiring (no extent),
│                                        #         drop-target detection on drag-stop,
│                                        #         VPC node styled as a container
└── tests/                                # ADD component tests for the above
```

**Structure Decision**: No structural change to the web application split established in 001.
This feature is additive within the existing `backend/` and `frontend/` trees.

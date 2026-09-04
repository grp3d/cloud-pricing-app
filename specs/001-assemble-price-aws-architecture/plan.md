# Implementation Plan: AWS Architecture Assembly & Pricing

**Branch**: `001-assemble-price-aws-architecture` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-assemble-price-aws-architecture/spec.md`

## Summary

Let a signed-in user create a reusable AWS **Architecture**, group AWS SKUs into
**Collections** (Application Component or VPC), link Collections with **Data Connectors**
(optionally attaching a gateway-type SKU), enter per-SKU pricing inputs (term, purchase option,
usage quantity), and calculate a total price sourced live from the AWS pricing data. Technical
approach: a FastAPI backend exposes a typed REST API backed by two datastores per the
constitution's data-layer separation — PostgreSQL for all user-defined objects (Architectures,
Collections, Connectors, SKU Selections, users) and DuckDB queries over the existing read-only
AWS pricing Parquet files for catalog search and price lookups. A React + Vite + TypeScript
frontend consumes the API via types generated from its OpenAPI schema, with a node/edge canvas
for the Collections+Connectors builder.

## Technical Context

**Language/Version**: Python 3.12+ (backend; local dev environment runs 3.14), TypeScript 5.x /
Node.js 20+ (frontend tooling)

**Primary Dependencies**: Backend — FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + Alembic
(Postgres ORM/migrations), the `duckdb` Python package (Parquet queries), `psycopg` (async
Postgres driver). Frontend — React 18+, Vite, `@tanstack/react-query` (server state),
`@xyflow/react` (React Flow — Collections-as-nodes / Data Connectors-as-edges canvas),
`openapi-typescript` (generates TS types from the backend's OpenAPI schema per the constitution's
Type-Safe Contract principle).

**Storage**: PostgreSQL (User, Architecture, Collection, Data Connector, SKU Selection — all
user-defined data). DuckDB reading the existing Parquet files at
`/Users/ghubs/Development/repos/personal/cloud-pricing/DATA/pricing_aws/parquet` (read-only;
most recent `snapshot_date` partition used unless a feature explicitly needs history).

**Testing**: Backend — pytest, pytest-asyncio, httpx (API contract/integration tests), a
disposable/test Postgres schema, and the real Parquet fixture data for DuckDB-layer tests.
Frontend — Vitest + React Testing Library for component/unit tests.

**Target Platform**: Web application — modern evergreen browsers (frontend), containerized Linux
server (backend API).

**Project Type**: web (frontend + backend, detected and confirmed — see Project Structure)

**Performance Goals**: Catalog search (service_code/product_family/text filter over ~173k SKU
rows per region/snapshot) returns in <1s p95, using DuckDB's columnar scan over the existing
`snapshot_date=`/`region=` partitions. Price calculation for a typical Architecture (tens of SKU
Selections) completes in <1s p95 (a handful of indexed point lookups against `price_fact`).

**Constraints**: DuckDB/Parquet access MUST remain strictly read-only (Constitution Principle I).
No vendor pricing value may be cached into Postgres as if it were source data (Principle II).
Provider MUST be modeled as an explicit field/dimension on Architecture, not hardcoded into
table/type names, even though only `aws` is valid in v1 (Principle III).

**Scale/Scope**: Not specified in the feature spec (flagged Outstanding/low-impact during
clarification); assumed early-stage/internal usage — tens of concurrent users, low hundreds of
Architectures total. Re-evaluate if this assumption proves wrong; no architectural decision here
is hard-blocked on a specific number.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Pricing Data Integrity | Backend's pricing-data access layer only ever reads from DuckDB/Parquet (never writes); every calculated price is traced to the `snapshot_date` partition used; FR-011/FR-012/FR-018 require flagging unpriceable SKUs and data-source outages rather than estimating. | PASS |
| II. Clear Data-Layer Separation | Postgres schema (data-model.md) holds only user-defined objects; `SKU Selection` stores a reference (`service_code` + `sku`) to the vendor catalog, never a copied price. Catalog search/pricing logic lives in a dedicated read-only DuckDB access layer, never queried from Postgres. | PASS |
| III. Provider-Extensibility by Design | `Architecture.provider` is a real column (`aws` today), not baked into table names or endpoint paths (`/architectures`, not `/aws-architectures`). SKU Selections store `service_code`/`sku` generically, not AWS-typed fields. | PASS |
| IV. Type-Safe Frontend/Backend Contract | FastAPI Pydantic models are the single source of truth for the OpenAPI schema; `openapi-typescript` generates the frontend's types in CI/build, failing the build on drift. No hand-maintained request/response types. | PASS |
| V. Test-First Development | Pricing calculation, DuckDB catalog/price queries, and Postgres read/write logic for Architectures/Collections/Connectors/SKU Selections all get tests written first per tasks.md (generated next by `/speckit-tasks`). UI-only presentational components may follow tests-after. | PASS (enforced at task-generation/implementation time) |
| VI. Simplicity & YAGNI | No GCP/Azure code paths beyond the inert `provider` value already on the entity; no speculative plugin architecture; React Flow is used only for the one screen that is literally a node/edge diagram (Create Architecture page), not introduced project-wide. | PASS |

No violations — Complexity Tracking table is empty.

**Post-Design Re-Check** (after Phase 1 `data-model.md`/`contracts/api.md`): all six gates still
PASS. `data-model.md` confirms `SKU Selection` stores only `service_code`/`sku` references, never
a copied price (Principle II); `Architecture.provider` remains a real enum column, never baked
into a path or table name (Principle III); `contracts/api.md`'s `503` vs. empty-`200` split for
the pricing data source keeps Principle I's no-fabricated-values rule enforceable at the API
boundary. No new complexity was introduced during design.

## Project Structure

### Documentation (this feature)

```text
specs/001-assemble-price-aws-architecture/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── api.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── main.py              # FastAPI app entrypoint
│   ├── api/                 # Route handlers (architectures, collections, connectors,
│   │                         # sku-selections, catalog, providers)
│   ├── models/               # Pydantic request/response schemas + SQLAlchemy ORM models
│   ├── services/              # Business logic: architecture ops, price calculation
│   ├── pricing_data/           # Read-only DuckDB/Parquet access layer (catalog search,
│   │                            # price lookups) — the only code that touches Parquet
│   └── db/                      # Postgres session/engine, Alembic migrations
└── tests/
    ├── contract/                # API request/response contract tests
    ├── integration/              # End-to-end flows against a real test Postgres + Parquet fixture
    └── unit/                      # Pure logic (price calculation, validation rules)

frontend/
├── src/
│   ├── api/                 # Generated OpenAPI types + a thin typed client
│   ├── components/           # Shared UI (catalog search/filter panel, pricing input form, ...)
│   ├── pages/                  # LandingPage (provider + Architecture list + pricing panel),
│   │                            # CreateArchitecturePage (React Flow canvas)
│   └── services/                # Frontend-side helpers (e.g., price formatting)
└── tests/
    ├── unit/
    └── integration/
```

**Structure Decision**: Web application split into `backend/` (FastAPI) and `frontend/`
(React + Vite + TypeScript) at the repository root, per the constitution's fixed technology
stack. Both are new — this is the first feature building real application code in this repo.

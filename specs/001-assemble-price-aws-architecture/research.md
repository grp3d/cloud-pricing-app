# Phase 0 Research: AWS Architecture Assembly & Pricing

Most technical decisions for this feature were already fixed by the project constitution
(`.specify/memory/constitution.md`) or resolved during `/speckit-specify`/`/speckit-clarify`.
This document covers the remaining implementation-level choices needed before design.

## 1. DuckDB access: Python package vs. CLI subprocess

- **Decision**: Use the `duckdb` Python package, queried directly from the backend's
  `pricing_data/` module via parameterized SQL against `read_parquet(...)` globs.
- **Rationale**: In-process queries avoid subprocess/CLI overhead and quoting/escaping risk,
  return results as native Python objects (or directly as Arrow/pandas if needed), and integrate
  cleanly with FastAPI's async request lifecycle (DuckDB calls run in a thread pool since the
  Python driver is sync). The CLI is only needed for ad-hoc exploration (already used during
  spec/clarify to inspect the schema).
- **Alternatives considered**: Shelling out to the `duckdb` CLI per query — rejected: slower,
  harder to parameterize safely, and produces text output that must be re-parsed.

## 2. Which Parquet snapshot to query

- **Decision**: At query time, resolve the latest available `snapshot_date` partition under
  each of `service_dim/`, `product_dim/`, `product_attribute/`, `region_dim/`, `price_fact/`
  (they are independently partitioned by date, confirmed during clarification — e.g.
  `price_fact/snapshot_date=2026-09-03/region=us-east-1/part-0.parquet`), and use that date
  consistently across all five tables within a single request (catalog search or price
  calculation) so results are never a mix of two different days' data.
- **Rationale**: Per Constitution Principle I, every price must be traceable to a specific
  snapshot; resolving and pinning one snapshot date per request makes that traceability
  trivial (return the snapshot date used alongside the calculation result) and avoids
  cross-snapshot inconsistency within one calculation.
- **Alternatives considered**: Always hardcoding "the newest date across all five tables
  independently" per-table — rejected: a partially-refreshed data drop could silently mix two
  different days' data within one price calculation.

## 3. Postgres access layer

- **Decision**: SQLAlchemy 2.0 in async mode with `psycopg` (v3, async driver), Alembic for
  migrations.
- **Rationale**: SQLAlchemy 2.0's async support is mature and idiomatic with FastAPI's async
  route handlers; Alembic is the de facto migration tool for SQLAlchemy and gives an explicit,
  reviewable migration history — useful given the constitution requires deliberate schema
  evolution (Technology Stack & Architecture Constraints section).
- **Alternatives considered**: A lighter query builder (e.g., raw `psycopg` + hand-written SQL)
  — rejected as unnecessary friction for a schema with real relationships (FKs, cascading soft
  deletes) where an ORM's relationship handling pays for itself; a second ORM (e.g., Tortoise) —
  rejected, no advantage over SQLAlchemy for this project's needs.

## 4. Frontend/backend typed contract

- **Decision**: FastAPI generates its OpenAPI schema from the Pydantic models (already
  automatic); `openapi-typescript` runs as a build/dev step to generate `frontend/src/api/`
  types from that schema. A thin typed fetch wrapper (not a full generated client/hooks
  library) calls the API using those types.
- **Rationale**: Satisfies Constitution Principle IV (typed contract, build fails on drift)
  with the smallest possible toolchain — `openapi-typescript` only generates types, no runtime
  dependency, no code-gen magic to debug. Data-fetching stays on `@tanstack/react-query`, which
  the team already needs for caching/loading states regardless of the client approach.
- **Alternatives considered**: `orval` (generates full client + React Query hooks) — more
  automation but more generated surface area and a heavier build dependency; deferred as
  unnecessary for v1's endpoint count. Hand-written `fetch` calls with manually maintained
  types — rejected outright, this is exactly what Principle IV disallows.

## 5. Collections + Data Connectors canvas (Create Architecture page)

- **Decision**: `@xyflow/react` (React Flow) renders Collections as nodes and Data Connectors
  as edges; a separate catalog search/filter panel provides SKUs that get added into a
  selected Collection node (not dragged directly onto the canvas in v1 — a click/"Add" action
  from the search results into the currently-selected Collection is simpler to build correctly
  and matches the functional requirements, which never require a specific drag gesture).
- **Rationale**: The doc's own mockup and the spec's data model (Collections as nodes,
  Data Connectors as directed links between them) is *exactly* the node/edge graph shape React
  Flow is built for — selection, connecting two nodes by drawing an edge, and per-node/per-edge
  detail panels are built-in interactions, not bespoke code to write and test from scratch.
- **Alternatives considered**: A generic drag-and-drop library (e.g., `@dnd-kit`) with a
  hand-rolled connector-drawing implementation — rejected: reimplements what React Flow already
  solves, more custom code to test per Principle V and more surface area than Principle VI
  (Simplicity/YAGNI) supports. A full diagramming suite (e.g., a commercial canvas SDK) —
  rejected as unjustified cost/complexity for this scope.

## 6. Soft delete implementation

- **Decision**: A nullable `deleted_at` timestamp column on Architecture, Collection, and Data
  Connector. All read queries filter `deleted_at IS NULL` by default; delete endpoints set the
  timestamp rather than issuing a `DELETE`.
- **Rationale**: Simplest pattern that satisfies FR-013/FR-014/FR-015's soft-delete requirement
  and preserves data per Constitution's data-integrity spirit; a timestamp (vs. a boolean flag)
  also records *when*, which costs nothing extra and is useful for future auditing without
  building an audit log now (YAGNI).
- **Alternatives considered**: A separate `status` enum column — no material benefit over a
  nullable timestamp for the one active/deleted transition this feature needs; a full audit-log
  table — deferred, not required by any FR.

## 7. Pricing data source outage handling (FR-018)

- **Decision**: The `pricing_data` access layer raises a distinct exception type when a DuckDB
  query fails or the expected Parquet path is unreadable; the API layer maps that to a `503`
  response with a machine-readable error code the frontend checks to render the blocking error
  state (distinct from an empty `200` result for a genuine zero-match search).
- **Rationale**: Keeps the "data source is down" signal structurally distinct from "no results"
  at every layer, which is what FR-018/the Edge Cases section require — the frontend cannot
  accidentally conflate the two if the HTTP status itself differs.
- **Alternatives considered**: Returning a `200` with an `error` field in the body — rejected,
  makes it easier for a future endpoint to forget to check the field and misrender an outage as
  empty results.

## Outstanding items

None. All Technical Context fields are resolved; no `NEEDS CLARIFICATION` markers remain.

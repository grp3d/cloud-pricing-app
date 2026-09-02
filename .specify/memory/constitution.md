<!--
Sync Impact Report
- Version change: (unversioned template) → 1.0.0
- Modified principles: n/a (initial ratification, all principles newly defined)
- Added sections:
  - Core Principles: I. Pricing Data Integrity, II. Clear Data-Layer Separation,
    III. Provider-Extensibility by Design, IV. Type-Safe Frontend/Backend Contract,
    V. Test-First Development, VI. Simplicity & YAGNI
  - Technology Stack & Architecture Constraints
  - Development Workflow & Quality Gates
  - Governance
- Removed sections: none (this is the first concrete ratification of the constitution)
- Templates requiring follow-up: none — dependent templates/commands read this file at
  runtime and are not modified by this command.
- Deferred placeholders: none remaining.
-->

# Cloud Pricing UI Constitution

## Core Principles

### I. Pricing Data Integrity
Vendor pricing data (initially AWS, later GCP/Azure) MUST be treated as read-only,
authoritative source data. It arrives as Parquet files produced by an upstream project and
is queried via DuckDB; the application MUST NOT hand-edit, estimate, or fabricate pricing
values anywhere in the frontend, backend, or database layer. Every price surfaced to a user
MUST be traceable back to a specific pricing dataset/version so staleness or provenance can
be verified. If the upstream Parquet data does not contain a value a user needs, the
application MUST surface that gap explicitly (e.g., "unavailable") rather than approximate
it.

Rationale: This is a pricing tool; a single silently-wrong number destroys user trust. Since
the pricing data is owned and refreshed by a separate upstream project, this codebase's
only correct relationship to it is faithful, attributable retrieval.

### II. Clear Data-Layer Separation
The system maintains two categorically different kinds of data, and the boundary between
them MUST stay explicit in code, schema, and naming:
- **Vendor pricing data**: Parquet files queried through DuckDB. Read-only from this
  application's perspective.
- **User-defined data**: collections, per-collection user inputs, and linking/mapping
  tables that associate vendor cloud services to internal categorizations (application
  components, VPCs, machines, etc.). This lives in Postgres and is the only data this
  application writes.

Business logic MUST NOT blur the two (e.g., no writing derived pricing values into
Postgres as if they were source data; no querying Postgres as a source of vendor pricing
truth). Linking tables in Postgres reference vendor services by stable identifiers, not by
copying vendor attributes that could drift from the Parquet source.

Rationale: Keeping vendor truth and user truth in physically and logically separate stores
prevents accidental overwrites of authoritative pricing data and makes it obvious which
store to query for which purpose.

### III. Provider-Extensibility by Design
Development MUST target AWS first, and no other provider is implemented until AWS has a
working end-to-end version. However, domain models (service categorization, linking
tables, pricing query interfaces, component/collection abstractions) MUST NOT hardcode
AWS-specific assumptions in a way that would require a rewrite — rather than an extension —
to add GCP or Azure later. Concretely: provider MUST be a modeled dimension (e.g., a field
or namespace), not an implicit assumption baked into table names, endpoint paths, or type
names.

Rationale: Multi-provider support is an explicit, known future requirement. Paying a small,
disciplined cost now (naming, modeling) avoids a costly migration later, without requiring
speculative multi-provider code paths today.

### IV. Type-Safe Frontend/Backend Contract
The FastAPI backend and the React + Vite + TypeScript frontend MUST communicate through a
strictly typed contract. API request/response shapes MUST be defined once (e.g., via
FastAPI's Pydantic models generating an OpenAPI schema) and used to generate or validate
corresponding TypeScript types — untyped, hand-maintained, or ad-hoc JSON shapes crossing
the frontend/backend boundary are not permitted. Any drift between backend schema and
frontend types MUST fail a build or type-check, not surface as a runtime bug.

Rationale: Pricing and collection data has enough structural complexity (nested
components, categorizations, per-collection inputs) that untyped contracts are a
recurring, avoidable source of defects.

### V. Test-First Development
Pricing calculation logic, DuckDB query logic, and Postgres read/write logic for
user-defined objects (collections, inputs, linking tables) MUST have tests written and
reviewed before the corresponding implementation is written. Red-Green-Refactor applies:
a failing test demonstrating the requirement, then the minimal implementation to pass it.
UI-only presentational code MAY follow tests-after where a test-first cycle adds no
verification value, but any logic that computes or transforms a price or a user-defined
data relationship is NON-NEGOTIABLE test-first.

Rationale: Correctness of pricing output is the product's core value proposition; the
cost of a testing discipline is far lower than the cost of a wrong price shown to a user.

### VI. Simplicity & YAGNI
Prefer the simplest design that satisfies the current AWS-first requirement. Do not build
generalized multi-cloud abstractions, speculative configuration systems, or premature
plugin architectures ahead of an actual second provider being implemented. Complexity
(a new service boundary, a new abstraction layer, a new data store) MUST be justified by a
concrete, current requirement, not a hypothetical future one.

Rationale: Principle III already protects the codebase from AWS-only lock-in through
careful naming and modeling; that is sufficient. Building the abstractions themselves
before they are needed adds cost and risk without corresponding present value.

## Technology Stack & Architecture Constraints

- **Frontend**: React + Vite + TypeScript.
- **Backend**: Python, FastAPI.
- **Vendor pricing data**: Parquet files (produced by an upstream project), queried via
  DuckDB. Read-only.
- **Application data**: PostgreSQL, for user-defined collections, last-entered inputs per
  collection per user, and linking tables mapping vendor cloud services to internal
  categorizations (application components, VPCs, machines, etc.).
- **Provider scope**: AWS only until an AWS end-to-end version is working; GCP and Azure
  are explicitly deferred, not in-scope for current implementation work.

Any deviation from this stack (introducing a new datastore, a new frontend framework, a
different API style) requires an explicit constitution amendment, not an ad-hoc choice
inside a feature branch.

## Development Workflow & Quality Gates

- Every change touching pricing calculation, DuckDB queries, or Postgres schema/queries for
  user-defined objects MUST include tests per Principle V before merge.
- Every change touching the API surface (FastAPI routes/schemas) MUST keep frontend
  TypeScript types in sync per Principle IV before merge; a build/type-check MUST pass.
- Code review MUST verify: no hardcoded/estimated pricing values (Principle I), no blurring
  of the vendor-data/user-data boundary (Principle II), no AWS-only assumptions baked into
  new shared abstractions (Principle III), and no unjustified complexity (Principle VI).
- Feature specs and plans produced by Spec Kit commands MUST be checked against this
  constitution during `/speckit-analyze`; unresolved conflicts block `/speckit-implement`.

## Governance

This constitution supersedes ad-hoc conventions for this project. Amendments require:
1. A documented rationale for the change (what principle/section changes and why).
2. A version bump per semantic versioning:
   - **MAJOR**: backward-incompatible governance changes or principle removals/redefinitions.
   - **MINOR**: a new principle or materially expanded guidance added.
   - **PATCH**: wording clarifications or non-semantic fixes.
3. Updating `Last Amended` to the date of the change.

All pull requests and code reviews MUST verify compliance with this constitution.
Complexity that is not justified by Principle III or a current concrete requirement MUST
be flagged and simplified per Principle VI. Runtime development guidance for AI agents
working in this repository (Spec Kit commands, templates) reads this file as the source of
truth for these principles.

**Version**: 1.0.0 | **Ratified**: 2026-09-02 | **Last Amended**: 2026-09-02

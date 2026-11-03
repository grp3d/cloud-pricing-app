<!--
Sync Impact Report
- Version change: 1.0.0 → 1.1.0
- Bump rationale: MINOR. AWS reached a working end-to-end version (feature 018), which is the
  condition the old Principle III and the stack section set for adding providers. GCP and Azure
  move into scope, and the guidance on multi-provider design is materially expanded. No
  principle is removed, and the gate is met rather than reversed.
- Modified principles:
  - I. Pricing Data Integrity: now covers AWS, GCP and Azure; adds per-provider snapshot
    independence and no currency conversion.
  - II. Clear Data-Layer Separation: user-defined data now includes per-user preferences.
  - III. Provider-Extensibility by Design → III. Multi-Provider by Design: the AWS-first gate
    is recorded as met; adds shared request/response shapes with provider-specific retrieval
    behind them.
  - V. Test-First Development: provider-specific retrieval and normalization code is now
    explicitly test-first.
  - VI. Simplicity & YAGNI: shared abstractions are justified for implemented providers only;
    still no speculative abstractions (other providers, LLM agent integrations).
- Added sections: none
- Removed sections: none
- Technology Stack & Architecture Constraints: provider scope is now AWS, GCP and Azure; pricing
  data is per-provider tables; application data includes user preferences.
- Development Workflow & Quality Gates: adds a review check for provider-specific code staying
  behind the shared contract.
- Templates requiring follow-up: none. Dependent templates and commands read this file at
  runtime and are not modified by this command.
- Deferred placeholders: none.
-->

# Cloud Pricing UI Constitution

## Core Principles

### I. Pricing Data Integrity
Vendor pricing data (AWS, GCP and Azure) MUST be treated as read-only, authoritative source
data. It arrives as Parquet files produced by an upstream project and is queried via DuckDB;
the application MUST NOT hand-edit, estimate, or fabricate pricing values anywhere in the
frontend, backend, or database layer. Every price surfaced to a user MUST be traceable back
to a specific provider, pricing dataset and version so staleness or provenance can be
verified. If the upstream Parquet data does not contain a value a user needs (including a
price the source omits, stores as null, or publishes in another currency), the application
MUST surface that gap explicitly (e.g., "unavailable") rather than approximate it, treat it as
zero, or convert it.

Each provider's snapshots MUST be read and validated independently: one provider's failed,
partial or stale snapshot MUST NOT hide or block another provider's data.

Rationale: This is a pricing tool; a single silently-wrong number destroys user trust. Since
the pricing data is owned and refreshed by a separate upstream project, this codebase's
only correct relationship to it is faithful, attributable retrieval.

### II. Clear Data-Layer Separation
The system maintains two categorically different kinds of data, and the boundary between
them MUST stay explicit in code, schema, and naming:
- **Vendor pricing data**: Parquet files queried through DuckDB. Read-only from this
  application's perspective.
- **User-defined data**: collections, per-collection user inputs, per-user preferences, and
  linking/mapping tables that associate vendor cloud services to internal categorizations
  (application components, VPCs, machines, service categories, etc.). This lives in Postgres
  and is the only data this application writes.

Business logic MUST NOT blur the two (e.g., no writing derived pricing values into
Postgres as if they were source data; no querying Postgres as a source of vendor pricing
truth). Linking tables in Postgres reference vendor services by stable identifiers, not by
copying vendor attributes that could drift from the Parquet source.

Rationale: Keeping vendor truth and user truth in physically and logically separate stores
prevents accidental overwrites of authoritative pricing data and makes it obvious which
store to query for which purpose.

### III. Multi-Provider by Design
AWS was built first and reached a working end-to-end version (feature 018), which met the
original gate for adding providers. AWS, GCP and Azure are now all in scope. Provider MUST
stay a modeled dimension (a field or namespace), never an implicit assumption baked into
table names, endpoint paths, or type names.

Requests and responses between the frontend and backend MUST have the same shape for every
provider, varying only by the provider value and clearly marked provider-specific fields.
Each common operation (for example, search a catalog or price a selection in a location) MUST
be backed by provider-specific retrieval and transformation code that reads that provider's
own tables; normalizing across providers happens there, in the application, not by reshaping
vendor data. Adding a provider MUST be an extension (a new provider-specific implementation),
not a rewrite of shared code.

Rationale: Each provider publishes pricing in a deliberately different shape. A shared
contract with per-provider implementations keeps the UI simple and lets each provider's
quirks stay contained and testable.

### IV. Type-Safe Frontend/Backend Contract
The FastAPI backend and the React + Vite + TypeScript frontend MUST communicate through a
strictly typed contract. API request/response shapes MUST be defined once (e.g., via
FastAPI's Pydantic models generating an OpenAPI schema) and used to generate or validate
corresponding TypeScript types — untyped, hand-maintained, or ad-hoc JSON shapes crossing
the frontend/backend boundary are not permitted. Any drift between backend schema and
frontend types MUST fail a build or type-check, not surface as a runtime bug. Extensible
stored structures (such as user preferences) MUST still cross the boundary as typed,
versioned shapes.

Rationale: Pricing and collection data has enough structural complexity (nested
components, categorizations, per-collection inputs) that untyped contracts are a
recurring, avoidable source of defects.

### V. Test-First Development
Pricing calculation logic, DuckDB query logic (including each provider's retrieval and
normalization code), and Postgres read/write logic for user-defined objects (collections,
inputs, preferences, linking tables) MUST have tests written and reviewed before the
corresponding implementation is written. Red-Green-Refactor applies: a failing test
demonstrating the requirement, then the minimal implementation to pass it. UI-only
presentational code MAY follow tests-after where a test-first cycle adds no verification
value, but any logic that computes or transforms a price, a price trend, or a user-defined
data relationship is NON-NEGOTIABLE test-first.

Rationale: Correctness of pricing output is the product's core value proposition; the
cost of a testing discipline is far lower than the cost of a wrong price shown to a user.

### VI. Simplicity & YAGNI
Prefer the simplest design that satisfies the current requirement. Shared multi-provider
abstractions are justified only for providers that are actually implemented (AWS, GCP and
Azure). Do not build abstractions, configuration systems, or plugin architectures for
providers or capabilities that are not being implemented (for example, further cloud
providers or LLM agent integrations recorded as future state). Complexity (a new service
boundary, a new abstraction layer, a new data store) MUST be justified by a concrete,
current requirement, not a hypothetical future one.

Rationale: Principle III protects the codebase from single-provider lock-in through a shared
contract; building abstractions beyond the providers and features actually in scope adds
cost and risk without corresponding present value.

## Technology Stack & Architecture Constraints

- **Frontend**: React + Vite + TypeScript.
- **Backend**: Python, FastAPI.
- **Vendor pricing data**: Parquet files (produced by an upstream project), one set of
  provider-specific tables per provider, located through each provider's own manifests and
  queried via DuckDB. Read-only.
- **Application data**: PostgreSQL, for user-defined collections, last-entered inputs per
  collection per user, per-user preferences, and linking tables mapping vendor cloud services
  to internal categorizations (application components, VPCs, machines, service categories,
  etc.).
- **Provider scope**: AWS, GCP and Azure. Adding any other provider requires a constitution
  amendment.

Any deviation from this stack (introducing a new datastore, a new frontend framework, a
different API style) requires an explicit constitution amendment, not an ad-hoc choice
inside a feature branch.

## Development Workflow & Quality Gates

- Every change touching pricing calculation, DuckDB queries, or Postgres schema/queries for
  user-defined objects MUST include tests per Principle V before merge.
- Every change touching the API surface (FastAPI routes/schemas) MUST keep frontend
  TypeScript types in sync per Principle IV before merge; a build/type-check MUST pass.
- Code review MUST verify: no hardcoded/estimated pricing values (Principle I), no blurring
  of the vendor-data/user-data boundary (Principle II), provider-specific code kept behind the
  shared contract with no single-provider assumptions in shared code (Principle III), and no
  unjustified complexity (Principle VI).
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

**Version**: 1.1.0 | **Ratified**: 2026-09-02 | **Last Amended**: 2026-11-02

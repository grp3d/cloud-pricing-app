<!--
Sync Impact Report
- Version change: 1.2.0 → 1.3.0
- Bump rationale: MINOR. Principle V gains a coverage rule: every acceptance scenario and
  measurable success criterion maps to an automated test or is marked [MANUAL: reason]. No
  principle is removed or redefined.
- Modified principles:
  - V. Test-First Development: acceptance coverage by automated tests or [MANUAL] marks; a
    feature is complete only when those tests pass; live-model evaluations are reported
    separately and are not a completion gate; the end-of-phase manual checklist holds only
    [MANUAL] items; checks needing real pricing snapshots or a real model are [MANUAL] or
    opt-in runs.
- Added principles: none
- Added sections: none
- Removed sections: none
- Development Workflow & Quality Gates: /speckit-analyze flags any acceptance scenario or
  success criterion with neither a mapped test nor a [MANUAL] mark.
- Source: feature 026's manual walk-through, which repeated checks already automated.
- Applies to specs written from this version on; existing specs/0NN records are not rewritten.
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

Every monetary figure the AI agent shows (price, total, difference, percentage, savings) MUST
come from the app's pricing operations. The model MAY choose which operations to run and MAY
explain their results; it MUST NOT calculate, estimate, round or recall a price itself.
Anything that can't be priced is shown as unpriceable, as the rest of the app does. Agent
figures are in USD, shown to 2 decimal places, and totals are summed from the pricing engine's
unrounded values so they match the Pricing tab.

Each provider's snapshots MUST be read and validated independently: one provider's failed,
partial or stale snapshot MUST NOT hide or block another provider's data.

Rationale: This is a pricing tool; a single silently-wrong number destroys user trust. Since
the pricing data is owned and refreshed by a separate upstream project, this codebase's
only correct relationship to it is faithful, attributable retrieval. Language models are
unreliable at arithmetic and at remembering prices, so the agent explains figures but never
produces them.

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

Automated tests MUST NOT call live language models; they MUST use a deterministic, scripted
model. Evaluations against real models are a separate, opt-in run that produces a pass/fail
report per model. Each AI agent feature's spec MUST include golden conversations (example user
messages, the follow-up questions the agent should ask, and the expected outcome); together
they form the shared evaluation set.

Every acceptance scenario and measurable success criterion in a spec MUST map to an automated
test (unit, API, end-to-end, or a scripted-model evaluation case), or be marked
`[MANUAL: reason]` in the spec. A feature is complete only when those automated tests pass;
opt-in live-model evaluations are reported separately and are not a completion gate. The
end-of-phase manual checklist contains only `[MANUAL]` items. Automated tests use the scripted
model and fixed pricing fixtures; checks that need real pricing snapshots or a real model are
`[MANUAL]` or opt-in runs.

Rationale: Correctness of pricing output is the product's core value proposition; the
cost of a testing discipline is far lower than the cost of a wrong price shown to a user.
Tests must be free, fast and repeatable, while real-model quality still needs measuring. A
manual check is kept for what only a person can judge, not repeated for what a test proves.

### VI. Simplicity & YAGNI
Prefer the simplest design that satisfies the current requirement. Shared multi-provider
abstractions are justified only for providers that are actually implemented (AWS, GCP and
Azure). Do not build abstractions, configuration systems, or plugin architectures for
providers or capabilities that are not being implemented (for example, further cloud
providers recorded as future state). Complexity (a new service
boundary, a new abstraction layer, a new data store) MUST be justified by a concrete,
current requirement, not a hypothetical future one.

Rationale: Principle III protects the codebase from single-provider lock-in through a shared
contract; building abstractions beyond the providers and features actually in scope adds
cost and risk without corresponding present value.

### VII. The Agent Acts as the User, and the User Decides
- **The agent is a user, not an administrator.** It MUST act only through the operations,
  validation and permissions the logged-in user already has. It MUST NOT get special access to
  data, to other users' architectures or to storage. It is available to named accounts only,
  never to guests.
- **Propose, then apply.** Any change to saved data (creating, changing or importing an
  architecture) MUST first be shown as a proposal the user can review. Nothing is saved until
  the user accepts. The changes made in response to one user message MUST be undoable in one
  action.
- **Content is data, not instructions.** Text inside architectures (names, descriptions,
  imported content) and any operation output MUST be treated as data. It can never change the
  agent's rules or trigger operations.
- **Transparency.** Users MUST be able to see which operations the agent ran, with what
  inputs, and the pricing snapshot date behind every figure. The agent states the assumptions
  it made.

Rationale: Mistakes and manipulation stay limited to what the user could already do, users
stay in control of their work, shared architectures are untrusted input, and every answer can
be checked.

### VIII. Replaceable Models, Bounded Cost, Protected Secrets
- **No dependence on one model vendor.** No feature may require a specific model or vendor.
  The provider and model MUST be chosen by settings, and supported models are checked against
  the shared evaluation set (Principle V).
- **The app works without the agent.** The agent MUST be able to be switched off, and the rest
  of the app MUST work fully when it is off or unavailable.
- **Bounded cost.** Usage MUST have per-user limits and a global monthly cap. Once a limit is
  reached, no further model usage happens.
- **Secrets stay on the server.** Model keys MUST NOT reach the browser and MUST NOT be stored
  in the database.

Rationale: This avoids lock-in, allows free local development, keeps the app usable when a
model service is down, and keeps a reachable agent endpoint from becoming an open billing risk.

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
- **AI agent model**: a language model reached from the backend only, with the provider and
  model chosen by settings (Principle VIII). It is not a datastore and holds no pricing truth.

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
  shared contract with no single-provider assumptions in shared code (Principle III), no
  unjustified complexity (Principle VI), agent actions limited to the user's own operations and
  permissions with changes proposed before they are saved (Principle VII), and no hard
  dependence on one model vendor, unbounded model usage, or model keys outside the server
  (Principle VIII).
- Every change touching the AI agent MUST keep its automated tests on a deterministic,
  scripted model (Principle V); no test in the default run may call a live model.
- `/speckit-analyze` MUST flag any acceptance scenario or success criterion with neither a
  mapped test nor a `[MANUAL]` mark (Principle V).
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

**Version**: 1.3.0 | **Ratified**: 2026-09-02 | **Last Amended**: 2026-11-20

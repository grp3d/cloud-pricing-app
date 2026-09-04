---

description: "Task list for AWS Architecture Assembly & Pricing"
---

# Tasks: AWS Architecture Assembly & Pricing

**Input**: Design documents from `/specs/001-assemble-price-aws-architecture/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md
(all present)

**Tests**: Included. The feature spec doesn't request TDD by name, but Constitution Principle V
(Test-First Development) is NON-NEGOTIABLE for pricing calculation logic, DuckDB query logic, and
Postgres read/write logic for user-defined objects — that covers nearly every backend task below.
Frontend presentational components may follow tests-after per the same principle, so frontend
tasks have no dedicated test tasks in this list.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3) to enable
independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are relative to the repository root and follow `plan.md`'s Project Structure

## Phase 1: Setup

**Purpose**: Project initialization and basic structure (backend/ + frontend/ per plan.md)

- [x] T001 Create the `backend/src/{api,models,services,pricing_data,db}/` and
      `backend/tests/{contract,integration,unit}/` directory skeletons, and the
      `frontend/src/{api,components,pages,services}/` and `frontend/tests/{unit,integration}/`
      directory skeletons, per `plan.md`'s Project Structure
- [x] T002 Initialize the backend Python project with `uv` (`backend/pyproject.toml`), adding
      FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, `duckdb`, `psycopg[binary]`, pytest,
      pytest-asyncio, and httpx as dependencies
- [x] T003 [P] Initialize the frontend Vite + React + TypeScript project (`frontend/package.json`),
      adding `@tanstack/react-query`, `@xyflow/react`, `openapi-typescript`, `vitest`, and
      `@testing-library/react` as dependencies
- [x] T004 [P] Configure backend linting/formatting (ruff) in `backend/pyproject.toml`
- [x] T005 [P] Configure frontend linting/formatting (ESLint + Prettier) in
      `frontend/.eslintrc.cjs` and `frontend/package.json`
- [x] T006 [P] Create the backend settings module (`DATABASE_URL`, AWS pricing Parquet base
      path, per `research.md`) in `backend/src/config.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T007 Configure the async Postgres engine/session in `backend/src/db/session.py`
      (depends on T002, T006)
- [x] T008 Initialize the Alembic migration environment in `backend/alembic.ini` and
      `backend/src/db/migrations/env.py` (depends on T007)
- [x] T009 Implement SQLAlchemy ORM models for User, Architecture, Collection, SKU Selection, and
      Data Connector — including the soft-delete `deleted_at` columns, the `provider`/`type`/
      `pricing_term`/`purchase_option` enums, and the check constraints from `data-model.md`
      (self-connect rejection, exactly-one-parent on SKU Selection) — in
      `backend/src/models/orm.py` (depends on T007)
- [x] T010 Generate the initial Alembic migration for all tables in
      `backend/src/db/migrations/versions/0001_initial.py` (depends on T008, T009)
- [x] T011 [P] Implement Pydantic request/response schemas for all entities per
      `contracts/api.md` in `backend/src/models/schemas.py` (depends on T009)
- [x] T012 [P] Implement the snapshot-date resolution helper (pin one `snapshot_date` across
      `service_dim`/`product_dim`/`product_attribute`/`region_dim`/`price_fact` per
      `research.md` #2) in `backend/src/pricing_data/snapshot.py` (depends on T006)
- [x] T013 [P] Implement the pricing-data-source-outage exception type in
      `backend/src/pricing_data/errors.py` (depends on T006)
- [x] T014 [P] Implement the DuckDB catalog search query function (filter by `service_code`,
      `product_family`, free text; reject an all-empty filter) in
      `backend/src/pricing_data/catalog.py` (depends on T012, T013)
- [x] T015 [P] Implement the DuckDB price lookup query function (`price_fact` by SKU, term,
      purchase option) in `backend/src/pricing_data/pricing.py` (depends on T012, T013)
- [x] T016 Implement the current-user auth dependency (FR-002 — a real, distinct user identity;
      login mechanism per `research.md`) in `backend/src/api/deps.py` (depends on T007)
- [x] T017 Implement the FastAPI app entrypoint, router registration, and the global exception
      handler mapping pricing-data-source errors to `503` (FR-018) in `backend/src/main.py`
      (depends on T013, T016)
- [x] T018 [P] Set up the frontend OpenAPI type-generation script (`openapi-typescript` against
      `/openapi.json`) in `frontend/package.json` and `frontend/src/api/`
- [x] T019 [P] Set up the frontend app shell and router (routes for the landing page and the
      Create Architecture page) in `frontend/src/App.tsx`

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Build and price a single-Collection Architecture (Priority: P1) 🎯 MVP

**Goal**: A user creates an Architecture, adds one Collection, searches the AWS catalog, adds a
SKU with pricing inputs, and calculates a total price.

**Independent Test**: Create one Architecture, add one Collection, search for and add at least
one AWS SKU with pricing inputs, click calculate, and verify a total price is displayed
(`quickstart.md` "Validate: end-to-end assemble-and-price flow").

### Tests for User Story 1 ⚠️

> Write these tests FIRST; ensure they FAIL before implementation (Constitution Principle V)

- [x] T020 [P] [US1] Contract test for `GET /providers` in
      `backend/tests/contract/test_providers.py`
- [x] T021 [P] [US1] Contract test for `POST /architectures`, `GET /architectures`, and
      `GET /architectures/{id}` in `backend/tests/contract/test_architectures.py`
- [x] T022 [P] [US1] Contract test for `POST /architectures/{id}/collections` in
      `backend/tests/contract/test_collections.py`
- [x] T023 [P] [US1] Contract test for `GET /catalog/skus` — including the `400` on an
      all-empty filter and the `503` on a simulated data-source outage — in
      `backend/tests/contract/test_catalog.py`
- [x] T024 [P] [US1] Contract test for `POST /collections/{id}/sku-selections` in
      `backend/tests/contract/test_sku_selections.py`
- [x] T025 [P] [US1] Contract test for `POST /architectures/{id}/calculate` in
      `backend/tests/contract/test_calculate.py`
- [x] T026 [P] [US1] Unit test for the price calculation service — priceable line items sum
      correctly, an unpriceable SKU (FR-011/FR-012) is flagged and excluded from the total, never
      silently omitted or estimated — in `backend/tests/unit/test_price_calculation.py`
- [x] T027 [US1] Integration test for the full assemble-and-price flow (per `quickstart.md`
      section 1) in `backend/tests/integration/test_us1_assemble_and_price.py`

### Implementation for User Story 1

- [x] T028 [US1] Implement the `GET /providers` endpoint (AWS active, GCP/Azure disabled per
      FR-003) in `backend/src/api/providers.py` (depends on T017)
- [x] T029 [US1] Implement `POST /architectures`, `GET /architectures`, and
      `GET /architectures/{id}` endpoints, scoped to the authenticated user (FR-001, FR-002,
      FR-013) in `backend/src/api/architectures.py` (depends on T011, T016)
- [x] T030 [US1] Implement `POST /architectures/{id}/collections` (FR-004) in
      `backend/src/api/collections.py` (depends on T029)
- [x] T031 [US1] Implement `GET /catalog/skus` (FR-005) in `backend/src/api/catalog.py`
      (depends on T014)
- [x] T032 [US1] Implement `POST`/`PATCH`/`DELETE /collections/{id}/sku-selections` (FR-006,
      FR-007) in `backend/src/api/sku_selections.py` (depends on T030)
- [x] T033 [US1] Implement the price calculation service (sum priceable line items via T015,
      flag unpriceable SKUs per FR-011/FR-012) in `backend/src/services/price_calculation.py`
      (depends on T015, T009)
- [x] T034 [US1] Implement `POST /architectures/{id}/calculate` (FR-010) in
      `backend/src/api/calculate.py` (depends on T033)
- [x] T035 [US1] Register the US1 routers in `backend/src/main.py` (depends on T028, T029, T030,
      T031, T032, T034)
- [x] T036 [P] [US1] Build the LandingPage (provider selector + Architecture list) in
      `frontend/src/pages/LandingPage.tsx` (depends on T018, T019)
- [x] T037 [P] [US1] Build the CatalogSearchPanel component (service_code/product_family/text
      filters, FR-005) in `frontend/src/components/CatalogSearchPanel.tsx` (depends on T018)
- [x] T038 [P] [US1] Build the PricingInputsForm component (term, purchase option, usage
      quantity, FR-007) in `frontend/src/components/PricingInputsForm.tsx` (depends on T018)
- [x] T039 [US1] Build the CreateArchitecturePage's single-Collection flow, wiring
      CatalogSearchPanel and PricingInputsForm and the Calculate action/results display in
      `frontend/src/pages/CreateArchitecturePage.tsx` (depends on T036, T037, T038, T035)
- [x] T040 [US1] Run the `quickstart.md` "end-to-end assemble-and-price flow" validation script
      against the running backend and frontend (depends on T035, T039)

**Checkpoint**: User Story 1 is fully functional and independently testable — this is the MVP.

---

## Phase 4: User Story 2 - Compose multi-Collection Architectures with Data Connectors (Priority: P2)

**Goal**: A user links Collections with Data Connectors and optionally attaches a priced AWS SKU
(e.g., a NAT Gateway) to a connector, whose cost rolls into the calculated total.

**Independent Test**: Create an Architecture with two Collections, add a Data Connector between
them, attach an AWS SKU to it with pricing inputs, and verify the connector's cost is included in
the calculated total (`quickstart.md` "Validate: connectors add to the total").

### Tests for User Story 2 ⚠️

- [x] T041 [P] [US2] Contract test for `POST /architectures/{id}/connectors`, including the
      `400` self-connect rejection (FR-008), in `backend/tests/contract/test_connectors.py`
- [x] T042 [P] [US2] Contract test for `POST /connectors/{id}/sku-selection` (FR-009) in
      `backend/tests/contract/test_connector_sku_selection.py`
- [x] T043 [US2] Integration test for the connectors-add-to-the-total flow (per `quickstart.md`
      section 2) in `backend/tests/integration/test_us2_connectors.py`

### Implementation for User Story 2

- [x] T044 [US2] Implement `POST /architectures/{id}/connectors`, validating
      `from_collection_id != to_collection_id` and that both Collections belong to the
      Architecture (FR-008), in `backend/src/api/connectors.py` (depends on T030)
- [x] T045 [US2] Implement `POST /connectors/{id}/sku-selection` (FR-009) in
      `backend/src/api/connectors.py` (depends on T044)
- [x] T046 [US2] Extend the price calculation service to include connector-attached SKU line
      items in the total (FR-010) in `backend/src/services/price_calculation.py` (depends on
      T033, T045)
- [x] T047 [US2] Register the US2 routers in `backend/src/main.py` (depends on T044, T045)
- [x] T048 [US2] Add the React Flow canvas rendering Collections as nodes to the Create
      Architecture page in `frontend/src/pages/CreateArchitecturePage.tsx` (depends on T039)
- [x] T049 [US2] Implement Data Connector edge creation and the attached-SKU side panel (reusing
      PricingInputsForm) in `frontend/src/components/DataConnectorPanel.tsx` (depends on T048,
      T038)
- [x] T050 [US2] Run the `quickstart.md` "connectors add to the total" validation script
      (depends on T047, T049)

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 - Manage Architectures over time (Priority: P3)

**Goal**: A user lists their Architectures, and can soft-delete Architectures, Collections, and
Data Connectors with confirmation.

**Independent Test**: Create two Architectures, confirm both appear in the list, soft-delete one
after confirming the prompt, and verify it disappears from the list while its data is retained
(`quickstart.md` "Validate: soft delete").

### Tests for User Story 3 ⚠️

- [x] T051 [P] [US3] Contract test for `DELETE /architectures/{id}` — soft delete and idempotent
      re-delete (FR-014) — in `backend/tests/contract/test_architecture_delete.py`
- [x] T052 [P] [US3] Contract test for `DELETE /collections/{id}` cascading to soft-delete its
      Data Connectors (FR-015) in `backend/tests/contract/test_collection_delete_cascade.py`
- [x] T053 [US3] Integration test for the lifecycle flow (per `quickstart.md` section 3) in
      `backend/tests/integration/test_us3_lifecycle.py`

### Implementation for User Story 3

- [x] T054 [US3] Implement `DELETE /architectures/{id}` soft delete (FR-014) in
      `backend/src/api/architectures.py` (depends on T029)
- [x] T055 [US3] Implement `DELETE /collections/{id}` soft delete with the Data Connector
      cascade (FR-015) in `backend/src/services/architecture_service.py` and
      `backend/src/api/collections.py` (depends on T030, T044)
- [x] T056 [US3] Implement `DELETE /connectors/{id}` soft delete (FR-015) in
      `backend/src/api/connectors.py` (depends on T044)
- [x] T057 [US3] Add the unconnected-VPCs warning (FR-017) to the price calculation service and
      `/calculate` response in `backend/src/services/price_calculation.py` (depends on T046)
- [x] T058 [US3] Register the remaining US3 routes in `backend/src/main.py` (depends on T054,
      T055, T056)
- [x] T059 [US3] Add a ConfirmDeleteDialog component and wire delete actions into the Landing
      and Create Architecture pages in `frontend/src/components/ConfirmDeleteDialog.tsx`
      (depends on T036, T039, T049)
- [x] T060 [US3] Display calculation warnings (unconnected VPCs) in the Create Architecture
      page's results panel in `frontend/src/pages/CreateArchitecturePage.tsx` (depends on T057,
      T039)
- [x] T061 [US3] Run the `quickstart.md` "Validate: soft delete" script (depends on T058, T059)

**Checkpoint**: All three user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T062 [P] Add structured request/error logging in `backend/src/main.py`
- [x] T063 [P] Add a frontend error boundary with a distinct UI state for `503`
      pricing-data-source-outage responses (FR-018), separate from an empty-results state, in
      `frontend/src/components/ErrorBoundary.tsx`
- [x] T064 [P] Write setup instructions in `backend/README.md` and `frontend/README.md`
      referencing `quickstart.md`
- [x] T065 [P] Add unit tests for the data-model validation rules (SKU Selection's
      exactly-one-parent constraint, Data Connector's self-connect constraint) in
      `backend/tests/unit/test_validation_rules.py`
- [x] T066 [P] Add a CI/build step that regenerates the frontend's OpenAPI-derived types
      (reusing T018's generation script) and fails the build if the regenerated output differs
      from what's checked in — e.g. `openapi-typescript` then `git diff --exit-code`, or an
      equivalent `tsc --noEmit` gate — enforcing Constitution Principle IV (contract drift MUST
      fail a build, never surface as a runtime bug) in `frontend/package.json` and the CI
      workflow config (depends on T018)
- [x] T067 Run the full `quickstart.md` validation end-to-end (all three user stories plus the
      frontend smoke check) as the final regression pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational; its implementation tasks build on US1's
  Collection/API/UI work (T030, T038, T039) but US1 itself needs no changes to support it
- **User Story 3 (Phase 5)**: Depends on Foundational; its implementation tasks build on US1's
  Architecture/Collection endpoints (T029, T030) and US2's connector endpoint (T044), but neither
  US1 nor US2 needs changes to support it
- **Polish (Phase 6)**: Depends on all three user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: No dependency on other stories — the MVP
- **User Story 2 (P2)**: Independently testable on its own terms, but its tasks are additive on
  top of US1's Collection and page-shell code rather than duplicating it
- **User Story 3 (P3)**: Same relationship — additive on top of US1/US2's endpoints, not a
  duplicate implementation

### Within Each User Story

- Contract/unit tests are written first and must fail before implementation (Principle V)
- Models/schemas (Foundational) before services; services before endpoints; endpoints before
  frontend wiring; router registration after the endpoints it registers

### Parallel Opportunities

- T003, T004, T005, T006 (Setup) can run in parallel
- T011, T012, T013 (Foundational) can run in parallel once T009/T006 are done; T014 and T015 can
  then run in parallel once T012/T013 are done; T018 and T019 can run in parallel with the
  backend Foundational tasks
- All Phase 3 (US1) contract/unit tests (T020–T026) can run in parallel with each other
- T036, T037, T038 (US1 frontend components) can run in parallel with each other and with the
  US1 backend tasks
- T041, T042 (US2 tests) can run in parallel; T051, T052 (US3 tests) can run in parallel
- T062–T066 (Polish) can all run in parallel; T067 (final regression) depends on all of them

---

## Parallel Example: User Story 1

```bash
# Launch all US1 contract/unit tests together:
Task: "Contract test for GET /providers in backend/tests/contract/test_providers.py"
Task: "Contract test for POST/GET /architectures in backend/tests/contract/test_architectures.py"
Task: "Contract test for POST /architectures/{id}/collections in backend/tests/contract/test_collections.py"
Task: "Contract test for GET /catalog/skus in backend/tests/contract/test_catalog.py"
Task: "Contract test for POST /collections/{id}/sku-selections in backend/tests/contract/test_sku_selections.py"
Task: "Contract test for POST /architectures/{id}/calculate in backend/tests/contract/test_calculate.py"
Task: "Unit test for price calculation in backend/tests/unit/test_price_calculation.py"

# Launch the US1 frontend components together:
Task: "Build LandingPage in frontend/src/pages/LandingPage.tsx"
Task: "Build CatalogSearchPanel in frontend/src/components/CatalogSearchPanel.tsx"
Task: "Build PricingInputsForm in frontend/src/components/PricingInputsForm.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run `quickstart.md` section 1 independently
5. Demo if ready — this alone proves the core "assemble AWS resources → real price" value

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. User Story 1 → validate independently → MVP demo
3. User Story 2 → validate independently → demo (multi-Collection + connector pricing)
4. User Story 3 → validate independently → demo (lifecycle management)
5. Polish → final regression pass against all three stories

---

## Notes

- [P] tasks touch different files with no unmet dependency
- [Story] labels map each task to its user story for traceability back to `spec.md`
- Constitution Principle V requires tests-first for pricing calculation, DuckDB queries, and
  Postgres logic; frontend presentational components (pages/, components/) are implemented
  tests-after, consistent with the plan.md Constitution Check
- Commit after each task or logical group; verify each story's tests fail before implementing
  against them
- Avoid: vague tasks, two tasks editing the same file marked `[P]`, cross-story edits that would
  break a story's independent testability

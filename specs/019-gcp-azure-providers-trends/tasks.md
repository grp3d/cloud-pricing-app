# Tasks: GCP and Azure Providers, Trends Page, Saved Preferences and Diagram Arrows

**Input**: Design documents from `specs/019-gcp-azure-providers-trends/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: Included. Constitution Principle V requires test-first for provider retrieval, tier pricing, the change-log builder and trend counts, preferences and connector branch rules (plan, Constitution Check). Write each test task first and confirm it fails before the matching implementation task.

**Organization**: Tasks are grouped by user story. The order follows plan.md "Delivery Phases": the preferences core (US4) comes before Trends because Trends selections persist through it, and branching connectors come last so they can be cut from the release on their own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: The user story the task belongs to (US1 to US5)
- Paths: `backend/src/`, `backend/tests/`, `frontend/src/`, `frontend/tests/` (web app, plan.md "Project Structure")

## Conventions for every task

- Backend commands run from `backend/` with `uv run` (for example `uv run pytest`, `uv run ruff check .`). Frontend commands run from `frontend/` (`npm test`, `npm run build`, `npm run check-api-types`).
- A missing `provider` always means `aws` (contracts "Compatibility rule").
- Prices are never estimated, converted or shown as 0 when missing (FR-007, Principle I).
- Whenever a task changes a Pydantic schema used by the API, run `npm run generate-api-types` in `frontend/` and commit the regenerated `frontend/src/api/generated/schema.d.ts`.
- The local pipeline output at `/Users/Shared/agent-workspace/projects/cloud-pricing/_DATA-PIPELINE` (`aws/`, `azure/`, `gcp/`) is the source for fixture rows and manual checks. Tests never read it directly.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies, settings and test fixtures that later phases need.

- [X] T001 Add Recharts to the frontend, pinned to an exact released version (no `^` or `~`), in `frontend/package.json` and `frontend/package-lock.json` (`npm install --save-exact recharts@<version>`); confirm `npm run build` still passes (research R14)
- [X] T002 [P] Add the settings `SNAPSHOT_STALE_DAYS` (int, default 14) and `PRICING_HISTORY_DIR` (path, default `~/.cloud-pricing/history`, not counted in `PRICING_CACHE_MAX_BYTES`) to `backend/src/config.py` and `backend/.env.example`, with tests of the defaults and overrides in `backend/tests/unit/test_settings.py` (contracts §1)
- [X] T003 [P] Update the vendored pipeline contracts to manifest and storage-layout 1.1 in `backend/tests/fixtures/contracts/` (`manifest.schema.json`, `latest.schema.json`, `storage-layout.md`) from `../cloud-pricing-data-retrieval/specs/004-add-azure-gcp-pricing/contracts/`, and record the source commit in `backend/tests/fixtures/contracts/SOURCE.md` (research R1)
- [X] T004 [P] Build a small Azure fixture root in `backend/tests/fixtures/pricing_parquet/azure/` (manifest 1.1 plus `price_item` and `price_item_savings_plan` Parquet for `eastus` and `global`), using `backend/tests/helpers/parquet_tree.py` and rows copied from the local 2026-11-02 Azure snapshot. Include: D4s v5 Linux and Windows meters (Consumption, Reservation 1 Year and 3 Years, savings plan 1 and 3 years); a P10 LRS managed disk; internet egress with its free first 100 GB tier and paid tiers; a global-only support item; one storage meter listed under two meter names with the same tier start and price; one `north-america` geography row. Document every row and its expected price in `backend/tests/fixtures/pricing_parquet/azure/README.md`
- [X] T005 [P] Build a small GCP fixture root in `backend/tests/fixtures/pricing_parquet/gcp/` (manifest 1.1 plus `service`, `sku`, `sku_price`, `sku_price_tier` for `us-east1` and `global`) from the local 2026-11-02 GCP snapshot. Include: N2 core and RAM SKUs with Default and CUD 1-year and 3-year prices; a pd-balanced disk; Standard storage; internet egress with tiers; one multi-regional SKU; one global licensing SKU. Document rows and expected prices in `backend/tests/fixtures/pricing_parquet/gcp/README.md`
- [X] T006 [P] Add tiered AWS rows to the AWS fixture in `backend/tests/fixtures/pricing_parquet/aws/` for one `AWSDataTransfer` internet egress SKU in `us-west-2` (tiers 0–10240 at 0.09, 10240–51200 at 0.085, 51200–153600 at 0.07, 153600–Inf at 0.05, copied from the local 2026-09-21 snapshot), and list them in `backend/tests/fixtures/manifests/README.md` or the AWS fixture README
- [X] T007 [P] Build the multi-week Trends fixture in `backend/tests/fixtures/trends/` (one provider root with 5 weekly AWS snapshots and one missing week), with known cases: SKUs that rise, fall, rise then fall back, are added, are removed, have a zero or missing price in one week, and a tiered SKU whose first tier is free. Add a second revision of one week. Write `backend/tests/fixtures/trends/README.md` with the expected counts per week and DuckDB queries that reproduce them (SC-005, SC-004a)
- [X] T008 Measure the on-disk size of one active snapshot per provider in the local pipeline root (sum of the Parquet files the app reads for all regions), record the numbers in research.md R2, and raise `PRICING_CACHE_MAX_BYTES` in `backend/src/config.py` (and the instance disk in `infra/` if needed) only if three active snapshots don't fit in 1 GiB (research R2)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Per-provider snapshots, the provider adapter layer, the shared tier function (including the AWS tier fix) and the single migration. Every user story depends on this phase.

**⚠️ CRITICAL**: No user story work starts until this phase is done.

### Tests for the foundation (write first, confirm they fail)

- [X] T009 [P] Extend `backend/tests/unit/test_manifest.py`: per-provider table registry (aws 5 tables, azure 2, gcp 4); an unknown table or `schema_version` for a provider is rejected; the file-path check accepts `global`, `north-america` and `northamerica-northeast1`; manifest 1.1 fields (`catalog`, `excluded_price_types`, `run.region_results`) are accepted and ignored (research R1)
- [X] T010 [P] Extend `backend/tests/unit/test_snapshot_monitor.py`: one `MonitorState` per provider; a `failed` GCP manifest leaves AWS and Azure active and untouched; `get_active_snapshot("azure")` returns the Azure snapshot; a provider with no manifest has status `none`; an active snapshot older than `SNAPSHOT_STALE_DAYS` has status `stale` and stays active (FR-001, FR-002, contracts §1)
- [X] T011 [P] Extend `backend/tests/unit/test_cache_cleanup.py`: each provider's active snapshot is protected; `pricing_cache_keep` applies per provider; the size budget is shared across providers (research R2)
- [X] T012 [P] Write `backend/tests/unit/test_tiers.py` for the shared graduated-tier function (research R8, FR-008):
  - tiers 0–10, 10–20, 20–1000 at rates r1, r2, r3 with quantity 40 → 10×r1 + 10×r2 + 20×r3, with three parts returned;
  - a single-tier price gives one part and the same cost as today;
  - a free first tier (rate 0) is applied, not skipped;
  - a quantity past a bounded top tier prices the excess at the tier with the highest upper bound;
  - a null rate in a tier the quantity reaches → unpriceable ("not published"); a null rate only in a tier it doesn't reach → priced;
  - duplicate rows with the same start and rate collapse to one tier; same start with different rates → unpriceable;
  - monthly normalization (research R8 table), each scaled to 1 day, 1 month and 1 year: a no-period unit tiers on quantity × 31 and scales by days ÷ 31; a fixed-period unit (GB-Mo) tiers on the quantity as entered and scales by days ÷ its period; an unrecognized unit is unpriceable; a single-tier price gives today's result in both classes.
- [X] T013 [P] Add AWS tier cases to `backend/tests/unit/test_price_calculation.py` using the T006 fixture: 20,480 GB of internet egress per month in `us-west-2` costs 10,240 × 0.09 + 10,240 × 0.085, and the line item's `tiers` holds both parts; a non-tiered AWS SKU's cost is unchanged
- [X] T014 [P] Write `backend/tests/integration/test_migration_0006.py`: `alembic upgrade head` from 0005 then `downgrade` to 0005 succeeds on real Postgres (existing `backend/tests/helpers/pg.py`); existing rows keep their values; new columns have their defaults (`arrow_style = 'none'`, `arrow_reversed = false`, `provider_options` null); the widened `pricing_term` CHECK accepts `savings_plan_1yr` and `commitment_3yr` (data-model §1 to §5)
- [X] T015 [P] Extend `backend/tests/contract/test_providers.py`: `GET /providers` returns `status`, `reason`, `snapshot_date`, `snapshot_revision` per provider; `active` is true only with a usable snapshot; Azure with no data returns `status: "none"`, `reason: "no snapshot available"` (contracts §1)

### Implementation for the foundation

- [X] T016 Replace the single `TABLES` tuple with a per-provider table registry and widen the location path check in `backend/src/pricing_data/manifest.py` (makes T009 pass)
- [X] T017 Make `backend/src/pricing_data/snapshot.py` provider-aware: table lookup by provider, `locations()` from the manifest's `regions.succeeded` instead of `common_regions()`, and a helper that returns a location's files plus `global`'s (research R1, R5)
- [X] T018 Generalize `backend/src/pricing_data/active_snapshot.py` from `PROVIDER = "aws"` to one `MonitorState` per provider in a dict keyed by provider code: `get_active_snapshot(provider: str = "aws")`, `pricing_status(provider)`, a `provider_status(provider)` returning `current | partial | failed | stale | none` plus reason, and `run_check` visiting aws, azure and gcp in turn with failures recorded per provider. Update `_snapshot_monitor` in `backend/src/main.py`. Keep `/health` readiness tied to AWS as today, so the feature 018 uptime alert doesn't change, and add per-provider detail to its body (makes T010 pass)
- [X] T019 Make clean-up provider-aware in `backend/src/pricing_data/snapshot_cache.py` and `_cleanup_cache` in `backend/src/pricing_data/active_snapshot.py` (makes T011 pass)
- [X] T020 [P] Create `backend/src/pricing_data/providers/__init__.py` and `backend/src/pricing_data/providers/base.py`: the `PricingProvider` protocol (`locations`, `search`, `describe`, `exists`, `price`, `service_key`, `comparable_prices`) and the dataclasses `CatalogItem`, `PriceQuote`, `Tier` (`start_quantity`, `rate`), `TierPart` (`from_quantity`, `to_quantity`, `rate`, `quantity`, `cost`) (research R3)
- [X] T021 [P] Implement `apply_tiers(tiers, monthly_quantity)` and tier normalization (sorting, duplicate collapse, bounded-top handling, null handling) in `backend/src/pricing_data/providers/tiers.py`, using `Decimal` throughout (makes T012 pass)
- [X] T022 Add `lookup_price_tiers(...)` to `backend/src/pricing_data/pricing.py`: returns every on-demand `price_fact` row for the SKU, term and options as `Tier`s ordered by numeric `begin_range`, with `Inf` as an open top. Leave `lookup_price` and `lookup_reserved_price` in place for reserved terms
- [X] T023 Implement `backend/src/pricing_data/providers/aws.py` wrapping `search_catalog`, `resolve_units`, `lookup_price_tiers`, `lookup_reserved_price`, `resolve_product_details` and `find_existing_skus` without changing their behavior, and `backend/src/pricing_data/providers/registry.py` with `get_provider(code)` (unknown code → `ValueError`) (research R3)
- [X] T024 Route pricing in `backend/src/services/price_calculation.py` through `get_provider(architecture.provider)`: on-demand lines get `tiers` from the adapter, are converted to a monthly quantity with the existing `_DURATION_DAYS` 31-day month, priced with `apply_tiers`, then scaled to the requested duration the same way as today. Reserved paths are unchanged (makes T013 pass)
- [X] T025 Run `uv run pytest`. Update only the existing AWS tests whose expected totals came from the old single-tier lookup, and list each changed test with its old and new value in a "Tier fix: updated tests" note at the end of this file (research R3). Every other test must pass unchanged
- [X] T026 Write migration `backend/src/db/migrations/versions/0006_providers_trends_preferences.py` and update `backend/src/models/orm.py`: `user_preferences`; `service_category_rules` (unique `provider, match_field, match_value`; CHECK on `category`); `sku_selections.pricing_term` CHECK widened and `provider_options` JSONB nullable; `collections.region` widened to varchar(64); `data_connectors.arrow_style` (CHECK, default `none`) and `arrow_reversed` (default false); `connector_branches` (FK cascade on connector). Include a working downgrade (makes T014 pass; data-model §1 to §5)
- [X] T027 Update `backend/src/models/schemas.py`: widen the `PricingTerm` enum; add the `ProviderOptions` discriminated union (`GcpMachineOptions`, `AzureVmOptions`, each with `version: 1`); add `price_type_label`, `tiers: list[TierPartOut] | None` and `components` to `PriceLineItem`; add `status`, `reason`, `snapshot_date`, `snapshot_revision` to the provider output model (contracts §1, §4, §5)
- [X] T028 Return per-provider status from `backend/src/api/providers.py` using `provider_status` (makes T015 pass)
- [X] T029 Regenerate `frontend/src/api/generated/schema.d.ts` (`npm run generate-api-types`) and fix any TypeScript errors in `frontend/src/` caused by the widened types; `npm run check-api-types && npm run build && npm test` pass
- [X] T030 **Gate**: `uv run pytest` and `uv run ruff check .` pass in `backend/`, with only the T025-listed tests changed; frontend checks pass

**Checkpoint**: The app behaves as before for AWS (apart from correct tier pricing), and knows the status of all three providers.

---

## Phase 3: User Story 1 - Build and price a GCP or Azure architecture (Priority: P1) 🎯 MVP

**Goal**: GCP and Azure are enabled in the workspace with search, Service Editor, pricing, Admin status and export/import, all through the shared request shapes.

**Independent Test**: Select Azure, create an architecture in `eastus`, add a Linux D4s v5, a P10 LRS disk and 500 GB of egress, and calculate; repeat for GCP in `us-east1` with an n2-standard-4. Every price matches the fixture README's expected price (quickstart B).

### Tests for User Story 1 (write first, confirm they fail)

- [X] T031 [P] [US1] Write `backend/tests/unit/test_provider_units.py`: Azure `unit_of_measure` forms (`1 Hour`, `1 GB/Month`, `10K`, `1/Month`, `100 Hours`) parse to (multiplier, base) and classify like `duration.py`; an unknown form is `unrecognized`; GCP `unit` with `unit_quantity` gives price ÷ `unit_quantity` (research R7)
- [X] T032 [P] [US1] Write `backend/tests/unit/test_provider_azure.py` against the T004 fixture: `locations` excludes `global` and `north-america`; `search` returns region plus global items, global items labeled `location_scope: "global"`; `kind` filters match the reference lookups; `describe` and `exists` work on `<sku_id>/<meter_id>`; published price types per item; `azure_vm` picks the Linux or Windows meter; a reservation prices as an upfront fee with no recurring rate; a savings plan prices from `price_item_savings_plan`; 500 GB egress → first 100 GB at $0 and 400 GB at the next tier; the duplicate-name meter collapses to one tier; `purchase_option` other than `not_applicable` is rejected (research R4 to R8)
- [X] T033 [P] [US1] Write `backend/tests/unit/test_provider_gcp.py` against the T005 fixture: `gcp_machine` with 4 vCPUs and 16 GiB costs 4 × core rate + 16 × RAM rate, with two `components`; CUD 1-year and 3-year prices; a multi-regional SKU appears once in `us-east1`; a global licensing SKU is found from `us-east1`; egress tiers by `start_amount`; null `list_price` → unpriceable (research R4 to R8)
- [X] T034 [P] [US1] Extend `backend/tests/contract/test_catalog.py` and `backend/tests/unit/test_regions.py`: `GET /catalog/skus?provider=azure|gcp` with `q`, `kind` and `product_family`; the new optional `CatalogSKUOut` fields; `from_region_code` with a non-AWS provider → 422; `GET /regions?provider=gcp` returns `display_name` and no `global` (contracts §2, §3)
- [X] T035 [P] [US1] Extend `backend/tests/contract/test_sku_selections.py` and `backend/tests/contract/test_collections.py`: the widened `pricing_term`; valid and invalid `provider_options` (wrong provider → 422, `vcpus <= 0` → 422); a price type the item doesn't publish → 422 with a field message; a collection region not in the provider's regions → 422; a 23-character GCP region is accepted (contracts §4, data-model §3, §4)
- [X] T036 [P] [US1] Extend `backend/tests/contract/test_calculate.py`: an Azure and a GCP architecture calculate from their own provider's snapshot and report its `snapshot_date` and `snapshot_revision`; `tiers`, `components` and `price_type_label` are present; an unpublished price is an `UnpriceableItem` "not published" (contracts §5, FR-003, FR-007)
- [X] T037 [P] [US1] Write `backend/tests/integration/test_us1_azure_gcp_assemble_and_price.py`: build the Independent Test architectures through the API for both providers and compare every line with the fixture READMEs (SC-002); and `backend/tests/integration/test_provider_isolation.py`: with GCP's newest manifest `failed`, AWS and Azure create, search and calculate normally and GCP returns 503 with its reason (SC-008)
- [X] T038 [P] [US1] Extend `backend/tests/unit/test_architecture_transfer.py` and `backend/tests/contract/test_admin_architecture_import.py`: an Azure architecture with `provider_options` exports and imports unchanged with the same total; an older export without the new fields still imports; import validation uses the adapter's `exists` (research R15)
- [X] T039 [P] [US1] Extend `backend/tests/contract/test_admin_system_info.py`: `GET /admin/system` returns `providers.{aws,azure,gcp}` each with `active_snapshot`, `latest_run`, `rejected`, `issues` (contracts §9; the `history` block is added in US2)

### Implementation for User Story 1

- [X] T040 [P] [US1] Implement the Azure and GCP unit tables in `backend/src/pricing_data/providers/units.py` (makes T031 pass)
- [X] T041 [US1] Implement `backend/src/pricing_data/providers/azure.py` (all protocol methods except `comparable_prices` and `service_key`, which come in US2), registered in `registry.py`, using DuckDB over the location plus `global` files and the pipeline 004 contract's text filters (makes T032 pass)
- [X] T042 [US1] Implement `backend/src/pricing_data/providers/gcp.py` the same way, including the `gcp_machine` core plus RAM calculation with `components` (makes T033 pass)
- [X] T043 [US1] Add the `provider` parameter (default `aws`) and `display_name` to `backend/src/api/regions.py`, and `provider`, `kind` and `product_family` to `backend/src/api/catalog.py`, both dispatching through `get_provider`; return 422 for AWS-only parameters on other providers (makes T034 pass)
- [X] T044 [US1] Validate per provider in `backend/src/services/architecture_service.py` and `backend/src/api/sku_selections.py` / `backend/src/api/collections.py`: price type supported and published, `provider_options.kind` matching the architecture's provider, `purchase_option = not_applicable` for Azure and GCP, collection region in the provider's `locations` (makes T035 pass)
- [X] T045 [US1] Use the architecture's provider snapshot in `backend/src/api/calculate.py` and `backend/src/services/price_calculation.py`, filling `price_type_label`, `tiers` and `components`; connector data transfer uses the connector's "from" region for every provider (makes T036 and T037 pass)
- [X] T046 [US1] Carry `provider_options` through `backend/src/services/architecture_transfer.py` and `backend/src/services/architecture_import.py`, with import validation through the adapter's `exists` (makes T038 pass)
- [X] T047 [US1] Return per-provider snapshot, latest run, rejection and issues from `backend/src/api/admin_system.py` (makes T039 pass)
- [X] T048 [US1] Regenerate the API types and add the `provider` argument to the regions and catalog calls in `frontend/src/api/client.ts`
- [X] T049 [P] [US1] Enable provider buttons by `active` and show the snapshot date, or the status reason when disabled, on hover in `frontend/src/components/workspace/ProviderArchitecturePanel.tsx` (FR-001)
- [X] T050 [US1] Make the regions, catalog and calculate queries in `frontend/src/pages/WorkspacePage.tsx` use `selectedProvider`, with query keys that include the provider
- [X] T051 [P] [US1] Show per-provider regions with `display_name` in `frontend/src/components/workspace/RegionSelectDialog.tsx`
- [X] T052 [P] [US1] Add the `kind` filter, the provider's grouping filter (`product_family`) and the "global" label to `frontend/src/components/CatalogSearchPanel.tsx`
- [X] T053 [US1] Create per-provider editor field components in `frontend/src/components/providers/AwsFields.tsx`, `AzureFields.tsx` (OS, reservation and savings plan terms) and `GcpFields.tsx` (vCPUs, memory, commitment terms), and use them from `frontend/src/components/workspace/ServiceConfigPanel.tsx` and `frontend/src/components/PricingInputsForm.tsx` so only the item's published price types are offered and AWS-only fields are hidden for other providers (FR-005, FR-005a)
- [X] T054 [P] [US1] Make connector data transfer selection provider-aware in `frontend/src/components/DataConnectorPanel.tsx` and `frontend/src/pages/connectorSelection.ts`, keeping `frontend/src/lib/awsDataTransfer.ts` for AWS only
- [X] T055 [P] [US1] Show the price type label, the tier breakdown and GCP machine components per line in `frontend/src/components/workspace/PricingPanel.tsx`
- [X] T056 [P] [US1] Show snapshot status per provider in `frontend/src/components/admin/SystemInformationSection.tsx` (FR-009)
- [X] T057 [P] [US1] Add frontend tests: provider fields and hidden AWS fields in `frontend/tests/unit/ServiceConfigPanel.test.tsx`, tier breakdown and components in `frontend/tests/unit/PricingPanel.test.tsx`, and enabled/disabled provider buttons in a new `frontend/tests/unit/ProviderArchitecturePanel.test.tsx`
- [X] T058 [US1] Run quickstart section B against the local pipeline root and record the results in a new `specs/019-gcp-azure-providers-trends/checklists/validation.md` (used by every later quickstart run)

**Checkpoint**: GCP and Azure can be used end to end. This is the MVP.

---

## Phase 4: User Story 4 (core) - Preferences on the server (Priority: P3, needed before Trends)

**Goal**: A typed, per-user preferences record on the server and a frontend store that loads, saves and retries it. Trends selections (US2, US3) persist through it.

**Independent Test**: `PATCH /me/preferences` with a `trends.charts` section, then `GET` from a second session as the same user returns it; a guest's preferences are separate (quickstart E1–E2, at API level).

### Tests for User Story 4 core (write first, confirm they fail)

- [X] T059 [P] [US4] Write `backend/tests/contract/test_preferences.py`: `GET /me/preferences` with no row returns `{schema_version: 1, data: {migrated_from_browser: false}}`; PATCH replaces only the sections sent (`workspace`, `trends.charts`, `trends.movers`) and returns the full record; unknown keys or invalid values → 422; two users and a guest are isolated; deleting a guest deletes its row (contracts §7, data-model §1)
- [X] T060 [P] [US4] Write `frontend/tests/unit/preferences.test.ts`: the store loads once, applies section patches optimistically, queues a failed save and retries with backoff, never throws to the caller, and drops queued duplicates for the same section (FR-025)

### Implementation for User Story 4 core

- [X] T061 [US4] Add the `Preferences` model (unknown keys rejected) and its sections to `backend/src/models/schemas.py`, mirroring data-model §1 (charts section: `providers`, `category`; no `metric`)
- [X] T062 [US4] Implement `backend/src/services/preferences_service.py` (read with defaults, section-replace write, `updated_at`) and `backend/src/api/preferences.py` (`GET` and `PATCH /me/preferences`, existing identity dependency from `backend/src/api/deps.py`), and register the router in `backend/src/main.py` (makes T059 pass)
- [X] T063 [US4] Regenerate API types and implement `frontend/src/lib/preferences.ts` (load, `patchSection`, in-memory retry queue with backoff, a React hook `usePreferences`) plus client calls in `frontend/src/api/client.ts` (makes T060 pass)

**Checkpoint**: Preferences can be stored and read; nothing in the UI uses them yet.

---

## Phase 5: User Story 2 - See how prices are moving on the Trends page (Priority: P2)

**Goal**: The Trends tab opens a page whose left side shows the **SKUs Changed** chart: per week and provider, the number of SKUs whose price went up and down, with provider, region and category selectors and Reset.

**Independent Test**: With the T007 fixture (or 3+ local weekly snapshots), select one provider with two regions: the chart shows one up/down pair whose counts match the fixture README (quickstart C, SC-005).

### Tests for User Story 2 (write first, confirm they fail)

- [X] T064 [P] [US2] Write `backend/tests/unit/test_categories.py`: rules match per provider on the documented fields; the highest priority wins; no match is uncategorized; the seed loads idempotently (research R9, data-model §2)
- [X] T065 [P] [US2] Write `backend/tests/unit/test_comparable_prices.py`: each adapter's `comparable_prices` returns one row per (location, item) with the on-demand price of the first non-zero tier, and `service_key` per item; null and zero prices are kept so the builder can count them as excluded (research R10)
- [X] T066 [P] [US2] Write `backend/tests/unit/test_history_builder.py` against the T007 fixture: per week pair, `changes` holds exactly the changed items; `counts` holds compared, unchanged, increased, decreased, added, removed and excluded per (location, service key); added and removed SKUs are never changes; a missing or zero price at either end is excluded; a missing week is a gap and the pair spans it; several snapshots in one ISO week use only the latest; a snapshot already processed is never fetched again; a new revision rebuilds the pairs on both sides; a builder version change rebuilds all; `pair.json` and `state.json` record provenance (data-model §7)
- [X] T067 [P] [US2] Write `backend/tests/unit/test_trends_metrics.py`: SKUs Changed per week sums `counts` over selected locations and the category's service keys; percentages are of compared; a week with nothing compared is null ("no data"), a week with no changes is 0 up and 0 down; empty regions mean all regions; a multi-regional SKU counts once per selected region; a global-only SKU counts once per provider (location `global`) when two regions are selected; uncategorized services count only under "all categories"; weeks are limited to 52 (FR-012 to FR-015a)
- [X] T068 [P] [US2] Write `backend/tests/contract/test_trends.py` for `GET /trends/series`: query `category`, repeated `select=<provider>:<regions>`, `weeks`; response shape with `metric: "skus_changed"`, per-series `status` (`ok`, `building` with `weeks_built` and `weeks_total` and the weeks built so far, `not_enough_history`, `provider_unavailable`) and points with `increased`, `decreased`, `increased_pct`, `decreased_pct`, `compared`, `excluded`, `gap`, snapshot provenance (contracts §8)
- [X] T069 [P] [US2] Write `backend/tests/integration/test_history_backfill.py`: on start with an empty history directory, the backfill walks manifests oldest to newest one snapshot at a time, deletes each fetched snapshot after use, and leaves `state.json` with weeks built and gaps; an interrupted backfill resumes; a restart after it finishes fetches nothing; with an S3-style source only `comparable_prices`' tables are fetched; a corrupt file triggers a rebuild of that pair (research R10)
- [X] T070 [P] [US2] Extend `backend/tests/contract/test_admin_system_info.py`: each provider has a `history` block (`weeks_built`, `gaps`, `backfill`, `last_error`) (contracts §9)

### Implementation for User Story 2

- [X] T071 [P] [US2] Write the category seed `backend/src/db/seed/service_categories.json` (AWS `service_code` / `product_family`, Azure `service_family` / `service_name`, GCP taxonomy levels 1 and 2, per research R9) and load it idempotently from a new migration `backend/src/db/migrations/versions/0007_service_category_seed.py` (down-revision 0006, which T026 wrote and is not changed) the same way `0005_standard_architectures.py` loads its seed
- [X] T072 [US2] Implement `backend/src/services/categories.py`: load rules, map service keys to categories, and list the service keys for a category (makes T064 pass)
- [X] T073 [US2] Implement `service_key` and `comparable_prices` in `backend/src/pricing_data/providers/aws.py`, `azure.py` and `gcp.py` (makes T065 pass)
- [X] T074 [US2] Implement `backend/src/pricing_data/history/store.py` (layout under `PRICING_HISTORY_DIR/<provider>/`, atomic writes, `state.json` including the snapshots already processed) and `backend/src/pricing_data/history/builder.py` (price list per snapshot, week pairs, revisions, gaps, builder version) (makes T066 pass)
- [X] T075 [US2] Run the builder after a provider's active snapshot switches and start the backfill as a background task on startup in `backend/src/pricing_data/active_snapshot.py` / `backend/src/main.py`, fetching only the tables `comparable_prices` needs from each historical snapshot with the existing verified download (reading in place for `file://`), deleting the copy after use, and keeping DuckDB within `DUCKDB_MEMORY_LIMIT` (makes T069 pass)
- [X] T075a [US2] Measure the AWS backfill against the S3 source (duration, bytes fetched, peak memory) and record the result in research R10 (research R10 alternatives)
- [X] T076 [US2] Implement the SKUs Changed series in `backend/src/pricing_data/history/metrics.py` (makes T067 pass)
- [X] T077 [US2] Implement `GET /trends/series` in `backend/src/api/trends.py` with Pydantic response models in `backend/src/models/schemas.py`, register it in `backend/src/main.py`, and add the `history` block to `backend/src/api/admin_system.py` (makes T068 and T070 pass)
- [X] T078 [US2] Enable the Trends tab in `frontend/src/components/layout/TopTabs.tsx` and add the `/trends` route to `frontend/src/App.tsx` pointing at a new `frontend/src/pages/TrendsPage.tsx` with a left charts section and a right movers section placeholder
- [X] T079 [US2] Load the `dataviz` skill, then build `frontend/src/components/trends/TrendsChartPanel.tsx` with Recharts: one up/down pair per provider, labeled with the provider and its regions; hover shows week, up and down counts, their % of compared, compared and excluded, and the tier note; "no data" and gap points are marked; a "not enough history yet" note per series; a "building history (n of m weeks)" note while a series is `building`; colors from the project's tokens in light and dark (FR-012, FR-013, R14)
- [X] T080 [US2] Build `frontend/src/components/trends/ChartSelectors.tsx` (providers with regions under each, only active providers; category) and wire it to `trends.charts` in `frontend/src/lib/preferences.ts`, with a Reset button restoring all providers, all regions, all categories (FR-011, FR-020, FR-021)
- [X] T081 [P] [US2] Add `frontend/tests/unit/TrendsChartPanel.test.tsx` and `frontend/tests/unit/ChartSelectors.test.tsx`: series per provider, "no data" vs 0, not enough history, Reset saves defaults for the charts section only
- [X] T082 [US2] Measure the Trends signal for Azure and GCP once each has at least 3 weekly snapshots (same query as research R11), and add the result to spec.md Assumptions "Trends signal"; if it is not available yet, note that in this file's final notes

**Checkpoint**: The Trends chart works and persists its selections.

---

## Phase 6: User Story 3 - See the biggest price movers per category (Priority: P2)

**Goal**: The right side of the Trends page lists the 3 largest % increases and decreases for a provider, category, regions and period.

**Independent Test**: Select AWS, Compute, all regions, 13 weeks against the T007 fixture: both lists match the fixture README's expected movers (quickstart D, SC-004a).

### Tests for User Story 3 (write first, confirm they fail)

- [X] T083 [P] [US3] Add movers cases to `backend/tests/unit/test_trends_metrics.py`: start price is before the first change in the window and end price after the last; changed-and-back items are dropped; items removed before the end are dropped; uncategorized services appear only under "all categories"; a global-only SKU is one entry (location `global`) when two regions are selected; ties by absolute price change then name; the same SKU in two regions gives two entries; `weeks_available` when history is shorter than the period; tiered items carry `tier_note` (FR-016 to FR-019)
- [X] T084 [P] [US3] Add `GET /trends/movers` cases to `backend/tests/contract/test_trends.py`: query `provider`, `category`, `regions`, `period_weeks` in {1, 4, 13, 52} (others → 422); prices as published decimal strings; `change_pct` to 2 decimals; `message` when both lists are empty (contracts §8)

### Implementation for User Story 3

- [X] T085 [US3] Implement movers in `backend/src/pricing_data/history/metrics.py` (makes T083 pass)
- [X] T086 [US3] Add `GET /trends/movers` and its response models to `backend/src/api/trends.py` and `backend/src/models/schemas.py` (makes T084 pass)
- [X] T087 [US3] Build `frontend/src/components/trends/MoversPanel.tsx` (provider, category, regions, period selectors; "Largest increases" and "Largest decreases" lists showing service, SKU description, region, start and end price, unit, % change; empty message; "weeks compared" note) and place it on the right of `frontend/src/pages/TrendsPage.tsx`
- [X] T088 [US3] Wire the movers selections to `trends.movers` in `frontend/src/lib/preferences.ts`, with a Reset restoring the first available provider, all categories, all regions and 52 weeks, without touching the charts section (FR-020)
- [X] T089 [P] [US3] Add `frontend/tests/unit/MoversPanel.test.tsx`: list rendering, empty message, Reset independence
- [X] T090 [US3] Check SC-004 against the local pipeline root: time from opening Trends to chart and both lists rendered with the defaults is under 3 seconds; record it in `specs/019-gcp-azure-providers-trends/checklists/validation.md`

**Checkpoint**: The whole Trends page works.

---

## Phase 7: User Story 4 (rest) - Selections and layout follow the user to any device (Priority: P3)

**Goal**: The general workspace settings move from the browser to the server once, and are read from there afterwards.

**Independent Test**: Change a column width in browser A; sign in as the same user in browser B and see the same width; old browser-only values are migrated once (quickstart E).

### Tests for User Story 4 rest (write first, confirm they fail)

- [X] T091 [P] [US4] Add migration and stale-value cases to `frontend/tests/unit/preferences.test.ts`: with `migrated_from_browser: false`, existing `columnWidths` and `columnCollapse` browser values are sent once and the flag is set; with the flag set, browser values are ignored; a stored provider or region that is no longer available is dropped and the cleaned value saved (FR-023, FR-024, data-model §1)
- [X] T092 [P] [US4] Update `frontend/tests/unit/columnCollapse.test.ts` (and add a column widths test if none exists) for the preferences-backed behavior

### Implementation for User Story 4 rest

- [X] T093 [US4] Back `frontend/src/lib/columnWidths.ts` and `frontend/src/lib/columnCollapse.ts` with the `workspace` preferences section, keeping their current exported API; implement the one-time browser migration in `frontend/src/lib/preferences.ts` (makes T091, T092 pass)
- [X] T094 [US4] Save and restore `workspace.last_provider` for `selectedProvider` in `frontend/src/pages/WorkspacePage.tsx`, falling back to `aws` when the stored provider is inactive
- [X] T095 [US4] Run quickstart section E in two browsers and record the results in the validation checklist

**Checkpoint**: All general preferences follow the user; per-architecture settings stay in the browser (FR-023).

---

## Phase 8: User Story 5 - Clearer diagrams with arrows: styles and reverse (Priority: P3)

**Goal**: Connectors get none, one-way and two-way arrow styles and a visual-only reverse, saved and exported.

**Independent Test**: Set a connector to one-way, two-way, then reverse it; markers update, the style survives reload and export/import, and the total is unchanged (quickstart F1, SC-007).

### Tests for User Story 5 arrows (write first, confirm they fail)

- [X] T096 [P] [US5] Extend `backend/tests/contract/test_connectors.py`: create and patch `arrow_style` and `arrow_reversed`; invalid style → 422; a connector without a data transfer selection accepts a style; reversing doesn't change `from`/`to` or the calculated total (FR-026, FR-028 to FR-030)
- [X] T097 [P] [US5] Extend `backend/tests/unit/test_architecture_transfer.py`: arrow fields round-trip through export, import and copy; older files import with `none` / false (research R15)

### Implementation for User Story 5 arrows

- [X] T098 [US5] Add `arrow_style` and `arrow_reversed` to the connector schemas in `backend/src/models/schemas.py`, `backend/src/api/connectors.py` and `backend/src/services/architecture_service.py`, and carry them through `backend/src/services/architecture_transfer.py` and `architecture_import.py` (makes T096, T097 pass)
- [X] T099 [US5] Regenerate API types; add an arrow style picker (2 clicks or fewer) and a Reverse action to `frontend/src/components/DataConnectorPanel.tsx`, and draw the markers with React Flow's built-in arrow markers in `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` (SC-007)
- [X] T100 [P] [US5] Add `frontend/tests/unit/connectorArrows.test.tsx`: style to marker mapping, reverse swaps marker ends only

**Checkpoint**: Arrow styles ship even if branching connectors are cut.

---

## Phase 9: User Story 5 - Branching connectors (Priority: P3, separable)

**Goal**: One-to-many and many-to-one connectors with extra boxes, the lifecycle rules, and data transfer priced once.

**Independent Test**: Make a connector one-to-many, add a third box, calculate (transfer priced once), delete a branch box (connector becomes one-way), reload, export and import (quickstart F2–F4).

**Note**: This phase can move to a later release on its own (spec Assumptions). If cut, leave `connector_branches` in migration 0006 unused and hide `one_to_many` / `many_to_one` in the UI.

**Status: deferred to a later release** (user decision, 2026-11-05). T101 to T108 stay open. `connector_branches` is unused, and the editor offers only None, One-way and Two-way. The API still accepts `one_to_many` and `many_to_one` (drawn like one-way on a two-box connector).

### Tests for User Story 5 branches (write first, confirm they fail)

- [ ] T101 [P] [US5] Write `backend/tests/contract/test_connector_branches.py`: `POST /connectors/{id}/branches` needs a branching style, a collection in the same architecture, not already linked; `DELETE` leaving 2 boxes returns `arrow_style: "one_way"`; changing style away from branching with branches present → 409 with a clear message; `DataConnectorOut.branch_collection_ids` in creation order (contracts §6, data-model §5)
- [ ] T102 [P] [US5] Extend `backend/tests/contract/test_collection_delete_cascade.py`: deleting a branch box removes its branch; deleting the primary `from` or `to` box promotes the oldest branch box; with no branch left, the connector is soft-deleted as today (data-model §5)
- [ ] T103 [P] [US5] Extend `backend/tests/contract/test_calculate.py` and `backend/tests/unit/test_architecture_transfer.py`: a branching connector's data transfer is priced once from the primary `from` region (FR-027a); `branch_refs` round-trip through export and import

### Implementation for User Story 5 branches

- [ ] T104 [US5] Implement branch add, remove, style-change guard and box-deletion lifecycle in `backend/src/services/architecture_service.py` and the routes in `backend/src/api/connectors.py`; add `branch_collection_ids` to the output schema (makes T101, T102 pass)
- [ ] T105 [US5] Carry `branch_refs` through `backend/src/services/architecture_transfer.py` and `architecture_import.py` (makes T103 pass)
- [ ] T106 [US5] Regenerate API types; draw a branching connector as a trunk to a junction point then one edge per branch in `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` and `frontend/src/lib/connectorRouting.ts`; add "Add box" and "Remove box" to `frontend/src/components/DataConnectorPanel.tsx`
- [ ] T107 [P] [US5] Add `frontend/tests/unit/connectorBranches.test.ts` for junction routing and add/remove behavior
- [ ] T108 [US5] Run quickstart section F and record the results in the validation checklist

**Checkpoint**: All user stories are complete.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [X] T109 [P] Update the top-level `README.md` and `backend/README` sections (if present) for three providers, the Trends page, `SNAPSHOT_STALE_DAYS` and `PRICING_HISTORY_DIR`
- [X] T110 [P] Write release notes for v0.0.2 in `specs/019-gcp-azure-providers-trends/release-notes.md`: AWS tier fix and its effect on existing totals, GCP and Azure disabled in production until pipeline 004 Part C (C2 onward) is done (research R16), Trends counts, preferences migration
- [X] T111 Run the full quickstart (sections A to F) and fix anything that fails
- [X] T112 Run `uv run ruff check .` and `uv run ruff format --check .` in `backend/`, and `npm run lint` (if configured), `npm run build`, `npm test` and `npm run check-api-types` in `frontend/`

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: needs Setup (T003, T006 for tests). Blocks every story.
- **US1 (Phase 3)**: needs Foundational. Needs T004, T005.
- **US4 core (Phase 4)**: needs Foundational (migration T026). Independent of US1.
- **US2 (Phase 5)**: needs Foundational and US4 core (selections persist), and T007. Azure and GCP lines need US1's adapters; with US1 not done, US2 works for AWS only.
- **US3 (Phase 6)**: needs US2's history builder (T071 to T075) and the Trends page (T078).
- **US4 rest (Phase 7)**: needs US4 core.
- **US5 arrows (Phase 8)**: needs Foundational (migration) only.
- **US5 branches (Phase 9)**: needs US5 arrows.
- **Polish (Phase 10)**: after the stories that ship.

### Within each story

Tests first (they must fail), then models and schemas, then services and adapters, then API routes, then frontend, then the quickstart run.

### Parallel opportunities

- Setup: T002 to T007 in parallel.
- Foundational tests T009 to T015 in parallel; T020 and T021 in parallel.
- After Foundational: US1, US4 core and US5 arrows can run in parallel (different files, apart from `schemas.py`, where edits are small and should be merged in sequence).
- Within US1: T031 to T039 in parallel; T049, T051, T052, T054, T055, T056 in parallel after T048.
- Within US2: T064 to T070 in parallel.

---

## Parallel Example: User Story 1

```text
# Tests together:
T032 Azure adapter tests in backend/tests/unit/test_provider_azure.py
T033 GCP adapter tests in backend/tests/unit/test_provider_gcp.py
T034 Catalog and regions contract tests
T036 Calculate contract tests

# Frontend pieces together after T048:
T049 ProviderArchitecturePanel.tsx
T051 RegionSelectDialog.tsx
T052 CatalogSearchPanel.tsx
T055 PricingPanel.tsx
```

## Parallel Example: User Story 2

```text
T064 test_categories.py
T066 test_history_builder.py
T067 test_trends_metrics.py
T068 test_trends.py (contract)
```

---

## Implementation Strategy

### MVP first (User Story 1)

1. Phase 1 Setup, then Phase 2 Foundational (includes the AWS tier fix).
2. Phase 3 US1.
3. **Stop and validate** with quickstart B. GCP and Azure stay disabled in production until the pipeline rollout (R16), so the MVP is demoable locally.

### Incremental delivery

1. Foundation → US1 (MVP) → US4 core → US2 → US3 → US4 rest → US5 arrows → US5 branches.
2. Each checkpoint leaves the app releasable. Branching connectors can be dropped without affecting the rest.

---

## Notes

- `[P]` means different files and no dependency on an unfinished task.
- Commit after each task or logical group (`/speckit-git-commit`).
- Tier fix: updated tests (T025, 2026-11-03). **No existing test's expected value changed.** The full backend suite (675 tests) passes with graduated tiers. The only tiered SKU an existing test or seed prices is `Z3FQZG73HYSPVABR` (S3 storage, `us-west-2`) at 2,000 GB in the *Active-Standby Multi-Region Web Application* standard architecture, which stays inside its first tier (0–51,200 GB). Mocks changed, values unchanged:
  - `backend/tests/unit/test_price_calculation.py`: 17 `monkeypatch.setattr(price_calculation, "lookup_price", f)` became `_patch_on_demand_price(monkeypatch, f)`, which serves the same price as one open tier through the AWS adapter; 25 `get_active_snapshot` mocks `lambda: FAKE_SNAPSHOT` became `lambda *_: FAKE_SNAPSHOT`, because the calculation now passes the architecture's provider.
  - `backend/tests/unit/test_calculate_snapshot.py`: 2 `get_active_snapshot` mocks, the same change.
- Lint-only test edits (T030, 2026-11-04, at the user's request): the 4 Ruff C408 errors were fixed by rewriting `dict(...)` as a `{...}` literal in `test_cache_cleanup.py`, `test_calculate_snapshot.py`, `test_price_calculation.py` and `test_standard_architecture_rules.py`. No behavior or expected value changed.

## Implementation notes

- **T018, `/health`** (2026-11-03): the body is unchanged (`status`, `pricing`, `pricing_reason`) and readiness stays tied to AWS. The planned per-provider detail was left out because the existing `/health` contract test asserts the exact body (T025: only tier tests change), and the per-provider status is already served by `GET /providers` (T028) and the Admin tab.
- **T018, `ACTIVE_SNAPSHOT_DATE`** pins AWS only. Azure and GCP publish on their own dates.
- **T006**: the tiered egress SKU was appended to the existing AWS fixture files, not rebuilt, because a rebuild reorders `product_dim` and `product_attribute` and some lookups take the first of several rows (`tests/fixtures/pricing_parquet/aws/README.md`).
- **T004**: the data has no Azure support plans, so the global-only item is a SQL Server licence.
- **US1 (T031 to T058), 2026-11-04. Decisions made while implementing**:
  - **Collection region errors stay 400.** T035 asked for 422. The existing region rule (010) answers 400 for an unavailable region, and its tests assert that, so every provider keeps 400. The region list is now the architecture provider's.
  - **Selection quantity is in the base unit.** An Azure or GCP price published for a block (`10K`, `100 Hours`, a GCP `unit_quantity`) is divided by the block size. The unit is shown as published.
  - **The Azure `vm` kind lists Linux meters only.** The `azure_vm` OS option picks the Windows meter of the same size. A Windows reservation with no published row is unpriced ("not published"), never priced at the Linux rate.
  - **GCP's `vm` kind lists the cores of predefined families.** Each core item names its RAM SKU in `attributes.ram_sku`, which the editor sends as `provider_options.ram_sku`. A SKU with two different matching commitment models is unpriced, because the right one can't be told.
  - **Per-item price types are checked only when the adapter reports them** (`reports_price_types`: Azure and GCP). AWS keeps its provider-level check, because existing AWS tests store placeholder SKUs.
  - **`SKUSelectionOut` gains `price_types` and `kind`.** This is an addition to contracts §4, so the Service Editor can offer an existing item's published types (FR-005).
  - **Unpriceable reasons start with "not published"** when the price is missing (contracts §5). Before, they started "no price for…".
  - **The 503 body gains `provider` and `reason`.** The message names the provider. It used to always say AWS.
  - **`/admin/system-info` gains `providers.{aws,azure,gcp}`.** Contracts §9 calls the route `/admin/system`; the existing route was kept. Its top-level snapshot fields stay AWS's, unchanged.
  - **The pricing panel shows a line's price type only when it isn't on demand**, so AWS lines look as before.
  - **Test helper fix**: the scratch-database teardown (`tests/helpers/pg.py`) now terminates client sessions only. A non-superuser test role can't signal autovacuum workers, which made migration and restore tests fail intermittently.
- **US1, existing tests changed** (each change is mechanical or follows from GCP and Azure becoming supported; no AWS expected value changed):
  - `tests/contract/test_providers.py`: `test_aws_active_gcp_azure_disabled` became `test_every_provider_with_a_snapshot_is_active`.
  - `tests/contract/test_architectures.py`: `test_non_aws_provider_rejected` became `test_unknown_provider_rejected` (`oracle`), plus a test that GCP and Azure can be created.
  - `tests/unit/test_architecture_transfer.py`: `test_rule4a_provider_not_supported` now simulates a provider with no adapter.
  - `tests/unit/test_price_calculation.py` (`_mock_reserved_price`, `_mock_no_period_units` and one inline units mock) and `tests/unit/test_calculate_snapshot.py` (2 mocks): `lookup_reserved_price` and `resolve_units` are patched on the AWS adapter module instead of `price_calculation`.
  - `tests/unit/test_architecture_import_file.py`: the per-region batching spy wraps `aws.find_existing_skus`.
- **US4 core and US2 (T059 to T082), 2026-11-04**:
  - **T082, Trends signal**: not available yet for Azure and GCP. Each local pipeline root has one weekly snapshot (2026-11-02), and at least 3 are needed. Measure once their weekly production runs start (pipeline 004 quickstart Part C). The local AWS history matches the spec's "Trends signal" assumption: 0 to 4 changes per week among up to 708,000 compared SKUs.
  - **The chart is small multiples**: one up/down bar chart per provider, with up above zero and down below. Price direction uses a new diverging pair, `--chart-up` (red) and `--chart-down` (blue), which passed the dataviz palette checks in light and dark. The project's `--chart-*` tokens are one sky-blue ramp and can't show direction. Each chart has a table view.
  - **The price list and changes also store `service_name` and `tiered`**, beyond data-model §7. The movers (US3) show the service name and the tier note.
  - **Service keys** are `a|b`: AWS `service_code|product_family`, Azure `service_family|service_name`, GCP taxonomy levels 1 and 2 after `GCP`. Rules match either part.
  - **History builds run only in the app's lifespan** (startup backfill and after each switch), never in tests. The new setting `PRICE_HISTORY_ENABLED` (default true) turns them off. The tests point `PRICING_HISTORY_DIR` at a temporary folder (`tests/conftest.py`).
  - **Empty stored chart providers mean the defaults** (every active provider, all regions). Reset stores `{providers: [], category: "all"}`.
  - **Existing test changed**: `tests/unit/test_settings.py::test_pricing_history_dir_defaults_to_persistent_user_folder` clears `PRICING_HISTORY_DIR`, which the conftest now sets for isolation.
- **US3 and US4 rest (T083 to T095), 2026-11-04**:
  - **The movers period is calendar weeks back from the newest snapshot.** The window holds every week pair that ends after that start, so a pair spanning a gap at the edge counts. `weeks_available` is the weeks the window covers, at most the period.
  - **A mover's end price is its price in the newest price list kept with the history**, not only its last recorded change. An item that is gone, or has no valid price at the end, is dropped. That covers "removed before the end" without a removed-items file.
  - **Ties** are ranked by the size of the price change, then service name, SKU description and region.
  - **`MoversOut` gains `status`, `reason` and `period_weeks`** beyond contracts §8, with the same statuses as a chart series, so the page can say why the lists are empty (building, not enough history, provider unavailable). `from_snapshot` and `to_snapshot` are null when there is no history.
  - **`period_weeks` is checked in the handler**, because a `Literal[1, 4, 13, 52]` query parameter doesn't accept the query string `"13"`.
  - **Prices are shown without trailing zeros** (`0.1`, not `0.10`), using the same decimal formatting as the rest of the comparable prices.
  - **Movers Reset clears the section** (`trends.movers: null`), and the page then shows the defaults (first available provider, all categories, all regions, 52 weeks).
  - **Column widths and collapsed columns map to `col1` to `col4` in column order**: provider, collections, service, pricing (no collapsed state for pricing).
  - **The one-time move runs on the first successful load where `migrated_from_browser` is false.** It sends the browser's old values with the account's own values winning per column, and sets the flag even when there is nothing to move. Until then the old browser values fill the gaps under the account's. The old browser keys are left in place, never written again.
  - **A stored last provider that is no longer active falls back to AWS and is cleared.** Opening an architecture still selects its provider without saving it; only picking a provider in column 1 saves it.
  - **Existing tests changed**: `preferences.test.ts` "applies a section patch at once…" now starts with `migrated_from_browser: true`, because a false flag now also sends the move. `columnWidths.test.ts` and `columnCollapse.test.ts` were rewritten for the account-backed behavior (T092). The `ChartSelectors.test.tsx` TrendsPage Reset test now finds the Reset button inside the charts section, as the page has two.
  - **T095 ran at API level** with two sign-in sessions for the same user, not in two real browsers; the page side is covered by unit tests (validation checklist, section E).
- **US5 arrows (T096 to T100), 2026-11-05**:
  - **`none` is a plain line** (user decision, 2026-11-05). FR-026 calls `none` "today's appearance", but since 010 every connector has had an arrowhead at its `to` end. To keep existing diagrams as they were, **migration 0008** (`6c3e9a1b5f08`) sets connectors still at `none` (and not reversed) to `one_way`. New connectors start as plain lines. Downgrade leaves the styles as they are.
  - **An export file without arrow fields imports as `one_way`**, for the same reason: it comes from before 019, when every connector had an arrowhead. Every new export writes `arrow_style` explicitly, so `none` round-trips.
  - **`PATCH /connectors/{id}` is new** (contracts §6 named it as changed). It takes only `arrow_style` and `arrow_reversed`, with unknown fields rejected. `arrow_reversed` must be a real boolean.
  - **The picker is in the connector section of `CollectionsPanel`**, not `DataConnectorPanel.tsx`, which nothing renders. One click once the connector is selected (SC-007). Reverse is disabled for `none` and `two_way`. The change applies to the cached architecture at once and is restored from the server on failure.
  - **Reversed arrows are a start marker on the same `from` → `to` path**, so routing, bends and side handles are unchanged. Branching styles (`one_to_many`, `many_to_one`) aren't offered in the picker until branches exist (phase 9).
  - **Existing tests changed**: none. `test_migration_0008.py` is new.
- **Polish (T109 to T112), 2026-11-05**:
  - **Phase 9 (branching connectors, T101 to T108) is deferred** to a later release (user decision). Those tasks stay open.
  - **The production stack now keeps the Trends history on a volume.** Without it, `PRICING_HISTORY_DIR` defaulted to the container's home folder, so every container restart would rebuild the whole history from S3. `compose.yaml` sets `PRICING_HISTORY_DIR=/var/lib/app/pricing-history` on a new `pricing-history` volume, and the Dockerfile creates that folder owned by `app`, like the cache folder. It is rebuilt on a new instance. Not run in Docker here (no Docker on this machine); the compose file was parsed and checked.
  - **`docs/configuration.md` gains the three new settings and a "Trends price history" section**, besides the README updates T109 named.
  - **T112, `ruff format --check` fails on 151 backend files**, 71 of them never touched by this feature: the backend has never been formatted with `ruff format`, and CI doesn't run it (CI runs `ruff check src/ scripts/ tests/`, which passes). Left as it is: reformatting the whole backend is a separate change. Every other T112 check passes: ruff check, lint (0 errors, the same 7 warnings), build, 351 frontend tests, 897 backend tests, and the API types (regenerated from the app's schema, since `check-api-types` needs a running server).

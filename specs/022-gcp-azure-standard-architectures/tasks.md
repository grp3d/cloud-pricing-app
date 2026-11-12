---

description: "Task list for 022 GCP and Azure standard architectures"
---

# Tasks: GCP and Azure Standard Architectures

**Input**: Design documents from `specs/022-gcp-azure-standard-architectures/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (`generator.md`,
`migration-0009.md`), quickstart.md

**Tests**: Included. Constitution Principle V requires tests first for DuckDB query logic and
for Postgres writes of user-defined data. Write each test before its implementation and see it
fail.

**Organization**: grouped by user story (spec.md). All paths are relative to the repo root.
Backend commands run from `backend/` with `uv run`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US4 from spec.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: make sure the pricing data the generator needs exists locally.

- [X] T001 Refresh the local GCP and Azure pricing snapshots so they include `europe-west1` (GCP) and `westeurope` (Azure), as in quickstart.md "Prerequisites". The commands run in `../cloud-pricing-data-retrieval`, with `PIPELINE_STORAGE_URI=file:///Users/Shared/agent-workspace/projects/cloud-pricing/_DATA-PIPELINE`. Then confirm `_DATA-PIPELINE/{gcp,azure}/manifests/latest.json` lists those regions under `regions.succeeded`. This is a **user step**: if it can't run in-session, stop and ask the user to run it. T001 blocks T015–T018 only.
- [X] T002 [P] Record the baseline: run `uv run python scripts/resolve_standard_architectures.py` (AWS) and confirm `git status backend/src/db/seed/` shows no change. That proves the AWS output is reproducible before any refactor.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: a provider-aware generator (research R3, R4) that every story builds on. The AWS
output must stay byte-identical.

**⚠️ CRITICAL**: complete this phase before any user story.

- [X] T003 Move the quantity formulas (`_q`, `always_on`, `per_hour_rate`, `monthly`, `daily_dpu`, `lambda_gb_seconds`, `fargate_vcpu`, `fargate_gb`, `kinesis_put_payload_units`, `as_stored`) from `backend/scripts/standard_architectures/match_rules.py` into a new `backend/scripts/standard_architectures/quantities.py`. Re-import them in `match_rules.py`, leaving the AWS rules untouched.
- [X] T004 [P] Write unit tests for `quantities.py` in `backend/tests/unit/test_standard_architecture_quantities.py`. Use known values from the AWS report, for example `monthly(10_000_000) == Decimal("322580.6452")`, `always_on(4) == Decimal("96.0000")` and `lambda_gb_seconds(15_000_000, 250, 1024)`. Add a new `dataflow_vcpu_hours`-style helper only if T015 needs it (test first).
- [X] T005 Re-run AWS generation and confirm no diff in `backend/src/db/seed/standard_architectures*.{json,md}`. Run `uv run pytest tests/unit/test_standard_architecture_rules.py`.
- [X] T006 [P] Write failing unit tests for a GCP SKU finder in `backend/tests/unit/test_standard_architecture_resolver_gcp.py`. Build tiny inline Parquet files (`sku`, `sku_price`) in `tmp_path` and cover:
  - the lowest `sku_id` wins among matches;
  - only `consumption_model_description = 'Default'` rows count;
  - the `region` partition plus `global` are both searched;
  - `expected_unit` filters;
  - an unrecognized unit (`parse_gcp_unit`) raises `UnrecognizedUnitError`;
  - no match becomes an `Omission` with a reason.
- [X] T007 [P] Write failing unit tests for an Azure meter finder in `backend/tests/unit/test_standard_architecture_resolver_azure.py`. Use inline `price_item` Parquet and cover:
  - only `type = 'Consumption'` counts;
  - filters on `service_name` / `product_name` / `sku_name` / `meter_name` / `arm_sku_name`;
  - the item is `<sku_id>/<meter_id>` (`providers/azure.py` `split_item`), and the lowest one wins;
  - region plus `global`;
  - an unrecognized unit (`parse_azure_unit`) raises;
  - no match becomes an omission.
- [X] T008 Add the rule dataclasses `GcpMatchRule` and `AzureMatchRule` in `backend/scripts/standard_architectures/resolver.py` (or a new `rules_base.py` beside it), following data-model §4. Their fields are `architecture_id`, `aws_component_id`, `figure`, `region`, the provider filters, `expected_unit`, `quantity`, `provider_options`, `size_note`, `omit_reason` and `note`. Make `Match` carry `provider_options`.
- [X] T009 Implement `_find_gcp` and `_find_azure` in `backend/scripts/standard_architectures/resolver.py`, reading files through the same `FilesFor` callable as AWS. Make `resolve(rules, files=…, snapshot_date=…, provider=…)` dispatch by provider, with the AWS path unchanged, until T006 and T007 pass.
- [X] T010 Make `to_export_file` provider-aware in `backend/scripts/standard_architectures/resolver.py`:
  - set `provider` on each `ArchitectureDefinition`;
  - name collections "VPC (<region>)" for aws and gcp, "VNet (<region>)" for azure (research R8);
  - map the AWS reference regions to the provider's regions through a `REGIONS` table exported by each rules module;
  - pass `provider_options` through to `SKUSelectionDefinition`.

  The AWS output must stay identical, so re-run T005's check.
- [X] T011 Add `--provider aws|gcp|azure` (default `aws`) to `backend/scripts/resolve_standard_architectures.py`, following `contracts/generator.md`:
  - pick the rules module;
  - call `select_snapshot(store, provider, settings.active_snapshot_date if provider == "aws" else None, at_startup=True)`;
  - write `standard_architectures.json` / `_report.md` for aws, and `standard_architectures_<provider>.json` / `_<provider>_report.md` otherwise;
  - exit 1 on an unrecognized unit or an empty architecture, writing nothing.

  Update the module docstring.

**Checkpoint**: the generator runs for all three providers; GCP and Azure have no rules yet.
The AWS output is unchanged.

---

## Phase 3: User Story 1 - A GCP or Azure user starts from a standard architecture (Priority: P1) 🎯 MVP

**Goal**: four public Admin GCP architectures and four Azure ones, each of which prices fully.

**Independent Test**: on a freshly migrated database, each provider shows exactly four public
Admin architectures, and each of the eight calculates a non-zero total with every service
priced.

### Tests for User Story 1 ⚠️ (write first, see them fail)

- [X] T012 [P] [US1] Extend `backend/tests/integration/test_standard_architecture_seed.py`, parametrized over the GCP and Azure seed files:
  - each holds exactly the four reference names with the right `provider`;
  - one collection per design region from research R1;
  - every selection is `on_demand` / `not_applicable`;
  - every GCP Compute Engine and Cloud SQL instance selection has `gcp_machine` options, and every Azure VM has `azure_vm {os: linux}`;
  - the file passes `validate_definition` against the pricing data (`find_existing_skus`, `list_available_regions`), as the AWS test does.
- [X] T013 [P] [US1] Extend `backend/tests/integration/test_standard_architecture_pricing.py` so its `definition` parameter also covers the eight GCP and Azure architectures. Each prices with no unpriceable items and a total above 0 (SC-002).
- [X] T014 [P] [US1] Create `backend/tests/integration/test_migration_0009.py` to cover the basic insert from `contracts/migration-0009.md`. On a database at 0008 holding the default Admin and the AWS four, upgrading to 0009 gives 8 more public Admin architectures (4 gcp, 4 azure). Their collections and selections match the seed files, including `provider_options` JSON, and the AWS four are unchanged. Reuse the patterns in `backend/tests/integration/test_migration_0008.py`.

### Implementation for User Story 1

- [X] T015 [US1] Write `backend/scripts/standard_architectures/match_rules_gcp.py`. Start with a `REGIONS` map (research R1) and give one rule per figure of every reference component, in reference order, with conversions from research R5 and sizes from research R6:
  - machines are e2-standard-4 and e2-standard-2 with `gcp_machine` options (core SKU plus `ram_sku`, vcpus, memory_gib);
  - Cloud SQL instances use their vCPU and RAM SKUs through `gcp_machine` options;
  - Memorystore is the 7 GB Standard tier;
  - global-only services go in the design's first region;
  - Fargate pods map to GKE Autopilot pod vCPU-hours and memory GiB-hours;
  - Redshift Serverless is left out (no like-for-like unit; research R5);
  - components left out of the AWS version get `omit_reason` "left out to match the AWS version: …".

  No complex conversions: a figure is matched only when the counterpart bills the same kind of unit with at most a simple scale; otherwise it's left out with a reason (research R5, guiding rule). Every sized rule gets a `size_note`, for example "t4g.xlarge 4/16 → e2-standard-4 4/16". Depends on T001 and T011.
- [X] T016 [P] [US1] Write `backend/scripts/standard_architectures/match_rules_azure.py` the same way:
  - VMs are Standard_D4s_v5 and Standard_D2s_v5 with `azure_vm {os: linux}`;
  - PostgreSQL Flexible E4ds_v5 and MySQL Flexible D4ds_v4 with zone-redundant high availability;
  - Redis Standard C4;
  - the Serverless design is in `westeurope`;
  - AKS is left out if the Free tier has no meter;
  - Fargate pods and Redshift Serverless are left out (research R5).

  Size notes as for GCP. Depends on T001 and T011.
- [X] T017 [US1] Run `uv run python scripts/resolve_standard_architectures.py --provider gcp`, then `--provider azure`, and read both reports. Where a figure is left out but a matching SKU exists in the data, correct the rule (filters, unit, fallback size per research R6) and re-run, until every left-out row has a real reason. This writes `backend/src/db/seed/standard_architectures_{gcp,azure}.json` and `_report.md`.
- [X] T018 [US1] Extend `backend/scripts/build_provider_fixtures.py` so the GCP and Azure fixtures include every `(service_code, sku)` in the two new seed files, read from the files as `build_test_pricing_fixture.py`'s `_standard_architecture_skus()` does. Add locations `us-west1` and `europe-west1` (GCP) and `westus2` and `westeurope` (Azure). Rebuild `backend/tests/fixtures/pricing_parquet/{gcp,azure}/` and update their README expected-price notes if the script requires it. The AWS fixture is untouched.
- [X] T019 [US1] Create `backend/src/db/migrations/versions/0009_gcp_azure_standard_architectures.py`, revising `6c3e9a1b5f08`, in the plain-SQL style of 0005:
  - read the two seed files in order (gcp, then azure);
  - insert the architecture (public), the collections, and the selections with `provider_options` as JSON;
  - use `clock_timestamp()`;
  - return early with no default Admin;
  - downgrade deletes only Admin-owned gcp and azure architectures with the seeded names.

  T012–T014 must now pass.
- [X] T020 [US1] Run `uv run alembic upgrade head` locally and follow quickstart.md §4 steps 1–4 (menu groups, Import list, Calculate, GCP machine fields and Price Change).

**Checkpoint**: US1 works on a fresh database and on the local one.

---

## Phase 4: User Story 2 - They appear in every environment without manual steps (Priority: P1)

**Goal**: created once per database, in fresh, existing and restored environments. Never
recreated or renamed back.

**Independent Test**: bring up an environment restored from a pre-release backup; exactly
eight are added. Bring it up again; nothing changes.

### Tests for User Story 2 ⚠️

- [X] T021 [P] [US2] Add skip-rule tests to `backend/tests/integration/test_migration_0009.py`, covering the `contracts/migration-0009.md` table:
  - the Admin already owns a non-deleted GCP "Serverless Microservices Back-End", so 7 are added;
  - a *deleted* one with that name doesn't block insertion;
  - a same-name AWS architecture doesn't block the GCP and Azure ones;
  - with no default Admin, nothing is added and the upgrade succeeds;
  - downgrade then upgrade adds 8 again, and downgrade leaves AWS untouched.
- [X] T022 [P] [US2] Add `test_backup_from_before_0009_gains_the_eight_standard_architectures` to `backend/tests/integration/test_db_init_restore.py`. Restore a backup taken at 0008 and run db-init: exactly 8 GCP and Azure Admin architectures are added. Run db-init again on the now-current database: no change (SC-003). Run with `PATH=/opt/homebrew/opt/postgresql@18/bin:$PATH`, so the restore tests aren't skipped.

### Implementation for User Story 2

- [X] T023 [US2] Make T021 and T022 pass. Any fix goes in `backend/src/db/migrations/versions/0009_gcp_azure_standard_architectures.py`; db-init needs no change if T022 passes as written.
- [X] T024 [US2] Add a seed-level test in `backend/tests/integration/test_standard_architecture_seed.py`: the AWS seed and report are byte-identical to `git show HEAD:` versions taken before this feature. Pin the SHA-256 of `standard_architectures.json` and `standard_architectures_report.md` in the test (FR-009, SC-006).

**Checkpoint**: US1 and US2 together are shippable.

---

## Phase 5: User Story 3 - It's clear what was matched and what was left out (Priority: P2)

**Goal**: a report per provider that names, for every AWS component, the match or the reason
it was left out. Generation is repeatable.

**Independent Test**: every component of every AWS original appears in both reports, matched
or left out with a reason.

### Tests for User Story 3 ⚠️

- [X] T025 [P] [US3] Write unit tests for report rendering in `backend/tests/unit/test_standard_architecture_report.py`, covering `contracts/generator.md`:
  - the GCP and Azure matches table has the columns `AWS component | Figure | Region | Service | SKU | Unit | Quantity | Tiered | Size | Note`;
  - the Left out table has `AWS component | Figure | Reason`;
  - the header names the provider and snapshot;
  - the AWS report rendering is unchanged.
- [X] T026 [P] [US3] Write a rules-completeness test in `backend/tests/unit/test_standard_architecture_rules.py`: for gcp and azure, every `(component id, usage figure)` of `docs/brief/common_aws_architectures.md` has exactly one rule, and every rule's `aws_component_id` exists in the reference (SC-004).
- [X] T027 [P] [US3] Write a determinism test in `backend/tests/integration/test_standard_architecture_seed.py`: resolve the GCP and Azure rules twice against the test fixture data and assert byte-identical seed and report output (SC-005). Skip with a reason if the fixture lacks a rule's region.

### Implementation for User Story 3

- [X] T028 [US3] Make T025–T027 pass. Implement the provider-aware `render_report` in `backend/scripts/standard_architectures/resolver.py`: the AWS layout stays as is; GCP and Azure get the extra columns. Then regenerate both providers (T017's commands) so the checked-in reports have the final layout.

**Checkpoint**: the reports are complete and reproducible.

---

## Phase 6: User Story 4 - A user compares a design across the providers (Priority: P2)

**Goal**: the three versions of each design line up for a like-for-like comparison.

**Independent Test**: for one design, all three versions share the name, the collection count
and order, and the usage figures wherever a matching service exists.

### Tests for User Story 4 ⚠️

- [X] T029 [P] [US4] Add a cross-provider consistency test in `backend/tests/integration/test_standard_architecture_seed.py`. For each design, the AWS, GCP and Azure seeds have the same architecture name and the same number of collections in the same reference-region order. Every GCP and Azure selection traces back, through its rule, to an AWS reference figure.

### Implementation for User Story 4

- [X] T030 [US4] Make T029 pass; any fix is in the rules modules. Then follow quickstart.md §4 step 5: calculate the three "Serverless Microservices Back-End" versions at 1 month and record the totals in the PR description.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T031 [P] Update `docs/features/accounts-and-sharing.md`, section "Standard architectures":
  - each provider now has four;
  - where each provider's report lives;
  - the regions used, including westeurope standing in for Ireland;
  - left-out components are listed only in the reports.

  Add one line to `CHANGELOG.md` under the next release heading (pre-1.0, for example v0.2.0 or v0.1.2, as the owner chooses). Don't touch the README.
- [ ] T032 [P] **Skipped** (the e2e backend uses the small hand-picked fixture, which doesn't hold the new SKUs; the full e2e suite still passes with migration 0009 applied). Optional: add `frontend/e2e/standard-architectures.spec.ts`. Open one GCP and one Azure standard architecture from the header menu and click Calculate; the total is non-zero and no row says unpriceable. Reuse `frontend/e2e/helpers.ts`. Skip it if the e2e backend fixture can't serve the new SKUs.
- [X] T033 Run the full backend suite with `PATH=/opt/homebrew/opt/postgresql@18/bin:$PATH uv run pytest` and confirm 0 skipped restore tests. Run `uv run ruff check` on the touched files only (no formatting of whole folders).
- [X] T034 Run quickstart.md §1–§4 end to end. Confirm that re-running each generator command leaves `git status backend/src/db/seed/` clean.

---

## Dependencies & Execution Order

- **Setup:** T001 is a user data step that blocks only T015–T018. T002 runs anytime first.
- **Foundational:** T003 → T005. T004, T006 and T007 can run in parallel with each other. T008 → T009 → T010 → T011. This phase blocks all stories.
- **US1:**
  - T012, T013 and T014 (tests) are written first.
  - T015 and T016 (rules) need T001 and T011.
  - Then T017 → T018 → T019 → T020.
- **US2:** needs T019. T021 and T022 run in parallel, then T023 and T024.
- **US3:** T025–T027 can be written any time after Phase 2. T028 needs T017.
- **US4:** needs T017. T029 → T030.
- **Polish:** after the stories you ship.

### Parallel examples

- Phase 2: T004, T006 and T007 together (three new test files).
- US1: T012, T013 and T014 together. Then T015 and T016 together (separate rule modules).
- US2: T021 with T022.
- US3: T025, T026 and T027 together.

## Implementation Strategy

1. **MVP:** Phases 1–3 (US1) give eight pricing architectures on fresh and local databases.
2. **Ship gate:** add US2 (restore and once-only behaviour) before any release, because
   production has data.
3. **Then** US3 (report quality and determinism tests), US4 (consistency check), and Polish.
4. **Release:** merge, CI, tag (pre-1.0), `deploy/app up`. Check the `db-init` log for the 0009
   upgrade, and that 12 standard architectures are visible (quickstart §5).

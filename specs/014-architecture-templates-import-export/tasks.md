---

description: "Task list for 014-architecture-templates-import-export"
---

# Tasks: Standard Architectures and Admin Architecture Import/Export

**Input**: Design documents from `specs/014-architecture-templates-import-export/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, contracts/export-format.md, quickstart.md

**Tests**: Included, and written **first**. The constitution's Principle V makes test-first mandatory for pricing and unit logic, DuckDB queries, and Postgres reads and writes of user-defined data. Every backend test task below MUST be written and seen failing before the implementation task it covers. Frontend presentational tests may follow implementation.

**Organization**: Tasks are grouped by user story, so each story can be built and tested on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 = standard architectures (P1), US2 = admin export (P2), US3 = admin import (P2)
- Paths are relative to the repository root (`backend/`, `frontend/`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new directories the plan introduces.

- [ ] T001 Create the resolver package `backend/scripts/standard_architectures/__init__.py` (empty) and the seed directory `backend/src/db/seed/`, containing only a `.gitkeep` until T016 generates its files, as laid out in plan.md › Project Structure

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pieces all three stories depend on:
- Newly recognized billing units (research §6).
- The batched SKU-existence lookup (research §9).
- The version-1 export-format models (contracts/export-format.md).
- The per-architecture validator (data-model.md › Validation rules).
- The shared row builder (research §10).

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

### Tests (write first, confirm they fail)

- [ ] T002 [P] Add failing cases to `backend/tests/unit/test_duration.py`:
  - `classify_unit` returns `no_period` for `LCU-Hrs`, `Queries`, `ShardHour`, `PutRequest`, `DPU-Hour`, `Terabytes`, `RPU-Hr`, `ReadRequestUnits`, `WriteRequestUnits`, `GB-Hours` and `Notifications`.
  - It returns `fixed_period` with `period_days == 31` for `Obj-Month`, `Mo`, `CognitoUserPoolsMAU` and `GigaBytesMonth`.
  - Existing assertions stay unchanged.
- [ ] T003 [P] Add failing tests to `backend/tests/unit/test_catalog.py` for a new `find_existing_skus(pairs: Iterable[tuple[str, str]], *, region: str, snapshot_date: str | None = None) -> set[tuple[str, str]]` in `backend/src/pricing_data/catalog.py`:
  - It returns only the `(service_code, sku)` pairs present in that region's `product_dim` partition for the latest snapshot.
  - Use fixture SKUs `("AmazonEC2", "NN4EGUUQRWVYP98C")` in `us-east-1` (present) and `("AmazonEC2", "ZZZZZZZZZZZZZZZZ")` (absent).
  - The same EC2 SKU queried in `eu-west-1` is absent, because SKUs are region-scoped.
  - An empty input returns an empty set without querying.
  - A DuckDB error raises `PricingDataUnavailableError`.
- [ ] T004 [P] Create `backend/tests/unit/test_architecture_transfer.py` with failing tests for the validator in `backend/src/services/architecture_transfer.py`:
  - `validate_envelope(doc: dict) -> None` raises `InvalidImportFileError` for:
    - a non-object body;
    - `format` other than `"cloud-pricing-architectures"`;
    - `format_version` not in `{1}`;
    - `architectures` missing or not a list.
  - `validate_definition(raw: dict, *, taken_names: set[str], available_regions: set[str], existing_skus: Callable[[str, set[tuple[str,str]]], set[tuple[str,str]]]) -> tuple[ArchitectureDefinition | None, str | None]` applies the data-model.md rules **in order**: 1, 2, 3, 4, 4a, 5, 6. It returns the first failure message, worded exactly as in the data-model.md table:
    - a malformed entry → `Invalid architecture definition: …`;
    - a duplicate name, including one in `taken_names` → `Architecture name already exists`;
    - an unknown `parent_ref`/`from_ref`/`to_ref`, or `from_ref == to_ref` → `Invalid reference: …`;
    - a `vpc` with a parent, or an application component whose parent isn't a `vpc` → `Invalid nesting: …`;
    - provider `gcp` → `Provider not supported: gcp`;
    - an unknown region → `Region not available in pricing data: …`;
    - a missing SKU → `Service not found in pricing data: <service_code> / <sku> (<region>)`.
  - A connector's SKU is checked in its `from` collection's region.
  - `usage_quantity` is accepted as either a string or a number.
  - Unknown extra fields are ignored.

### Implementation

- [ ] T005 [P] Add the units from T002 to `_NO_PERIOD_UNITS` and `_FIXED_PERIOD_UNITS` in `backend/src/pricing_data/duration.py`. Include a comment citing 014 research §6 and stating that every added unit is time-based in AWS's own definition. T002 must pass.
- [ ] T006 [P] Implement `find_existing_skus` in `backend/src/pricing_data/catalog.py`:
  - Use one `SELECT DISTINCT service_code, sku FROM read_parquet(<product_dim path for snapshot/region>) WHERE sku IN (…)` per call, reusing `_product_dim_path` and `resolve_latest_snapshot_date`.
  - Wrap `duckdb.Error` as `PricingDataUnavailableError`.
  - T003 must pass.
- [ ] T007 [P] Add the version-1 export-format Pydantic models to `backend/src/models/schemas.py`, per contracts/export-format.md and data-model.md, with `model_config = ConfigDict(extra="ignore")` on each:
  - `SKUSelectionDefinition`: `usage_quantity: Decimal`, `ge=0`, `decimal_places=4`, serialized as a string.
  - `CollectionDefinition`: `ref`, `type` Literal, `name` 1..255 and trimmed, `region`, `parent_ref: str | None`, `sku_selections`.
  - `ConnectorDefinition`: `from_ref`, `to_ref`, `sku_selection: SKUSelectionDefinition | None`.
  - `ArchitectureDefinition`: `name` 1..255 and trimmed, `provider` Literal `aws`/`gcp`/`azure`, `collections`, `connectors`.
  - `ArchitectureExportFile`: `format: Literal["cloud-pricing-architectures"]`, `format_version: Literal[1]`, `exported_at: datetime`, `source_username: str`, `architectures: list[ArchitectureDefinition]`.
  - `ArchitectureImportRequest`: `format: str`, `format_version: int`, `exported_at: datetime | None`, `source_username: str | None`, `architectures: list[dict[str, Any]]`.
  - `ImportResult`: `name: str | None`, `status: Literal["success", "failed"]`, `error: str | None`.
  - `ArchitectureImportResponse`: `imported_count`, `failed_count`, `results`.
  - A module-level `EXPORT_FORMAT = "cloud-pricing-architectures"` and `SUPPORTED_FORMAT_VERSIONS = frozenset({1})`.
- [ ] T008 Create `backend/src/services/architecture_transfer.py` (depends on T007):
  - `InvalidImportFileError(ValueError)`.
  - `validate_envelope` and `validate_definition`, per T004 (rules in data-model.md order).
  - A shared `build_architecture(session, *, owner: User, name: str, provider: str, collections: Sequence[CollectionSpec], connectors: Sequence[ConnectorSpec]) -> Architecture`. It adds new rows with explicit `uuid.uuid4()` ids, remaps parent and connector refs to the new ids in one parent-first pass (the same approach as today's `architecture_import.py`), sets `is_public=False`, and does **not** commit.
  - `CollectionSpec`/`ConnectorSpec` are small dataclasses holding a `ref`, the fields, and SKU-selection tuples.
  - T004 must pass.
- [ ] T009 Refactor `backend/src/services/architecture_import.py` so `import_architecture` converts the ORM source into `CollectionSpec`/`ConnectorSpec` (ref = str(collection.id)), calls `architecture_transfer.build_architecture`, then commits and refreshes. Behavior MUST stay the same, and the existing `backend/tests/unit/test_architecture_import.py` and `backend/tests/contract/test_architecture_sharing.py` must pass unmodified (depends on T008).

**Checkpoint**: New units priced, SKU lookup batched, format models plus validator plus builder in place. All user stories can start.

---

## Phase 3: User Story 1 - Every user can start from a standard architecture (Priority: P1) 🎯 MVP

**Goal**: Four public, Admin-owned standard architectures, created from `docs/common_aws_architectures.md` via checked-in match rules. Each has one VPC per listed region, one priced service entry per matched usage figure, and no application components or connectors. They are seeded once by migration.

**Independent Test**: quickstart.md steps 1–3. On a migrated database, Admin sees all four. Another user copies one from the Import list and sees the expected VPCs and priced entries.

### Tests for User Story 1 (write first, confirm they fail) ⚠️

- [ ] T010 [P] [US1] Create `backend/tests/unit/test_standard_architecture_rules.py` with failing tests.
  - **Quantity formulas**, pure functions in `backend/scripts/standard_architectures/match_rules.py`, each rounded to 4 decimal places:
    - `always_on(count)` → `count*24`;
    - `per_hour_rate(lcu)` → `lcu*24`;
    - `monthly(n)` → `n/31`;
    - `daily_dpu(dpu, hours)` → `dpu*hours`;
    - `lambda_gb_seconds(executions, avg_ms, memory_mb)` → `executions*(avg_ms/1000)*(memory_mb/1024)/31`, giving 120967.7419 for the JSON's values;
    - `fargate_vcpu(pods, vcpu)` → `pods*vcpu*24`;
    - `fargate_gb(pods, gb)` → `pods*gb*24`;
    - `as_stored(n)` → `n`.
  - **Resolver behavior**, in `backend/scripts/standard_architectures/resolver.py`, run against a tiny synthetic `product_dim`/`price_fact` Parquet written to `tmp_path` with a DuckDB `COPY`:
    - (a) Of several matching SKUs, the one first by `sku` ascending is chosen.
    - (b) Candidates are tried in order, so a rule with `["AWSELB", "AmazonEC2"]` falls back to `AmazonEC2` when the region has no `AWSELB` rows.
    - (c) Exact attribute filters on `attributes_json` exclude near-misses, e.g. an `"Accelerated InterRegion Outbound"` `transferType`.
    - (d) A rule matching nothing yields an omission record with a reason, not an entry.
    - (e) An `omit` rule with an explicit reason (App Mesh, gp3 IOPS) yields an omission without querying.
    - (f) A chosen SKU whose On-Demand `unit` isn't recognized by `classify_unit` raises `UnrecognizedUnitError`.
    - (g) A SKU with more than one On-Demand price row is flagged `tiered=True` in the report data.
    - (h) The output is byte-identical across two runs.
- [ ] T011 [P] [US1] Create `backend/tests/integration/test_standard_architecture_seed.py` with failing tests over `backend/src/db/seed/standard_architectures.json`:
  - **(a) Shape.** It parses as `ArchitectureExportFile`, with exactly the four names from spec FR-001.
  - **(b) VPCs.** Every collection is a `vpc` named `VPC (<region>)`, one per region the source JSON lists for that architecture: `us-east-1`+`us-west-2`; `us-east-1`; `eu-west-1`; `us-west-2`. There are no `application_component`s and no connectors (FR-005, FR-007).
  - **(c) Global components.** Route 53 and CloudFront entries sit in the first listed region's VPC (FR-006).
  - **(d) Pricing terms.** Every selection is `on_demand`/`not_applicable`.
  - **(e) Validation.** Every definition passes `validate_definition` against the CI fixture (`find_existing_skus` plus `list_available_regions`).
  - **(f) Migration insert.** Load migration `0005` with `importlib` and call its `insert_standard_architectures(connection)` inside a transaction that is rolled back afterwards. This yields four Admin-owned architectures with `is_public = true`, VPC collections and SKU selections matching the file. A second call inserts nothing, because of the name guard.
- [ ] T012 [P] [US1] Create `backend/tests/integration/test_standard_architecture_pricing.py` with a failing test:
  - For each seeded definition, build it with `architecture_transfer.build_architecture` under a test user and flush.
  - Run `calculate_architecture_price(…, one_month)` against the fixture.
  - Assert `unpriceable == []`, every line item is priced, and `total_price > 0` (SC-003).

### Implementation for User Story 1

- [ ] T013 [US1] Implement `backend/scripts/standard_architectures/match_rules.py`.
  - **Quantity formula functions** from T010.
  - **`MatchRule`**, a frozen dataclass: `architecture_id`, `component_id`, `figure`, `region`, `service_codes: tuple[str, ...]`, `product_family`, `attribute_filters: dict[str, str]` (exact equality on `attributes_json` keys, always including `locationType: "AWS Region"` where that attribute exists), `expected_unit`, `quantity: Decimal`, `omit_reason: str | None`.
  - **`RULES`**, one rule per usage figure of every component in `docs/common_aws_architectures.md`, per research §3–§5 and §7:
    - "global" components use the architecture's first region.
    - ELB uses `("AWSELB", "AmazonEC2")`.
    - API Gateway uses `AmazonApiGateway`, SQS uses `AWSQueueService`, and Fargate uses `AmazonEKS` with `usagetype` `USW2-Fargate-vCPU-Hours:perCPU` and `USW2-Fargate-GB-Hours`.
    - The EKS cluster uses `usagetype` `USW2-AmazonEKS-Hours:perCluster`.
    - S3 Glacier Instant Retrieval uses `storageClass` `"Archive Instant Retrieval"`.
    - Cross-region transfer uses `transferType` `"InterRegion Outbound"` with `toLocation` "US West (Oregon)".
    - The Aurora instance filters on `databaseEngine: "Aurora PostgreSQL"`, `instanceType: "db.r6g.xlarge"` and the Standard storage configuration, with a report note that Multi-AZ isn't expressible.
    - Omit rules, with the reasons from research §4/§7.1, cover App Mesh and RDS MySQL gp3 `provisionedIOPS` ("included in gp3 baseline").
- [ ] T014 [US1] Implement `backend/scripts/standard_architectures/resolver.py` (depends on T013):
  - `resolve(rules, *, parquet_dir, snapshot_date) -> Resolution`, using the DuckDB `product_dim` join to On-Demand `price_fact`, ordered by `sku`.
  - Candidate fallback, the unit check via `src.pricing_data.duration.classify_unit`, and tiered detection.
  - `to_export_file(resolution, source) -> ArchitectureExportFile`: collections `c1…` per region in the source's region order, named `VPC (<region>)`, with selections in rule order and `source_username` `"Admin"`.
  - `render_report(resolution) -> str` (markdown): per architecture, a table of component · figure · service_code · sku · unit · quantity · tiered, followed by an "Omitted" table of component · figure · reason.
  - T010 must pass.
- [ ] T015 [US1] Implement the CLI `backend/scripts/resolve_standard_architectures.py` (argparse: `--source` defaults to `../docs/common_aws_architectures.md`, which is pure JSON; `--parquet` defaults to `settings.aws_pricing_parquet_dir`; `--snapshot-date` defaults to the latest).
  - It writes `backend/src/db/seed/standard_architectures.json` (`indent=2`, trailing newline) and `backend/src/db/seed/standard_architectures_report.md`.
  - It exits non-zero on `UnrecognizedUnitError`, and fails if any architecture ends up with zero entries.
  - Add a module docstring with usage, in the style of `backend/scripts/build_test_pricing_fixture.py` (depends on T014).
- [ ] T016 [US1] Run `uv run python scripts/resolve_standard_architectures.py` from `backend/` against the real dataset and commit the two generated files in `backend/src/db/seed/`. Review the report and confirm:
  - App Mesh and gp3 IOPS are listed as omitted.
  - The us-east-1 ALB resolved to `AmazonEC2` and the us-west-2 ALB to `AWSELB`.
  - No near-miss SKUs (Accelerated transfer, Outposts, non-Redis cache) were chosen.

  If any additional unit is reported as unrecognized, add it to `duration.py` with a test first, as in T002/T005, and re-run (depends on T015).
- [ ] T017 [US1] Add every SKU in the generated seed file to `SEED_SKUS` in `backend/scripts/build_test_pricing_fixture.py`, grouped under a `# 014 standard architectures` comment. Rebuild `backend/tests/fixtures/pricing_parquet/` with `uv run python scripts/build_test_pricing_fixture.py --source "$AWS_PRICING_PARQUET_DIR"`, using the same snapshot date the seed was resolved against (depends on T016).
- [ ] T018 [US1] Create the Alembic data migration `backend/src/db/migrations/versions/0005_standard_architectures.py` (`down_revision = 'db1df84f4a73'`).
  - A module-level `insert_standard_architectures(connection)`:
    - reads `src/db/seed/standard_architectures.json`, resolved relative to the migration file, with plain `json`;
    - looks up the Admin id (`is_default_admin = true`);
    - for each architecture whose name the Admin doesn't already own (with `deleted_at IS NULL`), inserts `architectures` (`is_public = true`, `provider`), `collections` and `sku_selections` rows with raw `sa.text` INSERTs and `uuid.uuid4()` ids, in the style of `0004_user_accounts_sharing.py`. It does not import the app ORM.
  - `upgrade()` calls it with `op.get_bind()`.
  - `downgrade()` deletes the Admin's architectures with those four names, together with their SKU selections and collections.
  - T011 and T012 must pass (depends on T016, T017).
- [ ] T019 [US1] Run `uv run alembic upgrade head` against `cloud_pricing_dev`, then perform quickstart.md steps 2–3 (Admin sees four; re-running upgrade creates no duplicates; the multi-region architecture has two VPCs; a non-admin user copies "Serverless Microservices Back-End" via Import and it prices with no unpriceable items).

**Checkpoint**: US1 is fully functional. The four standard architectures exist, are public and price correctly.

---

## Phase 4: User Story 2 - Admin exports a user's architectures to a file (Priority: P2)

**Goal**: Two new Admin-table columns with wrapped headers. An Export button, disabled for users with no architectures, downloads all of that user's non-deleted architectures as `<username>_<YYYYMMDDTHHMMSS>.json` in export format version 1.

**Independent Test**: quickstart.md step 4.

### Tests for User Story 2 (write first, confirm they fail) ⚠️

- [ ] T020 [P] [US2] Create `backend/tests/unit/test_architecture_export.py` with failing tests for `serialize_user_architectures(architectures, *, username, now) -> ArchitectureExportFile` in `backend/src/services/architecture_transfer.py`:
  - Soft-deleted architectures and collections are excluded, and so are connectors that touch a deleted collection.
  - Refs are `c1…cn` per architecture, with parents before children.
  - `parent_ref` and connector `from_ref`/`to_ref` map correctly, and a connector's `sku_selection` is serialized.
  - `usage_quantity` is serialized as a 4-decimal string.
  - The output contains no `id`, `user_id`, `is_public` or price keys anywhere (FR-016).
  - A round trip through `validate_definition` plus `build_architecture` reproduces the same collections, nesting, connectors and selections (SC-004).
- [ ] T021 [P] [US2] Create `backend/tests/contract/test_admin_architecture_export.py` with failing tests:
  - `GET /api/v1/admin/users` items include `architecture_count` (0 for a new user, and excluding deleted architectures).
  - `GET /api/v1/admin/users/{id}/architectures/export` returns 200 with `format == "cloud-pricing-architectures"`, `format_version == 1`, `source_username` and every non-deleted architecture.
  - It returns 403 with non-admin `auth_headers`, 401 with no header, and 404 for an unknown id or a guest id.
- [ ] T022 [P] [US2] Create `frontend/tests/unit/exportFilename.test.ts` for `buildExportFilename(username: string, now: Date): string` in `frontend/src/lib/exportFilename.ts`:
  - `("jdoe", 2026-09-25 14:30:22 local)` → `jdoe_20260925T143022.json`.
  - Characters outside `[A-Za-z0-9._-]` become `_`, e.g. `"a b/c"` → `a_b_c_…`.
  - Month, day, hour, minute and second are zero-padded.

### Implementation for User Story 2

- [ ] T023 [US2] Implement `serialize_user_architectures` in `backend/src/services/architecture_transfer.py`, per contracts/export-format.md. T020 must pass.
- [ ] T024 [US2] Add `architecture_count: int` to `AdminUserOut` in `backend/src/models/schemas.py`, and compute it in `list_users` in `backend/src/api/admin_users.py` with one grouped `count(Architecture.id)` over `deleted_at IS NULL`, outer-joined to users. Pass it through `_to_admin_user_out`, and use `0` in the create, patch and password responses.
- [ ] T025 [US2] Add the route `GET /admin/users/{user_id}/architectures/export` (`response_model=ArchitectureExportFile`) to `backend/src/api/admin_users.py`. It uses `_get_named_user_or_404`, loads the user's non-deleted architectures with collections, SKU selections and connectors eager-loaded (`selectinload`, like the existing architecture detail route), and returns `serialize_user_architectures(..., now=datetime.now(UTC))`. T021 must pass (depends on T023, T024).
- [ ] T026 [US2] With the backend running, regenerate `frontend/src/api/generated/schema.d.ts` (`npm run generate-api-types`). In `frontend/src/api/client.ts`, add the type alias `ArchitectureExportFile = components["schemas"]["ArchitectureExportFile"]` and `exportUserArchitectures(userId)`, per contracts/api.md (depends on T025).
- [ ] T027 [P] [US2] Implement `buildExportFilename` in `frontend/src/lib/exportFilename.ts`. T022 must pass.
- [ ] T028 [US2] Update `frontend/src/pages/AdminPage.tsx`.
  - Insert two `<th>` headers between Password and Purge: "Import Architectures from Disk" and "Export Architectures to Disk". Give them `whitespace-normal leading-tight max-w-[6.5rem]`, so each wraps onto 2–3 lines (FR-011).
  - In each row, add an Import cell. It stays empty until T036.
  - In each row, add an Export cell with an outline `xs` "Export" button. The button is disabled when `user.architecture_count === 0` or an export is pending.
  - On click, call `api.exportUserArchitectures(user.id)`, create `new Blob([JSON.stringify(doc, null, 2)], {type: "application/json"})` and a temporary `<a download={buildExportFilename(user.username, new Date())}>`, click it, then revoke the object URL (FR-013, FR-014).
  - Depends on T026, T027.

**Checkpoint**: US2 works independently. Export downloads a correct file for any user with architectures.

---

## Phase 5: User Story 3 - Admin imports architectures from a file into a user's account (Priority: P2)

**Goal**: An Import button on each user row reads a local JSON file. A malformed file is rejected as a whole. Otherwise each architecture is validated and inserted on its own, with all-or-nothing writes per architecture, private and owned by that user. A ✓/✗ popup lists the result for each architecture.

**Independent Test**: quickstart.md step 5. It can be run with a hand-made export-format file, so US2 isn't needed.

### Tests for User Story 3 (write first, confirm they fail) ⚠️

- [ ] T029 [P] [US3] Create `backend/tests/unit/test_architecture_import_file.py` with failing tests for `async import_architectures(session, *, owner: User, doc: dict) -> ArchitectureImportResponse` in `backend/src/services/architecture_transfer.py`:
  - **Rejections.** `InvalidImportFileError` is raised for a bad envelope, with no rows written.
  - **Partial success.**
    - Given three entries (valid; name already owned; SKU `ZZZZZZZZZZZZZZZZ`), the result is `[success, failed "Architecture name already exists", failed "Service not found in pricing data: …"]` in file order.
    - Only the first is persisted, with `is_public = false` and the target as owner.
  - **Same-file duplicates.** The second entry with the same name fails.
  - **Unnamed entry.** An unparseable entry gets `name = null` and `Invalid architecture definition: …`.
  - **All-or-nothing.** A DB error raised while inserting one entry (monkeypatched `build_architecture`) rolls back only that entry's SAVEPOINT, and it is reported as failed.
  - **Empty file.** `architectures: []` gives a result with zero counts.
  - **Batching.** SKU existence is queried once per distinct region per file (spy on `find_existing_skus`).
- [ ] T030 [P] [US3] Create `backend/tests/contract/test_admin_architecture_import.py` with failing tests:
  - `POST /api/v1/admin/users/{id}/architectures/import` returns 200 and a correct body for a mixed file.
  - It returns 400 `{"error": "invalid_import_file"}` for a wrong `format`, for `format_version: 2`, and for the old baseline JSON shape (`{"version": "1.0", "architectures": [{"id": …, "components": …}]}` lacks `format`).
  - It returns 422 for a JSON array body, 403 for non-admin, 401 unauthenticated, and 404 for an unknown or guest user.
  - An imported architecture is not visible in the public Import list from feature 012 (FR-023, FR-024).
- [ ] T031 [P] [US3] Create `frontend/tests/unit/ImportResultsDialog.test.tsx` for `frontend/src/components/ImportResultsDialog.tsx`:
  - One row per result, with Status, Architecture and Error columns.
  - A success row shows a green check (`aria-label="Imported"`) and an empty error cell.
  - A failed row shows a red X (`aria-label="Failed"`) and its message.
  - A `null` name renders "(unnamed #n)".
  - An empty results list renders "No architectures were found in this file."

### Implementation for User Story 3

- [ ] T032 [US3] Implement `import_architectures` in `backend/src/services/architecture_transfer.py`:
  - `validate_envelope`.
  - Load the target's non-deleted names into `taken_names`, and get `list_available_regions()`.
  - Pre-parse all entries, collect `(service_code, sku)` pairs per region, and call `find_existing_skus` once per region **before any write**. A `PricingDataUnavailableError` propagates and becomes a 503 with nothing written.
  - Then, per entry in order: `validate_definition` → on success, `async with session.begin_nested():` `build_architecture(...)`, add the name to `taken_names`, record success. A `SQLAlchemyError` inside the SAVEPOINT is recorded as a failed result with the message "Could not save architecture".
  - Commit once at the end.
  - T029 must pass.
- [ ] T033 [US3] Add `POST /admin/users/{user_id}/architectures/import` (`body: ArchitectureImportRequest`, `response_model=ArchitectureImportResponse`) to `backend/src/api/admin_users.py`, and register an `InvalidImportFileError` handler in `backend/src/main.py` returning 400 `{"error": "invalid_import_file", "message": str(exc)}`.
  - Pass `body.model_dump()` to the service, so a wrong `format` or version still reaches `validate_envelope` as a 400, not a 422.
  - T030 must pass (depends on T032).
- [ ] T034 [US3] Regenerate `frontend/src/api/generated/schema.d.ts`. Add the `ArchitectureImportResponse` alias and `importUserArchitectures(userId, doc)` to `frontend/src/api/client.ts`, per contracts/api.md (depends on T033; run after T026 if US2 is also in progress).
- [ ] T035 [P] [US3] Implement `frontend/src/components/ImportResultsDialog.tsx`:
  - Props: `open`, `onOpenChange`, `results: ImportResult[]`, `failedMessage?: string`.
  - It is built on `components/ui/dialog.tsx`, with `lucide-react` `Check` (`text-green-600`) and `X` (`text-destructive`) icons in a three-column table: Status · Architecture · Error.
  - When `failedMessage` is set, it shows that message ("Import failed: …") in place of the table (FR-019, FR-022).
  - T031 must pass.
- [ ] T036 [US3] Update `frontend/src/pages/AdminPage.tsx`: in the Import cell from T028, add an outline `xs` "Import" button that clicks a hidden per-page `<input type="file" accept=".json,application/json">`, remembering the target user id.
  - On `change`:
    - no file selected, i.e. the picker was cancelled → do nothing, and reset the input value;
    - `await file.text()` → `JSON.parse`; a parse error opens `ImportResultsDialog` with `failedMessage="Import failed: the file is not valid JSON."`;
    - otherwise call `api.importUserArchitectures`. A 400 or 422 opens it with `failedMessage` `Import failed: <server message or "the file is not in the expected format">`. On success, open it with the results and invalidate the admin users query, so `architecture_count` refreshes.
  - Depends on T028, T034, T035.

**Checkpoint**: US3 works independently. Mixed files import partially, with an accurate status popup.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T037 [P] Add a "Standard architectures" section to `backend/README.md`. It covers when and how to re-run `scripts/resolve_standard_architectures.py`, that the generated seed and report must not be hand-edited, that the fixture must be rebuilt (T017) afterwards, and that a deleted standard architecture can be restored by importing `src/db/seed/standard_architectures.json` on the Admin row.
- [ ] T038 Run the full automated suites and fix any failures: `cd backend && uv run alembic upgrade head && uv run pytest -v`, then `cd frontend && npm test && npm run lint && npm run build && npm run check-api-types`. CI runs the same commands against `backend/tests/fixtures/pricing_parquet`.
- [ ] T039 Perform all of quickstart.md manually, including step 4's check that the Admin table doesn't scroll horizontally with both new columns (SC-008) and step 6's access-control checks (SC-007). Record any deviations in `specs/014-architecture-templates-import-export/quickstart.md` › a new "Validation notes" section.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: depends on Setup and **blocks every story**.
  - T002–T004 (tests) come first and can run in parallel.
  - T005, T006 and T007 can run in parallel.
  - T008 needs T007, and T009 needs T008.
- **US1 (Phase 3)**: needs Foundational. T013 → T014 → T015 → T016 → T017 → T018 → T019.
- **US2 (Phase 4)**: needs Foundational only. It is independent of US1.
- **US3 (Phase 5)**: needs Foundational only. It is independent of US1 and of US2's backend. Its frontend (T036) edits the same `AdminPage.tsx` as T028, so T036 runs after T028.
- **Polish (Phase 6)**: after the stories you intend to ship.

### Within each story

- Test tasks are written and seen failing before their implementation tasks (Constitution V).
- Service before route before generated types before client before UI.

### Parallel opportunities

- **Phase 2:** T002 ∥ T003 ∥ T004, then T005 ∥ T006 ∥ T007.
- **Across stories:** after Phase 2, US1 (backend scripts, migration) ∥ US2 backend (T020–T025) ∥ US3 backend (T029–T033). The three touch different files, except `admin_users.py`, which T024/T025 (US2) and T033 (US3) both edit, so do them one after the other.
- **Within stories:**
  - US1: T010 ∥ T011 ∥ T012.
  - US2: T020 ∥ T021 ∥ T022, and T027 ∥ the backend work.
  - US3: T029 ∥ T030 ∥ T031, and T035 ∥ the backend work.

---

## Parallel Example: User Story 1

```bash
# Tests first, together:
Task: "T010 [US1] rule/formula/resolver unit tests in backend/tests/unit/test_standard_architecture_rules.py"
Task: "T011 [US1] seed file + migration insert tests in backend/tests/integration/test_standard_architecture_seed.py"
Task: "T012 [US1] seeded pricing test in backend/tests/integration/test_standard_architecture_pricing.py"
```

## Parallel Example: User Story 3

```bash
Task: "T029 [US3] import service tests in backend/tests/unit/test_architecture_import_file.py"
Task: "T030 [US3] import route contract tests in backend/tests/contract/test_admin_architecture_import.py"
Task: "T031 [US3] ImportResultsDialog tests in frontend/tests/unit/ImportResultsDialog.test.tsx"
Task: "T035 [US3] ImportResultsDialog component in frontend/src/components/ImportResultsDialog.tsx"
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phases 1–2 (T001–T009).
2. Phase 3 (T010–T019).
3. **Stop and validate** with quickstart.md steps 1–3. Every user can already copy a priced standard architecture through the existing Import list.

### Incremental delivery

1. Foundation, then US1: demo the standard architectures (MVP).
2. Add US2: the Admin can export any user's architectures, including the standard ones.
3. Add US3: the Admin can import. The round trip with US2's files completes SC-004.
4. Polish (T037–T039).

### Notes

- `[P]` means different files with no dependency on an incomplete task.
- The two files T016 generates are artifacts of the resolver. Regenerate them rather than editing them.
- Commit after each task or logical group. Stop at any checkpoint to validate a story on its own.

# Research: Standard Architectures and Admin Architecture Import/Export

**Feature**: 014-architecture-templates-import-export | **Date**: 2026-09-25

The pricing-data findings below come from exploratory DuckDB queries against the real dataset (`DATA/pricing_aws/parquet`, snapshot `2026-09-24`). They were run while planning.

---

## §1 When and how the standard architectures are created

**Decision**: Split creation into two steps.
1. **Offline resolution.** A developer runs a script against the real pricing dataset. The script turns `docs/common_aws_architectures.md` plus an explicit, checked-in table of per-figure match rules into a **resolved seed file**. That file names each architecture, its VPCs, and every service entry by `service_code` + `sku` + usage quantity. The script also writes a **resolution report** listing every figure it left out and why.
2. **Seeding.** A new Alembic data migration (`0005_standard_architectures`) inserts the resolved seed file under the default Admin account.

**Rationale**:
- **"Created once, never recreated" (FR-003, clarification 3) comes for free.** An Alembic revision runs exactly once per database, including databases that existed before this feature. No seed-marker table is needed (Constitution VI).
- **Migrations never need the pricing dataset.** CI runs `alembic upgrade head` against a small Parquet fixture that doesn't contain these SKUs (`.github/workflows/ci.yml`). Live matching inside a migration or at app startup would fail there, and would also make startup depend on the pricing data being present.
- **"First available match" (FR-008) becomes deterministic and reviewable.** The resolved SKUs are a checked-in diff a human can read, not something re-decided silently on every deploy.
- **Constitution I/II are preserved.** The seed stores only stable vendor identifiers (`service_code`, `sku`), never prices. Prices are still looked up live at calculation time.
- **The source JSON is never loaded into the app.** It is reference input to a developer script only, matching clarification 2.

**Alternatives considered**:
- *Match live in a FastAPI startup hook, with a seed-marker table.* Rejected: the pricing data must be present at every boot, results can change between deploys, and it adds a new table plus boot-time failure modes.
- *Match live inside the migration.* Rejected: it breaks CI's `alembic upgrade head` against the fixture, and makes migrations non-deterministic.

## §2 The resolved seed file uses the export format

**Decision**: The resolved seed file is written in this feature's own architecture export format (§6, `contracts/export-format.md`). It is stored at `backend/src/db/seed/standard_architectures.json`.

**Rationale**: There is one format, one validator and one structure. A test runs the seed file through the same per-architecture validation the Admin import uses. That proves every seeded SKU exists and the structure is consistent. If the Admin ever deletes a standard architecture, it can be restored by importing that file on the Admin row (Constitution VI: no separate restore feature).

**Alternative considered**: A bespoke seed schema. Rejected as a second format to maintain for no benefit.

## §3 How each usage figure is matched to a SKU

**Finding**: Loose matching on service plus a few words picks the wrong SKU. Real examples from the spot check:
- Data transfer from us-east-1 to us-west-2 first matches an **"Accelerated InterRegion Outbound"** SKU, not plain "InterRegion Outbound".
- Glacier Instant Retrieval is filed as `storageClass: "Archive Instant Retrieval"`.
- `cache.m6g.large` Redis returns four SKUs at different prices.
- The EKS "cluster" search also returns an **Outposts** SKU (`locationType: "AWS Outposts"`).

**Decision**: Each usage figure gets one explicit **match rule**, checked in as Python data in `backend/scripts/standard_architectures/match_rules.py`. A rule contains:
- The source architecture and component id.
- A figure label.
- An ordered list of candidate `service_code`s.
- A `product_family`.
- Exact-equality attribute filters on `attributes_json`, e.g. `usagetype`, `instanceType`, `operatingSystem`, `tenancy`, `preInstalledSw`, `capacitystatus`, `databaseEngine`, `deploymentOption`, `storageClass`, `transferType`, `locationType = "AWS Region"`.
- The expected On-Demand `unit`.
- A quantity formula (§5).

The resolver picks the first SKU matching every filter in the target region, ordered by `sku` ascending, so the choice is deterministic. That is "the first available match" of FR-008, made reproducible. A rule that matches nothing is logged to the report and left out (FR-010, FR-009a).

**Rationale**: The exact rules are the audit trail: a reviewer can see why a SKU was chosen. They follow the "explicit, auditable table, never a heuristic" precedent in `pricing_data/duration.py`.

## §4 Translating JSON service names to pricing-data names

Service names checked against `product_dim`:

| JSON `service` | Pricing data | Notes |
|---|---|---|
| AmazonRoute53, AmazonCloudFront, AmazonEC2, AmazonRDS, AmazonS3, AWSDataTransfer, AmazonKinesis, AWSGlue, AmazonAthena, AmazonRedshift, AmazonCognito, AWSLambda, AmazonDynamoDB, AmazonSNS, AmazonEKS, AmazonECR, AmazonElastiCache | Same name | Present in every needed region |
| ElasticLoadBalancing | `AWSELB`, then `AmazonEC2` | **`AWSELB` has no us-east-1 partition.** us-east-1 ALB records exist only under `AmazonEC2` (`Load Balancer-Application`: `Hrs`, `LCU-Hrs`). The rule lists both candidates in order. |
| AmazonAPIGateway | `AmazonApiGateway` | `API Calls` family |
| AmazonSQS | `AWSQueueService` | `API Request` family |
| AWSFargate | `AmazonEKS` | `usagetype` `USW2-Fargate-vCPU-Hours:perCPU` and `USW2-Fargate-GB-Hours` |
| AWSAppMesh | *(none)* | No records. App Mesh has no direct charge, so it is left out and logged (FR-010). |

The ELB fallback to `AmazonEC2` goes slightly beyond clarification 2's wording ("ElasticLoadBalancing → AWSELB"). It is the only way to price the us-east-1 ALB at all. It is recorded here and will be called out in the plan summary.

## §5 Quantity formulas and the daily-rate convention

**Finding** (`services/price_calculation.py`, `pricing_data/duration.py`): an On-Demand entry's cost is `price × usage_quantity`, then:
- `no_period` units (e.g. `Hrs`, `Requests`, `GB`): the quantity is a **per-day rate** and the cost is scaled by the duration's day count.
- `fixed_period` units (e.g. `GB-Mo`, `IOPS-Mo`): the quantity is the amount for that unit's period, and the cost is scaled by `duration_days / period_days`.

**Decision**: A rule's quantity formula produces the per-day value for `no_period` units and the stored or monthly amount for `fixed_period` units:

| JSON shape | Formula | Example |
|---|---|---|
| Always-on resource (`runningHoursPerMonth: 730` / `hoursPerMonth: 730`) × count | `count × 24` | 4 × t4g.xlarge → 96 `Hrs`/day |
| LCU (`lcuPerHour`) | `lcu × 24` | 2 LCU → 48 `LCU-Hrs`/day |
| Monthly count (requests, queries, messages, GB transferred, TB scanned) | `monthly ÷ 31` | 10,000,000 Route 53 queries → 322,580.6452/day |
| Daily figure (`executionHoursPerDay`) | `dpu × hours` | Glue 10 DPU × 2 h → 20 `DPU-Hour`/day |
| Derived compute | Lambda `executions × avg_s × memory_GB ÷ 31` | 15M × 0.25 × 1 ÷ 31 → 120,967.7419 GB-s/day |
| Fargate | `pods × vCPU × 24` and `pods × GB × 24` | 10 × 1 × 24 = 240 vCPU-h/day; 10 × 2 × 24 = 480 GB-h/day |
| Stored amount (`storageGB`, `allocatedStorageGB`, `objectsStored`) against a `GB-Mo`/`Obj-Month` unit | as stored, no conversion | 2,000 GB-Mo |
| Monthly per-user count (`monthlyActiveUsers`) | as stated, fixed period | 10,000 MAU |
| Redshift Serverless (`rpuHoursPerMonth` as total RPU-hours) | `rpu_hours ÷ 31` | 240 → 7.7419 `RPU-Hr`/day |

Quantities are rounded to 4 decimal places, matching `SKUSelection.usage_quantity`'s `Numeric(18, 4)`. An always-on resource shows 744 hours in the app's 31-day month, not the JSON's 730, as the spec's Assumptions already state.

## §6 Billing units the pricing engine doesn't recognize yet (prerequisite fix)

**Finding**: Many units these services bill in are missing from `duration.py`'s explicit tables. The pricing engine would flag every one as `unrecognized` and exclude it from the total, which fails SC-003.

**Decision**: Add these units to the explicit tables, test-first (Constitution V):

| Add to | Units |
|---|---|
| `_NO_PERIOD_UNITS` | `LCU-Hrs`, `Queries`, `ShardHour`, `PutRequest`, `DPU-Hour`, `Terabytes`, `RPU-Hr`, `ReadRequestUnits`, `WriteRequestUnits`, `GB-Hours`, `Notifications` |
| `_FIXED_PERIOD_UNITS` (31 days) | `Obj-Month`, `Mo`, `CognitoUserPoolsMAU`, `GigaBytesMonth` |

The final list is whatever units the resolved seed actually uses. The resolver fails loudly if a chosen SKU's unit is still unrecognized, so this list can't silently drift.

**Rationale**: This is the existing, sanctioned way to teach the engine a unit. Each unit is time-based in AWS's own definition, so nothing is guessed.

## §7 Faithful-pricing judgment calls (to confirm with the user)

1. **The RDS MySQL gp3 IOPS figure (3,000) isn't priced as a separate entry.** gp3 includes a baseline of 3,000 IOPS (12,000 for MySQL volumes of 400 GB or more) at no charge. The pricing data's gp3 `IOPS-Mo` SKU bills IOPS *above* that baseline. Entering 3,000 would add about $60 a month that AWS wouldn't charge. The figure is logged as "included in gp3 baseline" and not approximated (Constitution I).
2. **Aurora "Multi-AZ" can't be expressed as a SKU attribute.** Aurora instance SKUs have no Multi-AZ deployment option; high availability comes from replicas. The Aurora PostgreSQL `db.r6g.xlarge` instance SKU is matched on engine, instance type and the Standard (not I/O-Optimized) storage configuration. The deployment note is logged.
3. **Tiered pricing uses the existing lookup's first-row behavior.** Some SKUs have several price rows by usage tier, e.g. a $0 free first tier for Glue Data Catalog storage and requests, S3 and CloudFront tiers. `lookup_price` returns the first row read. This existing limitation affects every architecture, not only these, and fixing it is out of scope. The resolution report lists every seeded SKU that has more than one price row, so the effect is visible.

## §8 Export and import transport

**Decision**:
- **Export.** `GET /api/v1/admin/users/{user_id}/architectures/export` returns the export document as JSON. The browser builds a `Blob` and saves it through a temporary `<a download>` element named `<safe-username>_<YYYYMMDDTHHMMSS>.json`, using the admin's local time at the moment of download (FR-013, FR-014). Nothing touches the server filesystem.
- **Import.** The admin chooses a file with a hidden `<input type="file" accept=".json,application/json">`.
  - The browser reads the file and runs `JSON.parse`. A parse failure shows "Import failed: the file is not valid JSON" without calling the server.
  - Otherwise it `POST`s the parsed document to `/api/v1/admin/users/{user_id}/architectures/import`.
  - The server rejects a whole file whose envelope is wrong (wrong `format`, unsupported `format_version`, missing or non-list `architectures`) with `400`. The client shows "Import failed".
  - Otherwise the server returns `200` with one result per architecture.
- **Per-architecture validation.** The envelope's `architectures` is typed as a list of loosely typed objects. Each is validated separately against the strict `ArchitectureDefinition` model, so one malformed entry produces a red ✗ row, not a whole-file `422` (FR-020).

**Rationale**: This keeps the typed OpenAPI contract (Constitution IV) while still allowing partial success. `multipart/form-data` would add a dependency (`python-multipart`) and hide the body from the typed schema.

## §9 Per-architecture atomicity on import

**Decision**: Validate each architecture fully before writing anything:
- Name conflicts, including names imported earlier from the same file.
- Region availability via `list_available_regions()`.
- Every `(service_code, sku)` existing in the latest snapshot for its collection's region, using one batched DuckDB query per region through a new `pricing_data/catalog.py` function `find_existing_skus`.
- Internal references (`parent_ref`, `from_ref`/`to_ref`) resolving within that architecture, and nesting rules (only an `application_component` may have a parent, and it must be a `vpc`).

Only then are its rows inserted, inside a `session.begin_nested()` SAVEPOINT. An unexpected DB error rolls back only that architecture, which is reported as a failure (FR-020).

## §10 Reusing the existing deep-copy logic

**Decision**: Extract the "create rows from a source" part of `services/architecture_import.py` into a shared builder in a new `services/architecture_transfer.py`. It has two input adapters: ORM source (the existing public-architecture import from feature 012, unchanged behavior) and export-format definition (Admin import). Export uses a serializer in the same module that walks a non-deleted architecture's non-deleted collections and connectors.

**Rationale**: One place maps parent and connector references to new rows. The existing `test_architecture_import.py` guards the refactor.

## §11 Export button enablement

**Decision**: Add `architecture_count: int` (non-removed architectures) to `AdminUserOut`. It is computed in the `GET /admin/users` query with a grouped count. The Export button is disabled when it is `0` (FR-012).

## §12 Frontend UI details

- **Headers.** The two new `<th>`s use `whitespace-normal` and a narrow max width, so "Import Architectures from Disk" and "Export Architectures to Disk" wrap onto 2–3 lines (FR-011). The table's `max-w-2xl` stays; SC-008 is checked manually per the quickstart.
- **Result popup.** It reuses the existing `components/ui/dialog.tsx` and `lucide-react`'s `Check` (green, `text-green-600`) and `X` (red, `text-destructive`) icons, with a three-column table: Status, Architecture, Error (FR-022).
- **Tests.** Vitest and Testing Library, following `frontend/tests/unit/*.test.tsx`: the filename builder and sanitizer, and the result dialog's rows.

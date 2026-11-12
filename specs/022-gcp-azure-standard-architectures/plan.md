# Implementation Plan: GCP and Azure Standard Architectures

**Branch**: `022-gcp-azure-standard-architectures` | **Date**: 2026-11-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/022-gcp-azure-standard-architectures/spec.md`

## Summary

This adds the GCP and Azure equivalents of the four AWS standard architectures: eight public
Admin architectures, created once in every environment. Technically:

- **Generator:** the 014 resolver is extended per provider (Principle III), and the AWS output
  stays byte-identical.
  - `resolve_standard_architectures.py --provider gcp|azure` applies new explicit rule
    modules, `match_rules_gcp.py` and `match_rules_azure.py`, against that provider's real
    snapshot. Each provider has its own SKU finder: GCP reads `sku` / `sku_price`, Azure reads
    `price_item`.
  - It writes `standard_architectures_{gcp,azure}.json` (export format, with
    `provider_options` for machines) and a report per provider. Each report row names the AWS
    component it stands in for, and gives the original and chosen sizes.
  - The usage formulas move to a shared `quantities.py`, so all three providers convert usage
    the same way.
- **Seeding:** a new Alembic revision, 0009, inserts the eight with plain SQL. It runs once per
  database and skips any architecture the Admin already owns with the same name and provider.
  `ops db-init` runs it on every bring-up, so it reaches local, fresh, existing and restored
  environments.
- **Sizing:** the smallest size with at least the same vCPU and memory (clarification 2). GCP
  machines and Cloud SQL use the existing `gcp_machine` composite pricing; Azure VMs use
  `azure_vm {os: linux}`.
- **Regions:** from what the pricing pipeline actually collects. The Azure Serverless design
  moves from northeurope to westeurope (research R1).
- **No changes** to the API, the frontend, the pricing engine or the schema.

## Technical Context

**Language/Version**: Python 3.12 (backend and scripts).

**Primary Dependencies**: Alembic and SQLAlchemy (migration, plain SQL); DuckDB 1.5 (generator
lookups over Parquet); Pydantic 2 (`ArchitectureExportFile`); the existing pricing adapters
(`src/pricing_data/providers/{gcp,azure}.py`), which are used unchanged.

**Storage**:
- PostgreSQL: rows in the existing `architectures`, `collections` and `sku_selections`
  tables.
- Parquet pricing data: read-only, local pipeline store, for generation only.

**Testing**:
- pytest: unit, integration, and the restore integration test, which needs `pg_dump` on PATH.
- Optional: a Playwright check.

**Target Platform**: the existing app; Linux containers in the cloud and macOS locally.

**Project Type**: web application. Changes are in `backend/` only; generated data goes in
`backend/src/db/seed/`.

**Performance Goals**: the migration inserts about 8 architectures and about 100 selections in
well under a second, adding nothing noticeable to the `db-init` 600s budget. The generator has
no target, since it's an offline developer command.

**Constraints**:
- Generated files are never hand-edited.
- Output is deterministic.
- The AWS seed and report don't change.
- 0005 isn't modified.
- No new npm or Python packages.
- Don't commit `specs/018-app-cloud-deployment/acceptance.md` or `.idea/`.

**Scale/Scope**: 8 architectures, about 50 rules per provider (one per AWS reference figure),
5 collections per provider.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Pricing Data Integrity | PASS | Seeds hold SKU references, never prices. A figure without a real SKU is left out with a reason, never approximated. A unit the engine can't classify fails generation. Rows are copied verbatim into the fixtures. |
| II. Data-Layer Separation | PASS | Postgres gets user-defined data only (architectures and selections by stable `service_code` and `sku`). Parquet is read-only. |
| III. Multi-Provider by Design | PASS | Provider is a field throughout (rules module, finder, seed file, existence check). Each provider's lookup reads its own tables. The AWS path isn't rewritten, only joined by GCP and Azure. |
| IV. Type-Safe Contract | PASS (n/a) | No API or frontend changes. The seed files use the existing typed `ArchitectureExportFile`. |
| V. Test-First | PASS (planned) | Finder, quantity, report, seed-validation, pricing and migration tests are written before the code (research R9). |
| VI. Simplicity & YAGNI | PASS | It reuses the 014 generator and the 0005 pattern. No mapping file or abstraction for agent-04 (research R10), and no marker table. |

**Post-design re-check**: still PASS. The design added no new store, service boundary or
dependency.

## Project Structure

### Documentation (this feature)

```text
specs/022-gcp-azure-standard-architectures/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R10
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── generator.md     # CLI, outputs, report columns, exit codes
│   └── migration-0009.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── scripts/
│   ├── resolve_standard_architectures.py      # + --provider; per-provider snapshot, outputs
│   ├── build_provider_fixtures.py             # + seeded GCP/Azure SKUs and new locations
│   └── standard_architectures/
│       ├── quantities.py                      # NEW: formulas moved from match_rules.py
│       ├── match_rules.py                     # AWS (imports quantities; rules unchanged)
│       ├── match_rules_gcp.py                 # NEW
│       ├── match_rules_azure.py               # NEW
│       └── resolver.py                        # + GCP/Azure finders, provider-aware export & report
├── src/db/
│   ├── seed/
│   │   ├── standard_architectures_gcp.json         # NEW, generated
│   │   ├── standard_architectures_gcp_report.md    # NEW, generated
│   │   ├── standard_architectures_azure.json       # NEW, generated
│   │   └── standard_architectures_azure_report.md  # NEW, generated
│   └── migrations/versions/
│       └── 0009_gcp_azure_standard_architectures.py  # NEW
└── tests/
    ├── unit/test_standard_architecture_resolver_{gcp,azure}.py   # NEW
    ├── unit/test_standard_architecture_quantities.py             # NEW
    ├── integration/test_standard_architecture_seed.py            # + GCP/Azure seed validation
    ├── integration/test_standard_architecture_pricing.py         # + the eight price fully
    ├── integration/test_migration_0009.py                        # NEW
    ├── integration/test_db_init_restore.py                       # + pre-0009 backup gains 8
    └── fixtures/pricing_parquet/{gcp,azure}/                     # rebuilt

frontend/e2e/standard-architectures.spec.ts   # NEW, optional (one GCP + one Azure calculate)

docs/features/architectures-and-canvas.md     # standard architectures now on all three providers
CHANGELOG.md                                  # one line under the release
```

**Structure Decision**: this is backend-only work inside the existing web-application layout.
It mirrors 014's generator and seed pattern, so a reviewer finds each piece where the AWS
version already lives.

## Implementation order

1. **Data prerequisite:** refresh the local GCP and Azure snapshots with `europe-west1` and
   `westeurope` (quickstart). This blocks generation, but not writing the tests.
2. **Shared formulas:** move the formulas to `quantities.py`. Re-run AWS generation and check
   there's no diff.
3. **Finders:** write the failing finder tests against inline Parquet, then the GCP and Azure
   finders in `resolver.py`. Add the provider-aware export and report, with the AWS output
   unchanged.
4. **Rules, then generation:** write the rule modules, one design at a time. Check each design
   against the report: confirm the sizes and conversions, and correct the rules wherever a
   figure is left out that should match.
5. **Fixtures:** rebuild the test data set, then write the seed-validation and pricing tests.
6. **Migration:** write the 0009 tests, then the migration. Then the restore test.
7. **Docs:** add the docs and CHANGELOG lines. Optionally add the e2e check.

## Risks

- **Conversions and engine units.** Some serverless and streaming units may not be classified
  by the engine (`units.py`, `duration.py`). The generator fails loudly. The fix is to leave
  that figure out with a reason, never to add an approximate unit mapping inside this feature.
- **Production pricing data must have the European regions** that the Serverless designs use.
  The production pipeline already collects them (R1), so this is only a local-data step.
- **Forced mappings.** Following the owner's rule (research R5), a figure whose counterpart
  bills a different kind of unit is left out rather than converted. Redshift Serverless is left
  out on both, and Fargate is left out on Azure. Comparing these designs' totals is therefore
  partial, and the reports say so.

## Complexity Tracking

No violations to justify.

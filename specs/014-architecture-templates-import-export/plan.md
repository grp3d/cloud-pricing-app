# Implementation Plan: Standard Architectures and Admin Architecture Import/Export

**Branch**: `014-architecture-templates-import-export` | **Date**: 2026-09-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-architecture-templates-import-export/spec.md`

## Summary

The feature has two parts.

**Part 1: four standard architectures, owned by Admin and public.** They are built from `docs/common_aws_architectures.md`, which contains:
- Active-Standby Multi-Region Web Application
- Modern Data Lake & ETL Analytics Pipeline
- Serverless Microservices Back-End
- Containerized Microservices Platform (EKS)

A developer-run resolver script matches every usage figure in that file to a real SKU in the pricing dataset. It uses explicit, checked-in match rules (research §3–§5) and writes a deterministic seed file in this feature's own export format, plus a report of anything left out. A one-time Alembic data migration inserts that seed under the default Admin. This gives "created once, never recreated" without a marker table, and keeps migrations independent of the pricing dataset (research §1–§2).

**Part 2: admin-only Import/Export on the Admin tab.**
- **Export** downloads all of one user's architectures as `username_<timestamp>.json`.
- **Import** reads such a file from the admin's computer. It validates and inserts each architecture on its own, with all-or-nothing writes per architecture, and shows a ✓/✗ result popup.
- One versioned JSON format ([contracts/export-format.md](contracts/export-format.md)) serves export, import and the seed.

**Prerequisite fix found in research (§6)**: about 15 billing units these services use (`LCU-Hrs`, `ShardHour`, `DPU-Hour`, `RPU-Hr`, `Terabytes`, `CognitoUserPoolsMAU`, …) aren't yet recognized by the pricing engine. They would show as unpriceable, so they are added to the explicit unit tables, test-first.

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 5 with React 18 (frontend)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, DuckDB (backend); Vite, TanStack Query, Tailwind, shadcn/ui, lucide-react, openapi-typescript (frontend). **No new dependencies.**

**Storage**: PostgreSQL for user-defined data, with no schema change and only data inserted by migration `0005`. Parquet via DuckDB for vendor pricing, read-only.

**Testing**: pytest against a real Postgres, plus the Parquet fixture in CI (backend). Vitest and Testing Library (frontend). `check-api-types` for contract drift.

**Target Platform**: Local and hosted web app; modern desktop browsers (download via `Blob` + `<a download>`, `<input type="file">`).

**Project Type**: Web application (`backend/` + `frontend/`)

**Performance Goals**: Import validation makes one batched DuckDB SKU-existence query per region per file, not one per SKU. An export or import of a user with tens of architectures completes in under 2 seconds.

**Constraints**:
- No server-side file storage (FR-014).
- No vendor prices in exports or the seed (Constitution I/II).
- Deterministic seed resolution.
- Migrations must run with no pricing dataset present (CI).

**Scale/Scope**:
- 4 seeded architectures with about 45 service entries.
- Admin-only feature for a handful of users.
- 2 new endpoints and 1 changed response.
- About 1 page of UI changes.

## Constitution Check

*GATE: must pass before Phase 0 research, and is re-checked after Phase 1 design.*

| Principle | Assessment | Status |
|---|---|---|
| **I. Pricing Data Integrity** | The seed and exports carry only `service_code`/`sku` references. Prices are always looked up live. No approximation: figures without a match are left out and logged, e.g. App Mesh (§4) and gp3 IOPS already included in the baseline (§7.1). The existing tiered-price first-row behavior is left as-is but made visible in the report (§7.3). | ✅ Pass |
| **II. Data-Layer Separation** | Nothing is written to Parquet. Import checks SKU existence *against* DuckDB but stores only references in Postgres. | ✅ Pass |
| **III. Provider-Extensibility** | The export format carries `provider` per architecture. Validation rejects non-`aws` only because no other pricing data exists. There are no AWS-only type or table names. The service-name translation lives in the AWS resolver script's rules, not in shared models. | ✅ Pass |
| **IV. Type-Safe Contract** | New Pydantic request/response models are regenerated into `schema.d.ts`, and CI `check-api-types` gates drift. The lenient `architectures: list[dict]` envelope is intentional (§8): each item is still validated against a strict, published `ArchitectureDefinition` model. | ✅ Pass |
| **V. Test-First** | Tests are written first for the unit-table additions, the match-rule resolver and quantity formulas, `find_existing_skus` (DuckDB), export serialization, per-architecture import validation and atomicity, and the seed file's validity. Frontend presentational code may be tested after. | ✅ Pass (enforced in tasks) |
| **VI. Simplicity & YAGNI** | No marker table, no template entity, no restore action. Restoring a deleted standard architecture is possible by importing the checked-in seed file. The existing deep-copy code is refactored into one shared builder rather than duplicated. | ✅ Pass |

**Post-design re-check (after Phase 1)**: No violations were introduced. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/014-architecture-templates-import-export/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── api.md           # Admin export/import endpoints, AdminUserOut change
│   └── export-format.md # Architecture Export File v1
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code

```text
backend/
├── scripts/
│   ├── resolve_standard_architectures.py        # NEW: dev-run resolver (research §1–§5)
│   ├── standard_architectures/
│   │   ├── __init__.py                          # NEW
│   │   ├── match_rules.py                       # NEW: explicit per-figure rules + quantity formulas
│   │   └── resolver.py                          # NEW: rule → SKU matching (DuckDB), report writer
│   └── build_test_pricing_fixture.py            # CHANGED: SEED_SKUS += seeded SKUs used by tests
├── src/
│   ├── api/admin_users.py                       # CHANGED: architecture_count; export/import routes
│   ├── db/
│   │   ├── migrations/versions/0005_standard_architectures.py  # NEW: data migration
│   │   └── seed/
│   │       ├── standard_architectures.json      # NEW (generated): export-format v1
│   │       └── standard_architectures_report.md # NEW (generated)
│   ├── models/schemas.py                        # CHANGED: export/import models, AdminUserOut field
│   ├── pricing_data/
│   │   ├── catalog.py                           # CHANGED: find_existing_skus(pairs, region)
│   │   └── duration.py                          # CHANGED: new recognized units (§6)
│   └── services/
│       ├── architecture_import.py               # CHANGED: delegates to architecture_transfer
│       └── architecture_transfer.py             # NEW: serialize (export), validate + build (import)
└── tests/
    ├── unit/
    │   ├── test_duration.py                     # CHANGED: new units
    │   ├── test_standard_architecture_rules.py  # NEW: quantity formulas, rule → SKU resolution
    │   ├── test_architecture_transfer.py        # NEW: serialize/validate/build, refs, nesting
    │   └── test_architecture_import.py          # EXISTING: guards the refactor
    ├── contract/
    │   └── test_admin_architecture_transfer.py  # NEW: export/import routes, 400/403/404, partial success
    └── integration/
        └── test_standard_architecture_seed.py   # NEW: seed file valid vs. fixture; migration result

frontend/
├── src/
│   ├── api/client.ts                            # CHANGED: exportUserArchitectures, importUserArchitectures
│   ├── api/generated/schema.d.ts                # REGENERATED
│   ├── lib/exportFilename.ts                    # NEW: safe username + timestamp builder
│   ├── components/ImportResultsDialog.tsx       # NEW: ✓/✗ results table
│   └── pages/AdminPage.tsx                      # CHANGED: two wrapped columns, buttons, file input
└── tests/unit/
    ├── exportFilename.test.ts                   # NEW
    └── ImportResultsDialog.test.tsx             # NEW
```

**Structure Decision**: Use the existing `backend/` + `frontend/` web-app layout. The resolver lives under `backend/scripts/` next to the existing `build_test_pricing_fixture.py`, because it is a developer tool, not application code (research §1). The checked-in seed file sits beside the migrations that consume it.

## Key Design Decisions

The rationale for each is in [research.md](research.md).

1. **Resolve offline, seed by migration** (§1). The migration reads `src/db/seed/standard_architectures.json` and inserts rows with plain SQL, in the style of `0004`. It never imports app ORM code, so later model changes can't break it. It skips any architecture name the Admin already owns.
2. **Explicit match rules, sorted by SKU for "first match"** (§3). ELB tries `AWSELB` first, then `AmazonEC2`, because us-east-1 ALB pricing exists only under `AmazonEC2` (§4).
3. **One export format for seed, export and import** (§2). A test runs the seed through the import validator, so every seeded SKU is proven to exist in the pricing snapshot.
4. **A lenient envelope with per-item strict validation**, validated fully before writing and inserted inside a SAVEPOINT (§8–§9).
5. **A shared transfer module** (§10). The existing public-architecture import from feature 012 keeps its exact behavior through the refactored builder.

## Items to Confirm with the User

These are recorded in research §4 and §7. They don't block tasks, but each changes the seeded content slightly:
- The us-east-1 ALB is priced from `AmazonEC2` load-balancer SKUs, because `AWSELB` has no us-east-1 records.
- The RDS gp3 figure of 3,000 IOPS is logged as included in the gp3 baseline, not priced as an extra ~$60/month.
- Aurora "Multi-AZ" is matched on the instance SKU alone, since Aurora pricing has no Multi-AZ attribute.
- SKUs with tiered prices use the existing first-row lookup. This is an app-wide limitation, flagged in the report.

## Complexity Tracking

No constitution violations to justify.

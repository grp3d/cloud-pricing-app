# Implementation Plan: Provider Icons and Price Change Fixes

**Branch**: `020-provider-icons-connector-fixes` | **Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/020-provider-icons-connector-fixes/spec.md`

## Summary

Two fixes for v0.0.3. The deferred connector work in the spec is not part of this plan.

**1. Price Change (User Story 1).** The comparison that decides whether an architecture changed
ignores a selection's provider options (GCP vCPUs and memory, Azure OS) and its region. The
Duration-switch re-pricing (`POST /catalog/calculate-snapshot`) prices every previous selection
as AWS in us-east-1, with no options. The fix has four parts:

- Compare all pricing inputs.
- Send the provider, each selection's region and its options to the snapshot endpoint, which
  then prices them through the shared path.
- Store a versioned baseline.
- Treat baselines from v0.0.2 as legacy. For GCP and Azure, the Duration-switch case shows
  "Not available: previous calculation from prior version is unreliable".

**2. Icons (User Story 2).** The diagram resolves every icon through the AWS resolver. The fix
has three parts:

- Add generated, reviewed GCP and Azure icon maps (per service, plus ordered per-service
  overrides for disks, IP addresses, snapshots and load balancing), built by a new generator
  script from the official icon packages. Only used SVGs are shipped.
- Choose the resolver by the architecture's provider.
- Draw a fallback tile (a small provider logo plus the service's name, same 60 px size) when a
  GCP or Azure service has no icon. `SKUSelectionOut` gains `service_name` for it.

AWS icons are unchanged.

## Technical Context

**Language/Version**: Python 3.12+ (venv 3.14) backend; TypeScript 5.6 frontend.

**Primary Dependencies**:
- Backend: FastAPI, Pydantic v2, DuckDB, SQLAlchemy (async).
- Frontend: React 18, Vite 5, @xyflow/react 12, Tailwind 4.

**Storage**:
- Postgres: no change and no migration.
- Pricing Parquet: read-only, unchanged.
- Browser `localStorage`: Price Change baseline and stored pricing result, both versioned.

**Testing**: pytest (contract, unit, integration against the real test DB and fixture Parquet);
Vitest with Testing Library (frontend).

**Target Platform**: Web app. Local, plus the packaged Docker stack on AWS.

**Project Type**: Web application (`backend/` + `frontend/`).

**Performance Goals**:
- The Duration-switch re-pricing stays one request, as today.
- Icon lookup is a static map lookup, with no runtime matching.

**Constraints**:
- AWS icons and behaviour byte-identical (FR-012).
- No layout changes (FR-013).
- Only used, unmodified icon SVGs are shipped (FR-014).
- Additive API changes only.

**Scale/Scope**:
- GCP: 1,748 services in the local data, mostly marketplace software, so most fall back by
  design.
- Azure: 188 services.
- About 40 to 80 icons expected per provider, including overrides.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Pricing Data Integrity | Price Change comes from real calculations through the shared pricing path, never estimated. Where the previous contents can't be re-priced faithfully (a legacy GCP or Azure baseline), the app says "Not available" instead of showing a number. Fixing the us-east-1 re-pricing removes an existing silent inaccuracy. | Pass |
| II. Data-Layer Separation | No Postgres changes. `service_name` is resolved from Parquet at response time and never stored. The icon maps are frontend display data keyed by stable vendor ids. | Pass |
| III. Multi-Provider by Design | The snapshot request gains `provider`, with the same shape for all providers. Icon resolution is one resolver per provider behind one shared entry point. The AWS resolver is untouched, and GCP and Azure are added as extensions. | Pass |
| IV. Type-Safe Contract | The request and response changes are Pydantic models, and the frontend types are regenerated. `check-api-types` must pass. | Pass |
| V. Test-First | Tests come before code for: the snapshot endpoint and `build_transient_architecture` (provider, region, options, defaults), `priceChange.ts` (the comparison key, the legacy rule, `unavailable`), the stored-record type guards, the icon resolvers, and the generator's matching and override logic. The fallback tile's look is UI-only, so its tests may follow the code. | Pass |
| VI. Simplicity | One generator script for both new providers. No change to the AWS script. No admin coverage reporting for GCP or Azure. No new storage. The connector work stays deferred. | Pass |

No violations, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/020-provider-icons-connector-fixes/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R7
├── data-model.md
├── quickstart.md
├── contracts/api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (not created here)
```

### Source Code

```text
backend/
├── scripts/
│   └── generate_provider_service_icon_map.py   # NEW: --provider gcp|azure (R5)
├── src/
│   ├── models/schemas.py                        # CalculateSnapshotRequest.provider; SnapshotSelection.region,
│   │                                            #   provider_options; SKUSelectionOut.service_name
│   ├── services/price_calculation.py            # build_transient_architecture: provider, per-region collections, options
│   ├── services/architecture_service.py         # resolve service_name with attributes/product_family
│   └── api/calculate.py                         # pass provider through
└── tests/
    ├── contract/test_calculate_snapshot*.py     # provider/region/options, defaults, 422 on kind mismatch
    ├── unit/test_price_calculation*.py          # transient architecture grouping and options
    └── unit/test_provider_icon_generator.py     # NEW: normalization, overrides, determinism, coverage report

frontend/
├── src/
│   ├── lib/priceChange.ts                       # key + legacy rule + `unavailable`
│   ├── lib/priorCalculation.ts                  # version 2 baseline, legacy read
│   ├── lib/architecturePricingResults.ts        # pricedContents with provider_options, legacy read
│   ├── lib/serviceIcons.ts                      # NEW: resolveServiceIcon(provider, selection) → icon | fallback
│   ├── lib/gcpServiceIcons.generated.ts         # NEW (generated)
│   ├── lib/azureServiceIcons.generated.ts       # NEW (generated)
│   ├── assets/gcp-icons/, assets/azure-icons/   # NEW (generated, used SVGs only, + README)
│   ├── components/workspace/ArchitectureDiagramPanel.tsx  # use resolveServiceIcon; fallback tile
│   ├── pages/WorkspacePage.tsx                  # build v2 selections; send provider/region/options; show "Not available" note
│   ├── components/workspace/PricingPanel.tsx    # Price Change "Not available" display
│   └── api/client.ts, api/generated/schema.d.ts # regenerated types
└── tests/unit/
    ├── priceChange.test.ts                      # extended
    ├── priorCalculation.test.ts / architecturePricingResults.test.ts  # legacy + v2
    ├── serviceIcons.test.ts                     # NEW
    └── ArchitectureDiagramPanel icon tests      # fallback tile, AWS unchanged
```

**Structure Decision**: the existing web-application layout. All changes sit in existing modules,
apart from the new generator script, the shared icon resolver and the generated icon modules and
assets.

## Implementation Order

1. **Price Change, backend.** Write the snapshot request tests first, then the code.
2. **Price Change, frontend.** Write tests for the comparison key, the legacy rule and the
   `unavailable` outcome first. Then the page wiring, the "Not available" note, and regenerating
   the types.
3. **`service_name`.** Add it to `SKUSelectionOut`, with a test first.
4. **Generator script.** Unit tests first. Then run it for GCP and for Azure, review the report,
   and add overrides until categorized services have no gaps (SC-003). Check in the generated
   modules and SVGs.
5. **Icons in the diagram.** The resolver, with tests first. Then the fallback tile and the
   diagram wiring, then the AWS no-change check.
6. **Quickstart A to D**, then docs and the v0.0.3 release notes.

User Story 1 can ship without User Story 2, and the other way round.

## Spec Updates Made While Planning

- **FR-005 and edge cases:** the legacy Duration-switch rule now covers every GCP or Azure
  architecture, not only ones with a machine or VM, because a legacy baseline has no region
  either (research R3).
- **Assumptions:** a Duration switch on an AWS architecture with boxes outside us-east-1 now gets
  a correct Price Change, where it was priced at us-east-1 rates. That is the only AWS change
  (research R2).
- **FR-001:** region is now listed among the settings that count as a change (research R1).

## Complexity Tracking

None. There are no Constitution Check violations.
